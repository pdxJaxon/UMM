release: cd backend && python -c "from app.db.initialize import initialize_schema; initialize_schema()"
web: honcho -f Procfile.honcho start