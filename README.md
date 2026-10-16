# UMockMe

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

In the first window, start the API and initialize the local database:

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
