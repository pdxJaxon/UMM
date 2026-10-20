# UMockMe

Reviewed, year-specific team-needs and projected-order refreshes are documented
in [the data workflow](data/README.md#reviewed-team-needs-and-projected-draft-order).
The pilot models one first-round pick per team, not traded pick ownership.

Candidate ingestion now accepts authorized dated PFF CSV exports. See the
[PFF import and nightly-job workflow](data/README.md#pff-csv-imports-and-projected-pools);
simulation-pool approval and detailed prospect enrichment remain separate.

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

When your controlled team is on the clock, the draft room requests an advisory
AI recommendation using the persisted draft pool, default-board/source ordering,
team needs, and historical team tendencies. Personal board order remains your
selection preference, not model evidence. Already selected, withdrawn, and
out-of-pool players cannot be recommended. Responses are bound to the draft,
team, and current pick and are discarded when that state changes.

Configure `LLM_API_KEY` in the backend environment to enable the existing
OpenAI-compatible provider; `LLM_API_URL` and `LLM_MODEL` select the service/model.
Provider failure is shown explicitly with a recommendation retry action, not
silently replaced by another engine. Manual selection remains available.
Selecting the recommendation or an alternative only fills the pick selector:
**Make pick** is the separate confirmation that saves a selection.

The displayed rank is the available pool's UMM default-board order followed by
pinned source order, not a personalized-board rank. Source consensus rank is
shown separately. Confidence and explanations are model output, not verified
scouting facts. Completed rounds remain visible as a first-round recap until
you choose **Close draft**.

### Verification

From `frontend\angular-app`, run `npm run test:unit` for component state tests and
`npm run build` for Angular template/type validation. The regression script runs
both alongside backend tests with the existing 80% coverage gate.

Browser smoke check (use test accounts and an isolated database):

1. Sign in, load a team board, set randomness, and start a mock draft.
2. Confirm the draft advances to your team; team/board/randomness controls are
   locked. Verify the recommendation's name, rank, explanation, and alternatives.
3. Choose an alternative, then another player in the selector. Neither action
   should change the pick log. Press **Make pick** to persist that selection.
4. Confirm other teams advance, 32 distinct picks appear in the recap, and the
   recommendation disappears. Close the completed draft explicitly.
5. Repeat with an early and late controlled team. With the provider unavailable,
   confirm an explicit error and retry appear while manual picks still work.
6. Delay a recommendation response, then submit a manual pick or sign out.
   Confirm the late result cannot reappear for the old pick/session.

The UI browser check can mock draft/provider responses to avoid paid model calls
and test-user records in the local application database; backend lifecycle tests
exercise real persistence separately.
