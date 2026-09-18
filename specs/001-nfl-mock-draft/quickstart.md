# Quickstart: NFL Mock Draft Experience

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Node.js and Angular toolchain for the frontend workspace
- Access to an LLM provider or compatible inference endpoint for AI-assisted recommendations
- Environment variables for database credentials, auth secrets, and AI configuration

## Local setup

1. Start PostgreSQL and create an application database.
2. Configure environment variables:
   - DATABASE_URL
   - SECRET_KEY
   - JWT_SECRET or equivalent
   - AI_PROVIDER_API_KEY
   - AI_MODEL_NAME
3. Install backend dependencies.
4. Install frontend dependencies for Angular and Flask gateway.
5. Run database migrations or bootstrap scripts.

## Run validation scenarios

### 1. User can register and start a new draft

- Create an account.
- Sign in.
- Select a team to control.
- Start a draft run.
- Verify that the app shows the controlled team and the current pick context.

Expected result: a new draft is created with exactly one user-controlled team and all other teams set to simulation state.

### 2. User makes a controlled-team pick

- Advance to a pick where the controlled team is on the clock.
- Select an available player from the ranked list.
- Submit the selection.

Expected result: the selection is saved, recorded as a `DraftPick`, and the draft advances.

### 3. Auto-simulation for other teams

- Let the draft progress past a non-controlled team's turn.
- Verify that the system uses the board logic to auto-select a player.

Expected result: a `DraftPick` is recorded with `selection_source = AUTO` for the simulated team.

### 4. Board customization is persisted

- Open a team board.
- Reorder, remove, or add players.
- Save the board.

Expected result: the user-specific board persists and is used in future draft runs for that team.

### 5. Rating and ranking data is auditable

- Inspect a player's record.
- Verify the raw signals and derived `UMM_Ranking` are stored.

Expected result: the raw values and the final composite score are both available for review and recalculation.

### 6. Authorization and audit checks

- Attempt to access another user's draft or board.
- Attempt invalid or missing security actions.

Expected result: the system denies access and records an `AuditEvent` entry.

## Example commands

```bash
# install dependencies once
python -m pip install -r backend/requirements.txt
cd frontend/angular-app
npm ci
cd ../..

# fast pre-PR check: backend smoke tests and frontend production build
powershell -ExecutionPolicy Bypass -File scripts/test-smoke.ps1

# full regression: all backend tests with coverage and Angular production build
powershell -ExecutionPolicy Bypass -File scripts/test-regression.ps1


The `Smoke tests` check in the repository CI workflow must be configured as a
required pull request status check in GitHub branch protection. The workflow
also runs the full regression suite on every pull request and push to `master`.
# frontend
dcd frontend/angular-app
npm install
ng serve
```

## Definition of done for validation

The feature is ready for implementation review when all of the following are true:

- new draft creation works with one controlled team
- non-controlled teams are auto-simulated
- user boards persist and apply to future draft runs
- raw rating signals and UMM_Ranking are stored together
- security checks and audit events behave as expected
- core flows pass responsive mobile and desktop checks
