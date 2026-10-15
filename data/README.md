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
