# Historical Backtest Datasets

These parquet snapshots support offline historical draft backtests. They are sourced from the nflverse-data GitHub releases and are intentionally tracked so results can be reproduced without network access.

| File | Source | SHA-256 |
| --- | --- | --- |
| `combine.parquet` | https://github.com/nflverse/nflverse-data/releases/download/combine/combine.parquet | `1B6C48A0B56E515B043DD678EA38A2E6AE83CB9DE488E6A0A89F8B2F980BF2CF` |
| `draft_picks.parquet` | https://github.com/nflverse/nflverse-data/releases/download/draft_picks/draft_picks.parquet | `C2FA5465989CBAC5721360F32ACA4D67AEFECCF2DD9A5F659B4D799AB2A77F9E` |
| `players.parquet` | https://github.com/nflverse/nflverse-data/releases/download/players/players.parquet | `39521DA386F322E0484D93E6E4AC4D294A710EBCF24799D01DA8F15DFDC4228A` |

Run the 2024 offline pilot from `backend`:

```powershell
python -m app.jobs.run_historical_backtest --start-season 2024 --end-season 2024 --draft-picks-file ..\data\draft_picks.parquet --combine-file ..\data\combine.parquet --players-file ..\data\players.parquet
```

The pilot reports outcomes missing from the prospect snapshot as
`unmatched_actuals`. These outcomes are excluded from scoring and deterministic
replay: they do not consume a candidate or renumber later picks. This is a
partial-coverage evaluation, not a simulation of the full draft.

Aggregate `mean_absolute_pick_error` divides the total absolute pick error by
the total number of matched players across all teams and seasons. Per-team
scorecards include `total_absolute_pick_error` so aggregation does not average
rounded team means. If no players match, the mean is `null`, not zero.

## Historical trade and leadership imports

From `backend`, import a JSON or CSV ownership history and optional leadership
file:

```powershell
python -m app.jobs.refresh_trade_history --start-season 2023 --end-season 2024 --trade-history-file path\to\trades.json --leadership-file path\to\leadership.json
```

Trade rows require a season (`season` or `draft_year`), a pick number (`pick` or
`pick_number`), and explicit original and selecting teams (`original_team` and
`team`, or `original_team_id` and `team_id`). File imports retain a
`file:<filename>` source label. Team abbreviations and canonical IDs are
case-insensitive; equivalent aliases of the same team are not trades.
Leadership rows accept those same team tokens, a `role` of `gm` or `head_coach`,
a `person_id`, and a `start_year`.

## Reviewed team needs and projected draft order

The reference seed's alphabetical order is sample data, not an NFL projection.
New draft runs use a reviewed year-specific order when one exists. This pilot
supports exactly one first-round pick per team, not traded pick ownership.
Published order metadata and the draft room distinguish reviewed projections
from sample/unreviewed order; neither is labeled official.

### Prepare and review the input

Use dated sources for both order and all 32 teams' needs. Record analyst judgments
as judgments: a numeric need score is a reviewed assessment, not a fact that can
be inferred directly from a standings table. Verify team identities, ties and
projection methodology, roster changes, source dates, and the rationale behind
each position/role assessment. Do not copy a traded-owner draft order into this
one-pick-per-team projection.

Public starting points include [NFL standings](https://www.nfl.com/standings/)
and [Tankathon](https://www.tankathon.com/nfl), but these pages are not imported
automatically and their listing does not certify a current 2027 projection.
Keep reviewed input manifests locally; never apply fabricated example needs or
assume that a current web page represents an earlier review date.

From `backend`, print the complete JSON schema:

```powershell
..\.venv\Scripts\python.exe -m app.jobs.import_league_refresh --schema
```

The JSON object must contain:

- `draft_year`, `reviewed_on` (`YYYY-MM-DD`), and nonempty `reviewed_by`.
- `prospect_snapshot_id`: the latest explicitly approved snapshot for that year.
- `order_basis`: exactly `projected-one-pick-per-team`.
- `order_source`: `name`, HTTP(S) `url`, and `observed_on`.
- `draft_order`: exactly 32 unique canonical IDs (`team-1` through `team-32`),
  arranged in projected pick order.
- `team_needs`: exactly one object per canonical team, containing `team_id`,
  `source` (same fields as `order_source`), and a nonempty `needs` list.
- Each need: canonical `position_code`, `role_level`, `need_score` (0-100),
  integer `quantity` (1-10), and nonempty `rationale`. Repeated position/role
  pairs within a team are rejected. Use an explicit zero-score assessment when
  review finds no need for a listed role; do not invent a need merely to fill a
  required list.

Sources cannot be dated after review; future review dates, unknown teams or
positions, incomplete team coverage, and unapproved prospect snapshots fail
before writes. The importer does not independently verify a source's claims:
operator review is required.

### Preview, then apply

Back up the database first. For PostgreSQL, apply migrations through
`023_add_league_data_refreshes.sql`. For SQLite, run the schema-only initializer
shown in the prospect workflow below; do not reseed an existing database.

```powershell
..\.venv\Scripts\python.exe -m app.jobs.import_league_refresh --manifest C:\path\to\reviewed-2027.json
..\.venv\Scripts\python.exe -m app.jobs.import_league_refresh --manifest C:\path\to\reviewed-2027.json --commit
```

Preview validates and reports without changing records. Apply deactivates
previous active needs for that draft year (retaining history), adds sourced
assessments, stores the reviewed manifest under its content hash, and creates 32
new default-board versions at each team's projected pick position. All changes
are transactional: generation failure publishes none of that refresh. Reapplying
identical current input is a no-op. Changed input requires a later review date;
older refreshes cannot be replayed over newer ones.

Existing personal boards, prospect identities/eligibility, draft picks, and
pinned draft orders stay unchanged. Other years' needs and order stay separate.
The original team seed order is not overwritten. Regeneration does not update
personal copies.

### Complete the full refresh deliberately

After importing, verify the projected order and active needs through
`GET /api/teams?draft_year=2027` and each team's needs endpoint. Review the new
default boards, then exercise a complete first round in an isolated database.
Only after prospects, team needs, order, and generated outputs have all been
reviewed should you record `DATA_UPDATED_ON` and restart the API.

The import never advances the homepage's full-refresh date automatically.
Projection status is not a claim that the eventual NFL order is known.

## PFF CSV imports and projected pools

The authorized PFF export is the candidate-list source going forward. The old
consensus adapter remains available only for historical/manual compatibility.
Do not run the legacy NFLverse prospect-refresh job as a replacement for this
inbox workflow: detailed prospect enrichment is separate.

Importing rankings and approving them for simulation are separate operations.
Only members of an explicitly approved snapshot become available as projected
prospects. Approval does not confirm eligibility or declaration.

Before updating an existing database, take a backup. For PostgreSQL, apply
migrations through `023_add_league_data_refreshes.sql` using the deployment
migration process. For local SQLite, run the schema-only upgrade from `backend`
to preserve existing reference data:

```powershell
Set-Location C:\Users\s008919\git\UMM\backend
..\.venv\Scripts\python.exe -c "from app.db.initialize import initialize_schema; initialize_schema()"
```

The CSV must have exactly
`Rank,Player,Position,School,PFF Grade,Analysis` headers in that order, unique
consecutive ranks starting at 1, and unique name/school identities. Standard CSV
quoting, UTF-8 BOMs, commas, and multiline analysis fields are supported.
Grades can be blank; supplied grades must be finite numbers from 0 to 100.
PFF grades are stored as source snapshot evidence, not athletic measurements or
UMM scoring inputs. Narrative `Analysis` is not imported or used for enrichment.
Profiles, measurements, and detailed scouting information require other sources.

Keep exports in the ignored `data\prospects` directory, named
`pff-my-big-board-YYYY-MM-DD.csv`. Use one inbox per draft year: the file does not
contain a draft-year column, so the operator must verify the year and pass it
explicitly. The date is the export's source date, not a filesystem timestamp.
Copy to a temporary filename outside the matching pattern and rename only when
the file is complete. The job reads and validates the newest dated file only;
it never falls back to older data when the newest input is invalid.

From `backend`, preview the inbox, then import:

```powershell
..\.venv\Scripts\python.exe -m app.jobs.import_pff_csv --directory ..\data\prospects --draft-year 2027
..\.venv\Scripts\python.exe -m app.jobs.import_pff_csv --directory ..\data\prospects --draft-year 2027 --commit
```

The default minimum is 150 candidates to reject truncated files. All rows are
imported, not just the first 150. Change `--min-prospects` only after reviewing an
intentional scope change. For an explicitly chosen file instead, use
`--csv PATH --snapshot-date YYYY-MM-DD` without `--directory`.

Reprocessing identical dated candidate data is a no-op. Older snapshots are
skipped. Changed data for an already imported date is rejected for manual
correction review. A later date with unchanged candidates is still a new dated
snapshot. Changing only narrative analysis does not create another snapshot.
Missing/empty inboxes, future dates, malformed CSVs, unmapped schools/positions,
and unresolved identities are explicit failures with a nonzero exit code.
Imports never delete omitted players, approve a pool, regenerate default boards,
or advance `DATA_UPDATED_ON`.

Identity conflicts require a reviewed JSON object mapping source keys to existing
player IDs via `--identity-map PATH`. This preserves stored profiles and records
the export's school/position on its ranking rows. Do not automatically accept
school changes or fuzzy name matches. Keep database-specific maps local, not in
Git. Review maps if a previously overridden prospect disappears from the file.

### Nightly local job

From the repository root, the PowerShell wrapper defaults to preview:

```powershell
.\scripts\import-pff-prospects.ps1 -DraftYear 2027
.\scripts\import-pff-prospects.ps1 -DraftYear 2027 -Commit
```

It uses the project's `.venv` and the absolute inbox path, so Task Scheduler's
working directory does not affect the database or input selection. If present,
`data\prospects\pff-identity-map-2027.json` is used automatically; alternatively
pass `-IdentityMap PATH`. A direct Python CLI invocation requires the explicit
`--identity-map` argument when overrides are needed.

Register the nightly task explicitly (default: 02:00 local machine time):

```powershell
.\scripts\register-pff-nightly.ps1 -DraftYear 2027 -At '02:00'
Get-ScheduledTaskInfo -TaskName 'UMM-PFF-Candidate-Import'
```

Registration does not overwrite an existing named task. It uses the current
Windows account's default interactive task context: keep that account signed in
and the machine available. Overlapping task invocations are ignored; missed runs
start when available. For unattended execution while logged out, configure a
dedicated scheduler account and database access separately; never put credentials
in scripts. Check Task Scheduler's last result/history for nonzero failures
and timestamped transcripts in `data\prospects\import-logs` for details.
These local logs include import reports and should be retained/rotated according
to your operational needs. A scheduled
run imports candidates only; simulation approval remains a deliberate review.
No GitHub cron is used because hosted runners cannot see this local ignored inbox
or the local SQLite database.
The task runs code from this checkout. Merge the ingestion changes before
switching this checkout to a branch that lacks the new job/scripts, or disable
the task first. Re-register for the next draft year only after changing inboxes
and reviewing the candidate year.

### Approve a reviewed candidate pool

The report returns a `snapshot_id`. Use that exact ID to preview approval, then
approve and generate fresh default boards for all teams:

```powershell
..\.venv\Scripts\python.exe -m app.jobs.approve_projected_pool --snapshot-id <snapshot_id>
..\.venv\Scripts\python.exe -m app.jobs.approve_projected_pool --snapshot-id <snapshot_id> --commit --generate-boards
```

Both CLIs default to dry-run. Approval is committed before board generation;
each default board is committed independently. A generation error is reported
explicitly and may leave some new default versions already created. After fixing
the error, rerunning preserves approval and creates additional default versions.

### Copy a default board into a personal board

After approving the desired source snapshot and generating defaults, sign in,
select your team, and open **Default board**. Choose **Copy to My board** to
create an editable personal copy of that team's persisted prospects, ranks,
scores, and source evidence. There is no placeholder-prospect fallback.
The new personal board loads immediately; use arrows or drag-and-drop to
reorder prospects, then **Save changes**. Switching away and back to **My board**
reloads the saved order without altering the default.

If a personal board already exists, copying requires explicit confirmation.
**Keep existing board** cancels without writing. **Replace My board with default**
creates a newer personal-board version from the latest default; the previous
copy remains stored but is no longer the active version. This replaces the
current custom order, not other teams' boards or other users' work.
Inactive default entries are not reactivated in the copy; an empty default must
be regenerated before copying.

API clients use `POST /api/teams/{team_id}/board/copy?draft_year=2027`.
An existing personal board returns HTTP 409 without changes. Only after user
confirmation should clients retry with `&replace_existing=true`.
Copying does not itself approve imports or regenerate defaults. A later import
or default regeneration never silently replaces a user's personal board.

### Identity and eligibility safeguards

- Imports reuse stable prospect IDs and append dated rankings. Existing profiles,
  eligibility, draft references, and personal board entries/order are preserved.
  Prospects missing from a later CSV are reported, not deleted.
- New players remain `unconfirmed`. Ambiguous identities, unexpected school
  changes, and year conflicts require review rather than automatic reassignment.
- Each new snapshot needs explicit approval. New drafts and generated defaults
  use the latest approved snapshot by collection date for their draft year.
- An approved pool contains only that snapshot's members whose status is
  `eligible` or `unconfirmed`; withdrawn and other blocked statuses remain
  unavailable. Nonmembers, including legacy samples, stay stored but are excluded.
- A draft pins its snapshot when created. Later approvals/default-board versions
  do not replace that pool or its source rankings. Eligibility changes can still
  make a pinned prospect unavailable. Without a pinned snapshot, legacy drafts
  retain their confirmed-eligible-only policy.
- Board regeneration creates new default versions; it never refreshes or
  reorders personal copies. Preserved personal entries outside a draft's pool
  cannot be selected in that draft.

### Source ranks versus UMM scores

Source rank is displayed separately from the team-adjusted UMM score. When
stored evaluation signals exist, they take precedence. Otherwise, an approved
snapshot supplies a transparent fallback evaluation:

```text
source evaluation = 100 * (snapshot prospect count - source rank + 1) / snapshot prospect count
```

The existing concern penalty and team-weighted scoring still apply. This
percentile is not an athletic measurement, scouting grade, or PFF grade.
Generated entries record the source snapshot, rank, normalized evaluation, and
evaluation basis in their score breakdown. Projected entries show an eligibility
disclaimer. The draft API's existing `eligible_players` field remains its
selectable-pool response and now includes eligibility, projected flags, and source
ranks.

The Big Board shows college logos beside school names. ESPN numeric team IDs
come from its public college-football team directory; legacy seeded slug-based
logo URLs are resolved when serving reference, board, and draft-pool responses.
Custom logo URLs are preserved. If an image cannot load, the school name remains
visible without a broken-image placeholder. Projection notices remain in the
page notice and evidence panel rather than repeating on every prospect row.

After completing and validating a full refresh of prospects, team needs, and
draft order, record its completion date with `DATA_UPDATED_ON=YYYY-MM-DD` in the
backend environment (or local `.env`), then restart the API. Do not advance this
date for partial imports or individual board saves. No full-refresh date is
assumed by default.

The public `GET /api/data/status` endpoint returns that explicit date as
`updated_on` (`YYYY-MM-DD`), or `null` when none is recorded. The homepage displays
`all data updated MM/DD/YYYY` beside Live Board. It does not infer the date from
prospect snapshots, board saves, or the current clock. Loading, missing data, and
request failures have distinct labels.
The eligibility banner is shown only in the authenticated board workspace;
the individual projected prospect disclaimer remains in the evidence panel.

## Permissioned 2027 PFF prospect boards

Only collect and import PFF data when your permission covers automated retrieval,
storage, and the intended display/use. A consumer API key alone is not evidence
of those rights. The browser collector does not use the PFF API, send API keys,
automate login, bypass paywalls, or evade access controls. It collects factual
board fields, not scouting write-ups or images.

From the repository root, install the backend requirements and browser runtime:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
New-Item -ItemType Directory -Force data\prospects
Set-Location backend

# Collection is read-only and refuses to overwrite an existing output.
..\.venv\Scripts\python.exe -m app.jobs.pff_big_board collect --draft-year 2027 --min-prospects 150 --output ..\data\prospects\pff-2027-2026-10-14.json
```

The October 14, 2026 review found 150 rendered rows, four missing grades, and
a source update label of October 6, 2026. This is not a guarantee of future row
counts or full draft-class coverage. The collector checks the displayed season,
consecutive unique ranks, identity fields, and reviewed school/position mappings.
It fails rather than saving an undersized or malformed result. An enabled
`Next` button also stops collection so pagination can be reviewed.

Some new browser sessions may load the page shell but not render the board.
If that happens, do not circumvent site controls. The collector can optionally
use an authorized session supplied with `--storage-state` (a secret file kept
outside git), or attach to a browser you explicitly started with a local
Chromium debugging endpoint:

```powershell
# Open the authorized 2027 board in that browser first. The collector requires
# exactly one matching tab and does not navigate, log in, or close that browser.
..\.venv\Scripts\python.exe -m app.jobs.pff_big_board collect --draft-year 2027 --min-prospects 150 --cdp-url http://127.0.0.1:9222 --output ..\data\prospects\pff-2027-2026-10-14.json
```

Only enable a debugging endpoint for a dedicated local browser profile. Never
expose it beyond loopback; it grants access to that browser's session. Close the
debug browser after collection. If rows still do not render, stop and resolve
access with the provider; there is no alternate hidden-endpoint fallback.

Initialize the configured database before the first import (for PostgreSQL,
apply `backend/app/db/migrations/020_add_prospect_board_snapshots.sql` through
your normal migration process):

```powershell
# Review DATABASE_URL first. This command seeds reference data, including teams.
..\.venv\Scripts\python.exe -m app.db.initialize

# Preview only: no player, identity, or snapshot writes.
..\.venv\Scripts\python.exe -m app.jobs.pff_big_board import --snapshot ..\data\prospects\pff-2027-2026-10-14.json

# Only after reviewing the preview:
..\.venv\Scripts\python.exe -m app.jobs.pff_big_board import --snapshot ..\data\prospects\pff-2027-2026-10-14.json --commit
```

### Identity and data-quality rules

- Source IDs are preferred when present. Otherwise a persistent source key uses
  normalized full name and source school, **never board rank**. Names retain
  punctuation and suffixes. Repeated imports reuse UMM IDs.
- Exact, unambiguous existing names and schools can match existing players.
  Transfers, namesakes, conflicting source mappings, and draft-year conflicts
  stop the import for review; there are no fuzzy matches.
- For reviewed transfers/namesakes, `--identity-map path\to\mapping.json` accepts
  a JSON object whose keys are the source keys and whose values are **existing**
  UMM player IDs. The key is `id:<provider-id>` if present; otherwise it is
  `name-school:<SHA-256>` of the JSON array of normalized name and source school,
  as defined by `source_key` in `backend/app/services/pff_snapshot.py`.
  The dry-run reports keys and mapped IDs on successful resolution; on a
  conflict, use that function to derive the key. Overrides cannot reassign an
  existing source mapping or silently move a player to a different draft year.
- Explicit mappings include `HB -> RB`, `ED -> EDGE`, `DI -> DT`, `T -> OT`,
  and `G/C -> IOL`. Source labels remain in the ranking snapshot. Youngstown
  State is explicitly seeded as FCS, not fabricated as an FBS school.
- New players have `eligibility_status = unconfirmed`. They do not enter the
  eligible simulation pool automatically. Declaration/eligibility must be
  reviewed separately. Existing player profiles and eligibility are not
  overwritten by a source board.
- PFF grades remain nullable source grades, separate from rank, athletic scores,
  and UMM scores. Missing is not zero. These imports do **not** change UMM ranking
  weights or regenerate existing team boards.
- Each dated snapshot retains its collection time, source update label, URL,
  scope, source labels, mapped school/position, and rank/grade. An exact dated
  snapshot is idempotent; a newly collected date preserves new history rather
  than overwriting the previous snapshot.

Licensed snapshots and browser authentication files should not be committed.
`data/prospects/` and `playwright/.auth/` are ignored for this purpose.
