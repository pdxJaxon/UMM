import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, Input, OnDestroy, OnInit } from '@angular/core';
import { Subscription } from 'rxjs';

interface SnapshotSummary {
  id: string;
  collected_at: string;
  source_updated_at_display: string | null;
  source_url: string;
  prospect_count: number;
  scope: string;
}

interface ProspectReviewRow {
  player_id: string;
  name: string;
  school: string;
  source_position: string;
  canonical_position: string;
  overall_rank: number;
  previous_rank: number | null;
  rank_change: number | null;
  pff_grade: number | null;
  eligibility_status: string;
}

interface ProspectBoardReview {
  draft_year: number;
  snapshot: SnapshotSummary | null;
  previous_snapshot: SnapshotSummary | null;
  entries: ProspectReviewRow[];
}

@Component({
  selector: 'umm-prospect-review',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './prospect-review.component.html',
  styleUrl: './prospect-review.component.css'
})
export class ProspectReviewComponent implements OnInit, OnDestroy {
  @Input({ required: true }) apiBase = '';
  @Input({ required: true }) headers: Record<string, string> = {};
  @Input() draftYear = 2027;
  protected review: ProspectBoardReview | null = null;
  protected loading = false;
  protected error: string | null = null;
  private request?: Subscription;

  constructor(private readonly http: HttpClient) {}

  ngOnInit(): void {
    this.load();
  }

  ngOnDestroy(): void {
    this.request?.unsubscribe();
  }

  protected load(): void {
    this.request?.unsubscribe();
    this.loading = true;
    this.error = null;
    this.review = null;
    this.request = this.http.get<ProspectBoardReview>(
      `${this.apiBase}/api/prospect-boards/pff/latest`,
      { headers: this.headers, params: { draft_year: this.draftYear } }
    ).subscribe({
      next: review => {
        this.review = review;
        this.loading = false;
      },
      error: () => {
        this.error = 'Unable to load prospect snapshots. Check your connection and sign-in, then retry.';
        this.loading = false;
      }
    });
  }

  protected movement(row: ProspectReviewRow): string {
    if (!this.review?.previous_snapshot) return 'No comparison';
    if (row.rank_change === null) return 'New to snapshot';
    if (row.rank_change > 0) return `Up ${row.rank_change}`;
    if (row.rank_change < 0) return `Down ${Math.abs(row.rank_change)}`;
    return 'Unchanged';
  }
}
