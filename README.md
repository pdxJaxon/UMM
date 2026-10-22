# UMockMe

Reviewed, year-specific team-needs and projected-order refreshes are documented
in [the data workflow](data/README.md#reviewed-team-needs-and-projected-draft-order).
The pilot models one first-round pick per team, not traded pick ownership.

Candidate ingestion now accepts authorized dated PFF CSV exports. See the
[PFF import and nightly-job workflow](data/README.md#pff-csv-imports-and-projected-pools);
simulation-pool approval and detailed prospect enrichment remain separate.

Users can copy their team's generated default into **My board**, then reorder
and save the persisted prospects. Existing custom orders require confirmation
before replacement; see [personal board copying](data/README.md#copy-a-default-board-into-a-personal-board).

## Run locally on Windows

### Prerequisites

- Python 3.11+
- Node.js 20 LTS and npm

### One-time setup

The commands below use `C:\Users\s008919\git\UMM` as the repository location.
Replace that path if you cloned the project somewhere else.

Run these commands in PowerShell:

```powershell
Set-Location "C:\Users\s008919\git\UMM"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Push-Location frontend\angular-app
npm ci
Pop-Location
```

### Start the site

Open two PowerShell windows. Each command block below first switches to the
correct folder, regardless of where your terminal starts.

In the first window, initialize a new local database and start the API. The
initializer also seeds reference data; for an existing database, use the
schema-only upgrade in the [prospect import workflow](data/README.md#consensus-csv-imports-and-projected-pools)
instead of rerunning the initializer:

```powershell
Set-Location "C:\Users\s008919\git\UMM\backend"
..\.venv\Scripts\python.exe -m app.db.initialize
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In the second window, start the frontend:

```powershell
Set-Location "C:\Users\s008919\git\UMM\frontend\angular-app"
npm start -- --host 127.0.0.1 --port 4201
```

If PowerShell cannot find `..\.venv\Scripts\python.exe`, make sure you ran the
one-time setup and that your current folder is `C:\Users\s008919\git\UMM\backend`,
not `backend\scripts`.

Open the site at <http://localhost:4201>. The API health check is at
<http://localhost:8000/health>, and interactive API documentation is at
<http://localhost:8000/docs>.

The local database uses SQLite by default and is stored in
`backend\umockme.db`. No separate database server is needed for the default
local setup.

To load a consensus CSV and explicitly approve projected prospects, follow the
[import and approval workflow](data/README.md#consensus-csv-imports-and-projected-pools).
Imports preserve personal boards; approval allows simulation without certifying
draft eligibility.

## First-round draft recommendations

Every new persisted pick requires an LLM decision. Simulated teams use the model's
validated selection; the controlled team receives the model decision first and
may explicitly override it with another eligible prospect. The pick record
stores the model-selected and final player, provider/model/prompt metadata,
candidate evidence, and whether the user overrode the model. Personal board
order remains your selection preference, not model evidence. Already selected,
withdrawn, and out-of-pool players cannot be selected. Recommendations are bound
to the draft, team, and current pick and are discarded when that state changes.

The selected team's active, nonzero team needs appear above its board title as
position abbreviations. Automated and AI-recommended picks may prioritize
positions with a need score of 70 or higher, but only within the round's maximum
reach distance on the team's default board: 12, 15, 20, 25, 35, 60, and 150
board slots for rounds one through seven, respectively. The current draft
simulator covers round one; reach limits are configured per round for
later-round support. Controlled-team picks may override the LLM selection only after the server has
obtained and validated an LLM decision.

Configure `LLM_API_KEY` in the backend environment to enable the existing
OpenAI-compatible provider; `LLM_API_URL` and `LLM_MODEL` select the service/model.
If the provider is missing or fails, the pick request fails and no picks from
that simulation batch are saved. The draft room blocks controlled-team picks
until an LLM decision is available and provides a retry action. The LLM decision
is the default selection; choosing another eligible player is an explicit
manual override. The server obtains a fresh LLM decision when the pick is
submitted and records that decision alongside the final selection.

The displayed rank is the available pool's UMM default-board order followed by
pinned source order, not a personalized-board rank. Source consensus rank is
shown separately. Confidence and explanations are model output, not verified
scouting facts. Completed rounds remain visible as a first-round recap until
you choose **Close draft**.

Automated picks are saved and shown one at a time, with a user-selected pause:
**Slow** (3 seconds), **Medium** (2 seconds, the default), or **Fast** (1 second)
after each visible pick before requesting the next selection (server latency
can make the interval longer). Speed can be changed before or during a draft.
Changing speed during a pending pause restarts that pause at the new duration;
an in-flight request is not interrupted. The draft pauses for your team's turn and stops
at round completion. Failures stop advancement and expose **Retry advance**;
signing out or leaving the app cancels pending timers. The pick log and recap
show each prospect's position, college name, and college logo when available.
The selecting NFL team's logo appears to the left of its name. Missing or
failed team logos leave the team name visible. The prospect selector omits
repeated "Projected" labels; the draft eligibility notice remains visible.
A failed logo is hidden without removing the college name.
Internal selection-source labels are not displayed in the log or recap.
The log follows each new selection; scrolling between selections is preserved
until the next pick arrives.

The UI calls `POST /api/drafts/{id}/auto-simulate?max_picks=1` for paced
advancement. API clients that omit `max_picks` retain the existing bulk behavior
of advancing to the controlled team or round completion; there is no server-side
sleep or long-held request between picks.

### Verification

From `frontend\angular-app`, run `npm run test:unit` for component state tests and
`npm run build` for Angular template/type validation. The regression script runs
both alongside backend tests with the existing 80% coverage gate.

Browser smoke check (use test accounts and an isolated database):

1. Sign in, load a team board, set randomness, and start a mock draft.
2. Confirm the draft advances to your team; team/board/randomness controls are
   locked. Verify the recommendation's name, rank, explanation, and alternatives.
3. Confirm the LLM choice is preselected. Choose an alternative or another
   eligible player to mark a manual override, then submit the displayed pick
   or override.
4. Confirm other teams advance, 32 distinct picks appear in the recap, and the
   recommendation disappears. Close the completed draft explicitly.
5. Repeat with an early and late controlled team. With the provider unavailable,
   confirm an explicit error and retry appear and that no pick can be submitted.
6. Delay a recommendation response, then sign out or advance to another pick.
   Confirm the late result cannot reappear for the old pick/session.

The UI browser check can mock draft/provider responses to avoid paid model calls
and test-user records in the local application database; backend lifecycle tests
exercise real persistence separately.
