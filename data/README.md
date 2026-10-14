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

### Nightly automatic refresh (scheduler installation deferred)

The host-neutral batch command collects a fresh board, archives the validated
snapshot, and automatically imports it in one database transaction. Unlike the
manual `import` command, this explicitly named refresh command writes by default:

```powershell
# Run from backend, with DATABASE_URL pointing to the intended initialized DB.
# Requires live authorized collection to be verified before production use.
..\.venv\Scripts\python.exe -m app.jobs.refresh_pff_board --draft-year 2027 --min-prospects 150 --output-dir ..\data\prospects

# Alternative: a dedicated authorized local browser with exactly one season tab.
# This batch RELOADS that tab before extraction; the manual collector does not.
..\.venv\Scripts\python.exe -m app.jobs.refresh_pff_board --draft-year 2027 --min-prospects 150 --output-dir ..\data\prospects --cdp-url http://127.0.0.1:9222
```

`--storage-state` is another option, mutually exclusive with `--cdp-url`.
There is no automated login or access-control bypass. The October 14 validation
found fresh headed/headless sessions did not render rows; live CDP refresh still
needs verification. A pre-existing browser tab is not evidence that unattended
reloads will work. Browser/session expiry must cause failure, not stale success.

Operational contract:

- Schedule exactly one invocation nightly on the eventual always-on host. The
  OS, nightly time/timezone, scheduler, and alert destination are not yet chosen;
  no schedule has been installed or enabled. Do not run a timer in every API
  worker. Keep an explicit draft year; review the season rollover each year.
- All scheduled invocations targeting the same database must use the **same
  absolute output directory on one host's local filesystem**. A nonblocking OS
  file lock prevents overlap and is released on process exit/crash; leave the
  lock file in place. Multiple hosts, network filesystems, and manual imports
  concurrent with the batch are not supported by this host-local guard.
- Each invocation writes a unique UTC-dated `*.run.json` report. Once validated,
  collection is atomically archived as `*.snapshot.json` **before** importing.
  Final reports include timestamps, stage, import counts, and snapshot ID.
  New dates preserve history even when rankings are unchanged.
- Unknown mappings, identity conflicts, undersized boards, and any reduction
  from the latest imported season's row count block the entire import. Nothing
  is deleted when a prospect drops off a board. A legitimate count reduction
  requires review and the manual snapshot import command above.
- Failures exit nonzero and log the exception/run ID/stage to stderr; the run
  report records `failed` and the exception type. Wire the host scheduler to
  alert on nonzero exits **and missing nightly success**, not merely file
  creation. Setup errors can occur before a report exists; a killed process can
  leave a `running` report. Do not treat either as success.
- No internal retries hide review failures. Resolve the cause, then retry a new
  collection or manually import the archived snapshot. `--identity-map` accepts
  reviewed overrides using the same rules as manual import. An exact snapshot
  retry is idempotent. If the DB committed but final report writing failed,
  check/reimport that archived snapshot rather than assuming it rolled back.
- The job does not initialize/migrate the database, seed reference data, change
  eligibility or UMM scores, or regenerate team boards. Apply migrations and
  verify reference data once through the normal deployment process.
- Restrict filesystem access to snapshots/reports (which include prospect
  identities), browser state, and database credentials. Keep them outside git,
  back up dated history, and set retention/monitoring before enabling production.

Deployment gates: verify live fresh/reloaded collection, run a read-only preview
against the intended database, apply/verify migrations, run one supervised batch,
then install the chosen scheduler and failure/staleness alerts. These steps are
not satisfied by offline DOM or isolated-database tests.

### Read-only prospect review

Signed-in users can select **Prospect data** in the Angular workspace to review
the latest imported PFF snapshot for the configured draft season. The view shows
collection time in UTC, the source's update label and URL, scope, source school
and position, canonical position, PFF rank/grade, and current UMM eligibility.
Missing grades are explicitly labeled, not converted to zero.

The authenticated `GET /api/prospect-boards/pff/latest?draft_year=2027` endpoint
compares the latest two snapshots by collection timestamp (ID breaks ties), not
import order. Positive rank changes mean a move up the board; negative changes
mean a move down. Players absent from the previous snapshot are labeled new,
and a first snapshot has no comparison. Rows absent from the latest snapshot
are not displayed or deleted. Comparison is always within the same source and
draft year. This view does not fetch PFF, import data, change eligibility, or
regenerate UMM boards. No imported snapshot produces an explicit empty state.
