release: cd backend && python -c "from app.db.initialize import initialize_schema; initialize_schema()"
web: cd frontend\angular-app && npm start -- --host 0.0.0.0 --PORT$PORT 