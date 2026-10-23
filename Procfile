release: cd backend && python -c "from app.db.initialize import initialize_schema; initialize_schema()"
web: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT