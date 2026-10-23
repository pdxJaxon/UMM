release: cd backend && python -c "from app.db.initialize import initialize_schema; initialize_schema()"
web: cd backend && gunicorn app:app --bind 0.0.0.0:$PORT