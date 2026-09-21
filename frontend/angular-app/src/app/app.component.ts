import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule, HttpErrorResponse } from '@angular/common/http';

interface TeamOption {
  id: string;
  name: string;
  abbreviation: string;
  logo_url: string;
  randomness_score: number;
}

interface TeamColors {
  primary: string;
  secondary: string;
}

const TEAM_COLORS: Record<string, TeamColors> = {
  ARI: { primary: '#97233f', secondary: '#ffb612' }, ATL: { primary: '#a71930', secondary: '#000000' },
  BAL: { primary: '#241773', secondary: '#9e7c0c' }, BUF: { primary: '#00338d', secondary: '#c60c30' },
  CAR: { primary: '#0085ca', secondary: '#101820' }, CHI: { primary: '#0b162a', secondary: '#c83803' },
  CIN: { primary: '#fb4f14', secondary: '#000000' }, CLE: { primary: '#311d00', secondary: '#ff3c00' },
  DAL: { primary: '#003594', secondary: '#869397' }, DEN: { primary: '#fb4f14', secondary: '#002244' },
  DET: { primary: '#0076b6', secondary: '#b0b7bc' }, GB: { primary: '#203731', secondary: '#ffb612' },
  HOU: { primary: '#03202f', secondary: '#a71930' }, IND: { primary: '#002c5f', secondary: '#a5acaf' },
  JAX: { primary: '#006778', secondary: '#d7a22a' }, KC: { primary: '#e31837', secondary: '#ffb81c' },
  LV: { primary: '#000000', secondary: '#a5acaf' }, LAC: { primary: '#0080c6', secondary: '#ffc20e' },
  LAR: { primary: '#003594', secondary: '#ffa300' }, MIA: { primary: '#008e97', secondary: '#fc4c02' },
  MIN: { primary: '#4f2683', secondary: '#ffc62f' }, NE: { primary: '#002244', secondary: '#c60c30' },
  NO: { primary: '#d3bc8d', secondary: '#101820' }, NYG: { primary: '#0b2265', secondary: '#a71930' },
  NYJ: { primary: '#125740', secondary: '#000000' }, PHI: { primary: '#004c54', secondary: '#a5acaf' },
  PIT: { primary: '#ffb612', secondary: '#101820' }, SF: { primary: '#aa0000', secondary: '#b3995d' },
  SEA: { primary: '#002244', secondary: '#69be28' }, TB: { primary: '#d50a0a', secondary: '#34302b' },
  TEN: { primary: '#0c2340', secondary: '#4b92db' }, WSH: { primary: '#5a1414', secondary: '#ffb81c' }
};

interface BoardEntry {
  rank: number;
  player_id: string;
  name: string;
  position: string;
  school: string;
  score: number;
  need: number;
  fit: number;
  source: string;
}

interface TeamBoardEntryPayload {
  player_id: string;
  rank_position: number;
  score: number;
  score_breakdown?: { need?: number; fit?: number;
    team_need?: number; team_fit?: number; };
  first_name?: string | null;
  last_name?: string | null;
  position?: string | null;
  college_name?: string | null;
  college_abbreviation?: string | null;
}

interface TeamBoardMetadata {
  id: number;
  version: number;
  board_type: 'default' | 'personal';
  generated_at: string;
  scoring_version: string;
}

interface TeamBoardResponse {
  team_id: string;
  draft_year: number;
  board: TeamBoardMetadata | null;
  entries: TeamBoardEntryPayload[];
}

interface AuthResponse {
  id: string;
  email: string;
  access_token: string;
  token_type: string;
  favorite_team_id: string | null;
}

@Component({
  selector: 'umm-root',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent implements OnInit {
  protected teams: TeamOption[] = [];
  protected selectedTeamId = '';
  protected boardMode: 'default' | 'personal' = 'default';
  protected authMode: 'login' | 'register' = 'login';
  protected activeEntry: BoardEntry | null = null;
  protected saved = false;
  protected entries: BoardEntry[] = [];
  protected loading = false;
  protected error: string | null = null;
  protected authMessage: string | null = null;
  protected authEmail = '';
  protected authPassword = '';
  protected authFirstName = '';
  protected authLastName = '';
  protected favoriteTeamId = '';
  protected preferredTeamId: string | null = null;
  protected favoriteTeamMessage: string | null = null;
  protected savingFavoriteTeam = false;
  protected boardVersion: number | null = null;
  protected overallRandomness = 50;
  protected teamRandomnessOverrides: Record<string, number> = {};
  protected draftRunMessage: string | null = null;
  protected startingDraft = false;

  private readonly apiBase = 'http://localhost:8000';
  private accessToken = '';
  private boardId: number | null = null;
  private readonly draftYear = 2027;

  constructor(private readonly http: HttpClient) {}

  ngOnInit(): void {
    this.http.get<TeamOption[]>(`${this.apiBase}/api/teams`).subscribe({
      next: (teams) => {
        this.teams = teams;
        if (this.isAuthenticated && teams.length > 0) {
          const previousTeamId = this.selectedTeamId;
          this.selectedTeamId = this.preferredTeamId && teams.some((team) => team.id === this.preferredTeamId)
            ? this.preferredTeamId
            : this.selectedTeamId || teams[0].id;
          if (this.selectedTeamId !== previousTeamId || !this.entries.length) {
            this.loadBoard();
          }
        }
      },
      error: () => {
        this.error = 'Unable to load teams from the API.';
      }
    });
  }

  protected get selectedTeamName(): string {
    return this.teams.find((team) => team.id === this.selectedTeamId)?.name ?? 'Select team';
  }

  protected get selectedTeamAbbreviation(): string {
    return this.teams.find((team) => team.id === this.selectedTeamId)?.abbreviation ?? 'NFL';
  }

  protected get selectedTeamLogoUrl(): string {
    return this.teams.find((team) => team.id === this.selectedTeamId)?.logo_url ?? '';
  }

  protected get selectedTeamColors(): TeamColors {
    if (!this.isAuthenticated) {
      return { primary: '#e65734', secondary: '#1d2a2d' };
    }
    return TEAM_COLORS[this.selectedTeamAbbreviation] ?? { primary: '#e65734', secondary: '#1d2a2d' };
  }

  protected get selectedTeamRandomness(): number {
    const override = this.teamRandomnessOverrides[this.selectedTeamId];
    return override ?? this.teams.find((team) => team.id === this.selectedTeamId)?.randomness_score ?? 50;
  }

  protected setSelectedTeamRandomness(value: number): void {
    if (!this.selectedTeamId) return;
    this.teamRandomnessOverrides = { ...this.teamRandomnessOverrides, [this.selectedTeamId]: Number(value) };
  }

  protected get isAuthenticated(): boolean {
    return this.accessToken.length > 0;
  }

  protected get canCopyBoard(): boolean {
    return this.isAuthenticated && this.boardMode === 'default' && this.entries.length > 0;
  }

  protected get canSaveBoard(): boolean {
    return this.isAuthenticated && this.boardMode === 'personal' && this.entries.length > 0 && this.boardId !== null;
  }

  protected get syncLabel(): string {
    if (this.boardMode === 'personal' && this.boardVersion !== null) {
      return `My board v${this.boardVersion}`;
    }
    if (this.boardVersion !== null) {
      return `Default board v${this.boardVersion}`;
    }
    return this.isAuthenticated ? 'Signed in' : 'Guest mode';
  }

  protected get boardActionLabel(): string {
    if (this.boardMode === 'personal') {
      return this.canSaveBoard ? (this.saved ? 'Saved' : 'Save changes') : 'Copy to edit';
    }
    return this.entries.length > 0 ? 'Copy to My board' : 'Generate default board';
  }

  protected get boardActionEnabled(): boolean {
    if (this.boardMode === 'personal') {
      return this.canSaveBoard;
    }
    return this.entries.length > 0 ? this.canCopyBoard : this.isAuthenticated;
  }

  protected onTeamChange(): void {
    this.boardId = null;
    this.boardVersion = null;
    this.loadBoard();
  }

  protected setBoardMode(mode: 'default' | 'personal'): void {
    this.boardMode = mode;
    this.boardId = null;
    this.boardVersion = null;
    this.loadBoard();
  }

  protected setAuthMode(mode: 'login' | 'register'): void {
    this.authMode = mode;
    this.authMessage = null;
  }

  protected loadBoard(): void {
    if (!this.selectedTeamId) {
      this.entries = [];
      this.activeEntry = null;
      return;
    }

    if (this.boardMode === 'personal' && !this.isAuthenticated) {
      this.entries = [];
      this.activeEntry = null;
      this.error = 'Sign in to load or save your personal board.';
      return;
    }

    this.loading = true;
    this.error = null;

    this.http
      .get<TeamBoardResponse>(
        `${this.apiBase}/api/teams/${this.selectedTeamId}/board?draft_year=${this.draftYear}&board_type=${this.boardMode}`,
        this.requestOptions(this.boardMode === 'personal')
      )
      .subscribe({
        next: (response) => {
          this.boardId = response.board?.id ?? null;
          this.boardVersion = response.board?.version ?? null;
          this.entries = this.mapEntries(response.entries ?? []);
          this.loading = false;
          this.activeEntry = this.entries[0] ?? null;
          if (!response.board) {
            this.error = this.boardMode === 'personal'
              ? 'No personal board yet. Copy the default board to start editing.'
              : 'No board is available yet for this team. Generate one to continue.';
          }
        },
        error: (error: HttpErrorResponse) => {
          this.loading = false;
          this.entries = [];
          this.activeEntry = null;
          this.boardId = null;
          this.boardVersion = null;
          this.error = this.describeApiError(error, this.boardMode === 'personal'
            ? 'Unable to load your personal board.'
            : 'No board is available yet for this team.');
        }
      });
  }

  protected register(): void {
    this.authMessage = null;
    this.error = null;
    this.http.post<AuthResponse>(`${this.apiBase}/auth/register`, {
      email: this.authEmail,
      password: this.authPassword,
      first_name: this.authFirstName,
      last_name: this.authLastName,
      favorite_team_id: this.favoriteTeamId
    }).subscribe({
      next: (response) => {
        this.completeAuthentication(response, 'Account created.');
      },
      error: (error: HttpErrorResponse) => {
        this.authMessage = this.describeApiError(error, 'Unable to create account.');
      }
    });
  }

  protected login(): void {
    this.authMessage = null;
    this.error = null;
    this.http.post<AuthResponse>(`${this.apiBase}/auth/login`, {
      email: this.authEmail,
      password: this.authPassword
    }).subscribe({
      next: (response) => {
        this.completeAuthentication(response, 'Signed in.');
      },
      error: (error: HttpErrorResponse) => {
        this.authMessage = this.describeApiError(error, 'Unable to sign in.');
      }
    });
  }

  protected generateBoard(): void {
    if (!this.ensureAuthenticated('Sign in before generating a board.')) {
      return;
    }
    this.loading = true;
    this.error = null;
    this.http.post<{ status: string }>(
      `${this.apiBase}/api/teams/${this.selectedTeamId}/board/generate?draft_year=${this.draftYear}`,
      {},
      this.requestOptions(true)
    ).subscribe({
      next: () => {
        this.boardMode = 'default';
        this.authMessage = 'Default board generated.';
        this.loadBoard();
      },
      error: (error: HttpErrorResponse) => {
        this.loading = false;
        this.error = this.describeApiError(error, 'Unable to generate the default board.');
      }
    });
  }

  protected copyBoard(): void {
    if (!this.ensureAuthenticated('Sign in before copying a personal board.')) {
      return;
    }
    this.loading = true;
    this.error = null;
    this.http.post<{ board_id: number; version: number }>(
      `${this.apiBase}/api/teams/${this.selectedTeamId}/board/copy?draft_year=${this.draftYear}`,
      {},
      this.requestOptions(true)
    ).subscribe({
      next: (response) => {
        this.boardMode = 'personal';
        this.boardId = response.board_id;
        this.boardVersion = response.version;
        this.authMessage = 'Personal board ready.';
        this.loadBoard();
      },
      error: (error: HttpErrorResponse) => {
        this.loading = false;
        this.error = this.describeApiError(error, 'Unable to copy the default board.');
      }
    });
  }

  protected selectEntry(entry: BoardEntry): void {
    this.activeEntry = entry;
  }

  protected saveBoard(): void {
    if (!this.ensureAuthenticated('Sign in before saving your personal board.')) {
      return;
    }
    if (this.boardMode !== 'personal' || this.boardId === null) {
      this.error = 'Copy the default board into My board before saving changes.';
      return;
    }
    this.error = null;
    this.http.put<{ version: number }>(
      `${this.apiBase}/api/teams/${this.selectedTeamId}/board/${this.boardId}/order`,
      { player_ids: this.entries.map((entry) => entry.player_id) },
      this.requestOptions(true)
    ).subscribe({
      next: (response) => {
        this.boardVersion = response.version;
        this.saved = true;
        this.authMessage = 'Personal board saved.';
        setTimeout(() => this.saved = false, 2200);
      },
      error: (error: HttpErrorResponse) => {
        this.error = this.describeApiError(error, 'Unable to save your board order.');
      }
    });
  }

  protected logout(): void {
    this.accessToken = '';
    this.favoriteTeamMessage = null;
    this.favoriteTeamId = '';
    this.preferredTeamId = null;
this.selectedTeamId = '';
this.overallRandomness = 50;
this.teamRandomnessOverrides = {};
this.draftRunMessage = null;
this.entries = [];
this.activeEntry = null;
    this.boardId = null;
    this.boardVersion = null;
    this.authMessage = 'Signed out.';
    if (this.boardMode === 'personal') {
      this.boardMode = 'default';
    }
    this.loadBoard();
  }

  protected saveFavoriteTeam(): void {
    if (!this.isAuthenticated || !this.favoriteTeamId || this.favoriteTeamId === this.preferredTeamId) {
      return;
    }

    this.savingFavoriteTeam = true;
    this.favoriteTeamMessage = null;
    this.http.patch<{ favorite_team_id: string }>(
      `${this.apiBase}/auth/me/favorite-team`,
      { favorite_team_id: this.favoriteTeamId },
      this.requestOptions(true)
    ).subscribe({
      next: (response) => {
        this.preferredTeamId = response.favorite_team_id;
        this.favoriteTeamId = response.favorite_team_id;
        this.selectedTeamId = response.favorite_team_id;
        this.boardMode = 'default';
        this.boardId = null;
        this.boardVersion = null;
        this.favoriteTeamMessage = 'Favorite team saved.';
        this.savingFavoriteTeam = false;
        this.loadBoard();
      },
      error: (error: HttpErrorResponse) => {
        this.savingFavoriteTeam = false;
        this.favoriteTeamMessage = this.describeApiError(error, 'Unable to update your favorite team.');
      }
    });
  }

  protected completeBoardAction(): void {
    if (this.boardMode === 'personal') {
      this.saveBoard();
      return;
    }
    if (this.entries.length > 0) {
      this.copyBoard();
      return;
    }
    this.generateBoard();
  }

  protected startMockDraft(): void {
    if (!this.ensureAuthenticated('Sign in before starting a mock draft.')) return;
    this.startingDraft = true;
    this.draftRunMessage = null;
    const overrides = this.teamRandomnessOverrides[this.selectedTeamId] === undefined
      ? {}
      : { [this.selectedTeamId]: this.teamRandomnessOverrides[this.selectedTeamId] };
    this.http.post<{ draft_run_id: string }>(
      `${this.apiBase}/api/drafts`,
      {
        controlled_team_id: this.selectedTeamId,
        draft_year: this.draftYear,
        overall_randomness: this.overallRandomness,
        randomness_overrides: overrides
      },
      this.requestOptions(true)
    ).subscribe({
      next: (response) => {
        this.startingDraft = false;
        this.draftRunMessage = `Mock draft ${response.draft_run_id} is ready with your randomness settings.`;
      },
      error: (error: HttpErrorResponse) => {
        this.startingDraft = false;
        this.draftRunMessage = this.describeApiError(error, 'Unable to start the mock draft.');
      }
    });
  }

  protected moveEntry(index: number, direction: -1 | 1): void {
    const target = index + direction;
    if (target < 0 || target >= this.entries.length) return;
    if (this.boardMode !== 'personal') return;
    const selectedPlayerId = this.activeEntry?.player_id ?? null;
    const next = [...this.entries];
    [next[index], next[target]] = [next[target], next[index]];
    this.entries = next.map((entry, position) => ({ ...entry, rank: position + 1 }));
    this.activeEntry = selectedPlayerId
      ? this.entries.find((entry) => entry.player_id === selectedPlayerId) ?? this.entries[target] ?? null
      : this.entries[target] ?? null;
  }

  private completeAuthentication(response: AuthResponse, message: string): void {
    this.accessToken = response.access_token;
    this.preferredTeamId = response.favorite_team_id;
    this.favoriteTeamId = response.favorite_team_id ?? '';
    this.favoriteTeamMessage = null;
    this.applyPreferredTeam();
    this.authMessage = `${message} Signed in as ${response.email}.`;
    this.authPassword = '';
    if (this.boardMode === 'personal') {
      this.loadBoard();
    }
  }

  private applyPreferredTeam(): void {
    const nextTeamId = this.preferredTeamId && this.teams.some((team) => team.id === this.preferredTeamId)
      ? this.preferredTeamId
      : this.selectedTeamId || this.teams[0]?.id;
    if (!nextTeamId) {
      return;
    }
    if (this.selectedTeamId === nextTeamId && this.entries.length) {
      return;
    }
    this.selectedTeamId = nextTeamId;
    this.boardMode = 'default';
    this.loadBoard();
  }

  private ensureAuthenticated(message: string): boolean {
    if (this.isAuthenticated) {
      return true;
    }
    this.error = message;
    return false;
  }

  private requestOptions(includeAuth: boolean): { headers?: Record<string, string> } {
    if (!includeAuth || !this.accessToken) {
      return {};
    }
    return {
      headers: {
        Authorization: `Bearer ${this.accessToken}`
      }
    };
  }

  private mapEntries(entries: TeamBoardEntryPayload[]): BoardEntry[] {
    return entries.map((entry, index) => {
      const breakdown = entry.score_breakdown ?? {};
      const name = [entry.first_name, entry.last_name].filter(Boolean).join(' ') || 'Unknown prospect';
      const needValue = Number(breakdown.need ?? breakdown.team_need ?? 0);
      const fitValue = Number(breakdown.fit ?? breakdown.team_fit ?? 0);
      return {
        rank: entry.rank_position ?? index + 1,
        player_id: entry.player_id,
        name,
        position: entry.position ?? 'N/A',
        school: entry.college_name ?? entry.college_abbreviation ?? 'N/A',
        score: Number(entry.score ?? 0),
        need: needValue,
        fit: fitValue,
        source: this.boardMode === 'personal' ? 'My board' : 'Default board'
      };
    });
  }

  private describeApiError(error: HttpErrorResponse, fallback: string): string {
    const detail = typeof error.error?.detail === 'string' ? error.error.detail : null;
    return detail ?? fallback;
  }
}