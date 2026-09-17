import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule } from '@angular/common/http';

interface TeamOption {
  id: string;
  name: string;
  abbreviation: string;
}

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

interface TeamBoardResponse {
  team_id: string;
  draft_year: number;
  entries: TeamBoardEntryPayload[];
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
  protected activeEntry: BoardEntry | null = null;
  protected saved = false;
  protected entries: BoardEntry[] = [];
  protected loading = false;
  protected error: string | null = null;

  private readonly draftYear = 2027;

  constructor(private readonly http: HttpClient) {}

  ngOnInit(): void {
    this.http.get<TeamOption[]>('http://localhost:8000/api/teams').subscribe({
      next: (teams) => {
        this.teams = teams;
        if (teams.length > 0) {
          this.selectedTeamId = teams[0].id;
          this.loadBoard();
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

  protected onTeamChange(): void {
    this.loadBoard();
  }

  protected loadBoard(): void {
    if (!this.selectedTeamId) {
      this.entries = [];
      this.activeEntry = null;
      return;
    }

    this.loading = true;
    this.error = null;

    this.http
      .get<TeamBoardResponse>(`http://localhost:8000/api/teams/${this.selectedTeamId}/board?draft_year=${this.draftYear}`)
      .subscribe({
        next: (response) => {
          this.entries = (response.entries ?? []).map((entry, index) => {
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
              source: 'API'
            };
          });
          this.loading = false;
          this.activeEntry = this.entries[0] ?? null;
        },
        error: () => {
          this.loading = false;
          this.entries = [];
          this.activeEntry = null;
          this.error = 'No board is available yet for this team.';
        }
      });
  }

  protected selectEntry(entry: BoardEntry): void {
    this.activeEntry = entry;
  }

  protected saveBoard(): void {
    this.saved = true;
    setTimeout(() => this.saved = false, 2200);
  }

  protected moveEntry(index: number, direction: -1 | 1): void {
    const target = index + direction;
    if (target < 0 || target >= this.entries.length) return;
    const next = [...this.entries];
    [next[index], next[target]] = [next[target], next[index]];
    this.entries = next.map((entry, position) => ({ ...entry, rank: position + 1 }));
    this.activeEntry = this.entries[index] ?? null;
  }
}