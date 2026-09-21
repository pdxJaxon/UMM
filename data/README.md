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
