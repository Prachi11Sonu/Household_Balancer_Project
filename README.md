# Shared Expenses App

This is my submission for the Spreetail shared-expenses assignment. The app imports the provided messy expense export, records the cleanup decisions it makes, and calculates balances for the flatmates.

I kept the project deliberately small: Flask for the web app and SQLite for the relational database. That makes the importer and balance calculation easy to trace during review.

## What Works

- Login with a seeded demo account.
- Create groups.
- Store membership periods, including people joining and leaving.
- Add expenses manually.
- Record payments/settlements.
- Import the original `Expenses Export.csv` through the UI.
- Detect and report CSV anomalies instead of silently fixing them.
- Calculate group balances and a suggested settlement plan.
- Open an expense and see the exact split behind it.

## Demo Login

```text
Email: admin@example.com
Password: password
```

## Running Locally

```powershell
cd "C:\Users\prach\Downloads\Spreetail_Project"
python -m pip install -r requirements.txt
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

The database is created automatically at:

```text
instance/spreetail.db
```

## Import Flow

1. Log in.
2. Go to **Import**.
3. Select the `Flatmates` group.
4. Upload the original `Expenses Export.csv`.
5. Review the import report.
6. Approve any cleanup actions that need human review.
7. Go back to **Balances** to see the final summary.

## Main Files

- `app.py` - Flask routes, database setup, CSV importer, split logic, and balance calculation.
- `static/styles.css` - dark UI theme.
- `templates/` - page templates.
- `SCOPE.md` - data problems found and how I handled them.
- `DECISIONS.md` - implementation decisions and tradeoffs.
- `AI_USAGE.md` - how I used AI while building the project.

## Deployment

For a real deployment, I would set `SECRET_KEY` in the environment and run the Flask app behind a production WSGI server. SQLite is fine for this assignment-sized app, but Postgres would be my next choice if this had multiple real users.
