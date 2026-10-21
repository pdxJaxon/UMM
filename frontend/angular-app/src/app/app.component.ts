import { CommonModule } from '@angular/common';
import { AfterViewChecked, Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule, HttpErrorResponse } from '@angular/common/http';

interface TeamOption {
  id: string;
  name: string;
  abbreviation: string;
  logo_url: string;
  randomness_score: number;
  draft_order_basis?: string;
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
  schoolLogoUrl: string | null;
  score: number;
  need: number;
  fit: number;
  source: string;
  projected?: boolean;
  sourceRank?: number | null;
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
  college_logo_url?: string | null;
  is_projected?: boolean;
  source_rank?: number | null;
  source_name?: string | null;
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

interface DraftPlayerPayload {
  player_id: string;
  first_name: string;
  last_name: string;
  position: string;
  college_name: string | null;
  college_abbreviation: string | null;
  college_logo_url?: string | null;
  is_projected?: boolean;
  source_rank?: number | null;
}

interface StartDraftResponse {
  draft_run_id: string;
  eligible_players: DraftPlayerPayload[];
}

interface DraftStateResponse {
  draft_run: {
    id: string;
    controlled_team_id: string;
    season_year: number;
    status: string;
    draft_order: string[];
    order_basis?: string;
  };
  current_pick_number: number;
  current_team_id: string;
  picks: Array<{
    id: string;
    pick_number: number;
    team_id: string;
    player_id: string;
    selection_source: string;
    prediction_metadata: Record<string, unknown>;
  }>;
  trades: Array<{
    id: string;
    pick_number: number;
    moving_up_team_id: string;
    moving_down_team_id: string;
  }>;
}

interface AuthResponse {
  id: string;
  email: string;
  access_token: string;
  token_type: string;
  favorite_team_id: string | null;
}

interface DataStatusResponse {
  updated_on: string | null;
}

interface RecommendationCandidate {
  player_id: string;
  name: string;
  rank: number;
  position: string;
  college_name: string | null;
  source_rank: number | null;
  is_projected: boolean;
}

interface DraftRecommendation {
  draft_run_id: string;
  team_id: string;
  pick_number: number;
  recommended: RecommendationCandidate;
  alternatives: RecommendationCandidate[];
  confidence: number;
  reasoning_factors: string[];
  evidence: string[];
  provider: string;
  model: string;
  rank_basis: string;
}

@Component({
  selector: 'umm-root',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('draftPickList') private draftPickList?: ElementRef<HTMLOListElement>;
  private visiblePickCount = 0;
  protected teams: TeamOption[] = [];
  protected selectedTeamId = '';
  protected boardMode: 'default' | 'personal' = 'default';
  protected authMode: 'login' | 'register' = 'login';
  protected activeEntry: BoardEntry | null = null;
  protected saved = false;
  protected savingBoard = false;
  protected boardDirty = false;
  protected boardSaveFailed = false;
  protected entries: BoardEntry[] = [];
  protected loading = false;
  protected confirmingBoardCopy = false;
  protected error: string | null = null;
  protected authMessage: string | null = null;
  protected signedInEmail = '';
  protected dataUpdatedOn: string | null = null;
  protected dataDateError = false;
  protected dataDateLoading = true;
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
  protected draftState: DraftStateResponse | null = null;
  protected draftEntries: BoardEntry[] = [];
  protected draftId: string | null = null;
  protected draftError: string | null = null;
  protected draftBusy = false;
  protected draftSelectedPlayerId = '';
  protected recommendation: DraftRecommendation | null = null;
  protected recommendationLoading = false;
  protected recommendationError: string | null = null;
  protected recommendationNotice: string | null = null;
  private recommendationRequest = 0;
  private draftAdvanceRequest = 0;
  private draftPickTimer: ReturnType<typeof setTimeout> | null = null;
  protected draftPickDelayMs: 1000 | 2000 | 3000 = 2000;
  protected readonly draftSpeeds = [
    { label: 'Slow', delayMs: 3000 },
    { label: 'Medium', delayMs: 2000 },
    { label: 'Fast', delayMs: 1000 }
  ] as const;
  protected readonly failedDraftTeamLogos = new Set<string>();
  private draggedPlayerId: string | null = null;

  private readonly apiBase = 'http://localhost:8000';
  private accessToken = '';
  private authSession = 0;
  private boardId: number | null = null;
  private boardRequest = 0;
  private readonly draftYear = 2027;

  constructor(private readonly http: HttpClient) {}

  ngAfterViewChecked(): void {
    const count = this.draftState?.picks.length ?? 0;
    if (count !== this.visiblePickCount && this.draftPickList) {
      const list = this.draftPickList.nativeElement;
      list.scrollTop = list.scrollHeight;
    }
    this.visiblePickCount = count;
  }

  ngOnDestroy(): void {
    this.cancelDraftAdvance();
    this.clearRecommendation();
    this.authSession += 1;
  }

  ngOnInit(): void {
    this.http.get<DataStatusResponse>(`${this.apiBase}/api/data/status`).subscribe({
      next: (response) => {
        this.dataUpdatedOn = response.updated_on;
        this.dataDateError = false;
        this.dataDateLoading = false;
      },
      error: () => {
        this.dataUpdatedOn = null;
        this.dataDateError = true;
        this.dataDateLoading = false;
      }
    });
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

  protected get draftOrderLabel(): string {
    const basis = this.draftState?.draft_run.order_basis
      ?? this.teams.find((team) => team.id === this.selectedTeamId)?.draft_order_basis;
    return basis === 'projected-one-pick-per-team'
      ? 'Projected draft order - one pick per team; traded ownership is not modeled.'
      : 'Sample/unreviewed draft order - not the official NFL order.';
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

  protected get draftCandidates(): BoardEntry[] {
    const selectedPlayers = new Set(this.draftState?.picks.map((pick) => pick.player_id) ?? []);
    return this.draftEntries.filter((entry) => !selectedPlayers.has(entry.player_id));
  }

  protected get draftOnControlledTeam(): boolean {
    return !!this.draftState
      && this.draftState.draft_run.status === 'drafting'
      && this.draftState.current_team_id === this.draftState.draft_run.controlled_team_id;
  }

  protected get currentDraftTeamName(): string {
    return this.teamName(this.draftState?.current_team_id ?? '');
  }

  protected teamName(teamId: string): string {
    const team = this.teams.find((candidate) => candidate.id === teamId);
    return team?.name ?? teamId;
  }

  protected draftTeamLogo(teamId: string): string | null {
    if (this.failedDraftTeamLogos.has(teamId)) return null;
    return this.teams.find((team) => team.id === teamId)?.logo_url || null;
  }

  protected setDraftSpeed(delayMs: 1000 | 2000 | 3000): void {
    this.draftPickDelayMs = delayMs;
    if (this.draftPickTimer !== null && this.draftState) {
      this.cancelDraftAdvance();
      this.continueDraft(this.draftState);
    }
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
    return this.isAuthenticated ? (this.loading ? 'Loading board...' : 'Board unavailable') : 'Guest mode';
  }

  protected get boardActionLabel(): string {
    if (this.boardMode === 'personal') {
      if (!this.canSaveBoard) return 'Copy to edit';
      if (this.savingBoard) return 'Saving...';
      if (this.boardSaveFailed) return 'Retry save';
      return this.saved ? 'Saved automatically' : 'Changes auto-save';
    }
    return this.entries.length > 0 ? 'Copy to My board' : 'Generate default board';
  }

  protected get boardActionEnabled(): boolean {
    if (this.loading || this.confirmingBoardCopy) return false;
    if (this.boardMode === 'personal') {
      return this.canSaveBoard && this.boardDirty && this.boardSaveFailed && !this.savingBoard;
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
    const request = ++this.boardRequest;
    this.confirmingBoardCopy = false;
    this.saved = false;
    this.savingBoard = false;
    this.boardDirty = false;
    this.boardSaveFailed = false;
    if (!this.selectedTeamId) {
      this.loading = false;
      this.entries = [];
      this.activeEntry = null;
      return;
    }

    if (this.boardMode === 'personal' && !this.isAuthenticated) {
      this.loading = false;
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
          if (request !== this.boardRequest) return;
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
          if (request !== this.boardRequest) return;
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
        this.completeAuthentication(response);
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

  protected copyBoard(replaceExisting = false): void {
    if (this.loading || this.draftId || !this.selectedTeamId) return;
    if (replaceExisting && !this.confirmingBoardCopy) return;
    if (!this.ensureAuthenticated('Sign in before copying a personal board.')) {
      return;
    }
    const request = ++this.boardRequest;
    this.confirmingBoardCopy = false;
    this.loading = true;
    this.error = null;
    this.http.post<{ board_id: number; version: number }>(
      `${this.apiBase}/api/teams/${this.selectedTeamId}/board/copy?draft_year=${this.draftYear}&replace_existing=${replaceExisting}`,
      {},
      this.requestOptions(true)
    ).subscribe({
      next: (response) => {
        if (request !== this.boardRequest) return;
        this.boardMode = 'personal';
        this.boardId = response.board_id;
        this.boardVersion = response.version;
        this.authMessage = 'Default prospects copied to your personal board.';
        this.loadBoard();
      },
      error: (error: HttpErrorResponse) => {
        if (request !== this.boardRequest) return;
        this.loading = false;
        if (error.status === 409 && !replaceExisting) {
          this.confirmingBoardCopy = true;
          return;
        }
        this.error = this.describeApiError(error, 'Unable to copy the default board.');
      }
    });
  }

  protected cancelBoardCopy(): void {
    this.confirmingBoardCopy = false;
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
    if (this.savingBoard) return;
    this.boardDirty = true;
    this.saved = false;
    this.boardSaveFailed = false;
    this.error = null;
    const boardId = this.boardId;
    const teamId = this.selectedTeamId;
    const authSession = this.authSession;
    const playerIds = this.entries.map((entry) => entry.player_id);
    this.savingBoard = true;
    this.http.put<{ version: number }>(
    `${this.apiBase}/api/teams/${teamId}/board/${boardId}/order`,
    { player_ids: playerIds },
    this.requestOptions(true)
    ).subscribe({
      next: (response) => {
        if (
          this.boardId !== boardId
          || this.selectedTeamId !== teamId
          || this.boardMode !== 'personal'
          || this.authSession !== authSession
        ) return;
        this.savingBoard = false;
        this.boardVersion = response.version;
        const latestPlayerIds = this.entries.map((entry) => entry.player_id);
        if (playerIds.length !== latestPlayerIds.length || playerIds.some((id, index) => id !== latestPlayerIds[index])) {
          this.saveBoard();
          return;
        }
        this.boardDirty = false;
        this.boardSaveFailed = false;
        this.saved = true;
      },
      error: (error: HttpErrorResponse) => {
        if (
          this.boardId !== boardId
          || this.selectedTeamId !== teamId
          || this.boardMode !== 'personal'
          || this.authSession !== authSession
        ) return;
        this.savingBoard = false;
        this.boardSaveFailed = true;
        this.error = this.describeApiError(error, 'Unable to save your board order.');
      }
    });
  }

  protected logout(): void {
    if (this.boardDirty || this.savingBoard) {
      this.error = 'Save your personal board changes before signing out.';
      return;
    }
    this.cancelDraftAdvance();
    this.clearRecommendation();
    this.authSession += 1;
    this.accessToken = '';
    this.signedInEmail = '';
    this.favoriteTeamMessage = null;
    this.favoriteTeamId = '';
    this.preferredTeamId = null;
this.selectedTeamId = '';
this.overallRandomness = 50;
this.teamRandomnessOverrides = {};
this.draftRunMessage = null;
    this.startingDraft = false;
  this.draftState = null;
    this.draftEntries = [];
    this.draftId = null;
  this.draftError = null;
  this.draftBusy = false;
  this.draftSelectedPlayerId = '';
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
    if (
      !this.isAuthenticated || !this.favoriteTeamId || this.favoriteTeamId === this.preferredTeamId
      || this.boardDirty || this.savingBoard
    ) {
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
    if (!this.entries.length) {
      this.draftRunMessage = 'Generate or load a team board before starting a mock draft.';
      return;
    }
    this.startingDraft = true;
    this.draftRunMessage = null;
    this.draftError = null;
    this.draftEntries = [];
    const boardEntries = [...this.entries];
    const overrides = { ...this.teamRandomnessOverrides };
    const authSession = this.authSession;
    this.http.post<StartDraftResponse>(
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
        if (authSession !== this.authSession) return;
        this.startingDraft = false;
        this.draftId = response.draft_run_id;
        this.draftEntries = this.mapDraftEntries(response.eligible_players, boardEntries);
        this.draftRunMessage = `Mock draft ${response.draft_run_id} started.`;
        this.advanceDraft(response.draft_run_id);
      },
      error: (error: HttpErrorResponse) => {
        if (authSession !== this.authSession) return;
        this.startingDraft = false;
        this.draftId = null;
        this.draftRunMessage = this.describeApiError(error, 'Unable to start the mock draft.');
      }
    });
  }

  protected submitDraftPick(): void {
    const state = this.draftState;
    if (!state || !this.draftOnControlledTeam || !this.draftSelectedPlayerId || this.draftBusy) return;

    this.clearRecommendation();
    this.draftBusy = true;
    this.draftError = null;
    const authSession = this.authSession;
    this.http.post<DraftStateResponse>(
      `${this.apiBase}/api/drafts/${state.draft_run.id}/picks`,
      { team_id: state.draft_run.controlled_team_id, player_id: this.draftSelectedPlayerId },
      this.requestOptions(true)
    ).subscribe({
      next: (updatedState) => {
        if (authSession !== this.authSession) return;
        this.setDraftState(updatedState);
        this.continueDraft(updatedState);
      },
      error: (error: HttpErrorResponse) => {
        if (authSession !== this.authSession) return;
        this.draftBusy = false;
        this.draftError = this.describeApiError(error, 'Unable to submit your pick.');
        this.loadRecommendation();
      }
    });
  }

  protected simulateToUserPick(): void {
    const draftId = this.draftState?.draft_run.id ?? this.draftId;
    if (!draftId || this.draftBusy) return;
    this.advanceDraft(draftId);
  }

  protected closeDraft(): void {
    if (this.draftState?.draft_run.status !== 'completed') return;
    this.cancelDraftAdvance();
    this.clearRecommendation();
    this.draftState = null;
    this.draftEntries = [];
    this.draftId = null;
    this.draftError = null;
    this.draftSelectedPlayerId = '';
    this.draftRunMessage = null;
  }

  protected draftPlayerName(playerId: string): string {
    return this.draftEntries.find((entry) => entry.player_id === playerId)?.name ?? playerId;
  }

  protected draftPlayerDetails(playerId: string): BoardEntry | undefined {
    return this.draftEntries.find((entry) => entry.player_id === playerId);
  }

  private cancelDraftAdvance(): void {
    this.draftAdvanceRequest += 1;
    if (this.draftPickTimer !== null) {
      clearTimeout(this.draftPickTimer);
      this.draftPickTimer = null;
    }
  }

  private continueDraft(state: DraftStateResponse): void {
    this.draftBusy = false;
    if (state.draft_run.status === 'completed') return;
    if (state.current_team_id === state.draft_run.controlled_team_id) {
      this.loadRecommendation();
      return;
    }
    this.draftBusy = true;
    const request = this.draftAdvanceRequest;
    const authSession = this.authSession;
    this.draftPickTimer = setTimeout(() => {
      this.draftPickTimer = null;
      if (request !== this.draftAdvanceRequest || authSession !== this.authSession
        || this.draftId !== state.draft_run.id) return;
      this.advanceDraft(state.draft_run.id);
    }, this.draftPickDelayMs);
  }

  private advanceDraft(draftId: string): void {
    this.cancelDraftAdvance();
    this.clearRecommendation();
    this.draftBusy = true;
    this.draftError = null;
    const authSession = this.authSession;
    const request = this.draftAdvanceRequest;
    this.http.post<DraftStateResponse>(
      `${this.apiBase}/api/drafts/${draftId}/auto-simulate?max_picks=1`,
      {},
      this.requestOptions(true)
    ).subscribe({
      next: (state) => {
        if (authSession !== this.authSession || request !== this.draftAdvanceRequest) return;
        this.setDraftState(state);
        this.continueDraft(state);
      },
      error: (error: HttpErrorResponse) => {
        if (authSession !== this.authSession || request !== this.draftAdvanceRequest) return;
        this.draftBusy = false;
        this.draftError = this.describeApiError(error, 'Unable to advance the draft.');
      }
    });
  }

  private setDraftState(state: DraftStateResponse): void {
    this.clearRecommendation();
    this.draftState = state;
    this.draftId = state.draft_run.id;
    const available = this.draftEntries.filter((entry) => !state.picks.some((pick) => pick.player_id === entry.player_id));
    if (!available.some((entry) => entry.player_id === this.draftSelectedPlayerId)) {
      this.draftSelectedPlayerId = available[0]?.player_id ?? '';
    }
  }

  protected loadRecommendation(): void {
    this.clearRecommendation();
    const state = this.draftState;
    if (!state || !this.draftOnControlledTeam || this.draftBusy) return;
    if (!this.draftCandidates.length) {
      this.recommendationError = 'No available prospects remain for a recommendation.';
      return;
    }
    const request = this.recommendationRequest;
    const authSession = this.authSession;
    const pickNumber = state.current_pick_number;
    this.recommendationLoading = true;
    this.http.post<DraftRecommendation>(
      `${this.apiBase}/api/drafts/${state.draft_run.id}/recommendation`, {}, this.requestOptions(true)
    ).subscribe({
      next: (result) => {
        if (request !== this.recommendationRequest || authSession !== this.authSession) return;
        this.recommendationLoading = false;
        const current = this.draftState;
        const available = new Set(this.draftCandidates.map((candidate) => candidate.player_id));
        if (!current || !this.draftOnControlledTeam
          || current.draft_run.id !== result.draft_run_id
          || current.current_pick_number !== pickNumber || result.pick_number !== pickNumber
          || result.team_id !== current.current_team_id
          || !available.has(result.recommended.player_id)
          || result.alternatives.some((candidate) => !available.has(candidate.player_id))) {
          this.recommendationError = 'The recommendation is no longer current. Request a fresh recommendation.';
          return;
        }
        this.recommendation = result;
      },
      error: (error: HttpErrorResponse) => {
        if (request !== this.recommendationRequest || authSession !== this.authSession) return;
        this.recommendationLoading = false;
        if (error.status === 503 && error.error?.detail?.code === 'recommendation_not_configured') {
          this.recommendationNotice = 'AI recommendations are not enabled yet. You can still select a prospect and make your pick.';
          return;
        }
        this.recommendationError = this.describeApiError(error, 'Unable to load the AI recommendation. You can still choose your own prospect.');
      }
    });
  }

  protected chooseRecommendation(playerId: string): void {
    if (!this.draftOnControlledTeam || this.draftBusy) return;
    if (this.draftCandidates.some((candidate) => candidate.player_id === playerId)) {
      this.draftSelectedPlayerId = playerId;
    }
  }

  private clearRecommendation(): void {
    this.recommendationRequest += 1;
    this.recommendation = null;
    this.recommendationError = null;
    this.recommendationNotice = null;
    this.recommendationLoading = false;
  }

  protected moveEntry(index: number, direction: -1 | 1): void {
    this.reorderEntries(index, index + direction);
  }

  protected startEntryDrag(event: DragEvent, entry: BoardEntry): void {
    if (this.boardMode !== 'personal' || this.draftId) {
      event.preventDefault();
      return;
    }
    this.draggedPlayerId = entry.player_id;
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', entry.player_id);
    }
  }

  protected allowEntryDrop(event: DragEvent): void {
    if (this.boardMode !== 'personal' || this.draftId || !this.draggedPlayerId) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
  }

  protected dropEntry(event: DragEvent, targetIndex: number): void {
    event.preventDefault();
    const playerId = this.draggedPlayerId;
    this.draggedPlayerId = null;
    if (this.boardMode !== 'personal' || this.draftId || !playerId) return;
    const sourceIndex = this.entries.findIndex((entry) => entry.player_id === playerId);
    this.reorderEntries(sourceIndex, targetIndex);
  }

  protected endEntryDrag(): void {
    this.draggedPlayerId = null;
  }

  private reorderEntries(sourceIndex: number, targetIndex: number): void {
    if (this.boardMode !== 'personal' || this.draftId) return;
    if (sourceIndex < 0 || sourceIndex >= this.entries.length) return;
    if (targetIndex < 0 || targetIndex >= this.entries.length || sourceIndex === targetIndex) return;
    const selectedPlayerId = this.activeEntry?.player_id ?? null;
    const next = [...this.entries];
    const [movedEntry] = next.splice(sourceIndex, 1);
    next.splice(targetIndex, 0, movedEntry);
    this.entries = next.map((entry, position) => ({ ...entry, rank: position + 1 }));
    this.activeEntry = selectedPlayerId
      ? this.entries.find((entry) => entry.player_id === selectedPlayerId) ?? this.entries[targetIndex] ?? null
      : this.entries[targetIndex] ?? null;
    this.boardDirty = true;
    this.saved = false;
    this.boardSaveFailed = false;
    this.error = null;
    this.saveBoard();
  }

  private completeAuthentication(response: AuthResponse, message: string | null = null): void {
    this.accessToken = response.access_token;
    this.preferredTeamId = response.favorite_team_id;
    this.favoriteTeamId = response.favorite_team_id ?? '';
    this.favoriteTeamMessage = null;
    this.applyPreferredTeam();
    this.signedInEmail = response.email;
    this.authMessage = message;
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
        schoolLogoUrl: entry.college_logo_url || null,
        score: Number(entry.score ?? 0),
        need: needValue,
        fit: fitValue,
        source: entry.source_name ?? (this.boardMode === 'personal' ? 'My board' : 'Default board'),
        projected: entry.is_projected ?? false,
        sourceRank: entry.source_rank ?? null
      };
    });
  }

  private mapDraftEntries(players: DraftPlayerPayload[], boardEntries: BoardEntry[]): BoardEntry[] {
    const playersById = new Map(players.map((player) => [player.player_id, player]));
    const preferredEntries = boardEntries
      .filter((entry) => playersById.has(entry.player_id))
      .map((entry, index) => ({
        ...entry, rank: index + 1, source: 'Draft board',
        position: playersById.get(entry.player_id)?.position || entry.position,
        school: playersById.get(entry.player_id)?.college_name
          ?? playersById.get(entry.player_id)?.college_abbreviation ?? entry.school,
        schoolLogoUrl: playersById.get(entry.player_id)?.college_logo_url ?? entry.schoolLogoUrl,
        projected: playersById.get(entry.player_id)?.is_projected ?? false,
        sourceRank: playersById.get(entry.player_id)?.source_rank ?? null
      }));
    const preferredIds = new Set(preferredEntries.map((entry) => entry.player_id));
    const additionalEntries = players
      .filter((player) => !preferredIds.has(player.player_id))
      .map((player, index) => ({
        rank: preferredEntries.length + index + 1,
        player_id: player.player_id,
        name: [player.first_name, player.last_name].filter(Boolean).join(' ') || 'Unknown prospect',
        position: player.position || 'N/A',
        school: player.college_name ?? player.college_abbreviation ?? 'N/A',
        schoolLogoUrl: player.college_logo_url || null,
        score: 0,
        need: 0,
        fit: 0,
        source: 'Draft pool',
        projected: player.is_projected ?? false,
        sourceRank: player.source_rank ?? null
      }));
    return [...preferredEntries, ...additionalEntries];
  }

  private describeApiError(error: HttpErrorResponse, fallback: string): string {
    const detail = typeof error.error?.detail === 'string' ? error.error.detail : null;
    return detail ?? fallback;
  }
}