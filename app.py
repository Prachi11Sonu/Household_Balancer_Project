from __future__ import annotations

import csv
import io
import os
import re
import sqlite3
from urllib.parse import urlencode
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from hashlib import sha256
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for


APP_ROOT = Path(__file__).parent
DB_PATH = APP_ROOT / "instance" / "spreetail.db"
USD_TO_INR = Decimal("83.25")
MONEY = Decimal("0.01")

CANONICAL_NAMES = {
    "aisha": "Aisha",
    "rohan": "Rohan",
    "priya": "Priya",
    "priya s": "Priya",
    "meera": "Meera",
    "sam": "Sam",
    "dev": "Dev",
    "devs friend kabir": "Kabir",
    "dev's friend kabir": "Kabir",
    "kabir": "Kabir",
}

MEMBERSHIP_POLICY = {
    "Aisha": ("2026-02-01", None),
    "Rohan": ("2026-02-01", None),
    "Priya": ("2026-02-01", None),
    "Meera": ("2026-02-01", "2026-03-31"),
    "Sam": ("2026-04-10", None),
    "Dev": ("2026-02-08", "2026-03-14"),
    "Kabir": ("2026-03-11", "2026-03-11"),
}


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-for-deploy")


def money(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def cents(value: Decimal) -> int:
    return int((money(value) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_cents(value: int) -> Decimal:
    return money(Decimal(value) / 100)


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def normalize_name(value: str | None) -> str:
    key = re.sub(r"\s+", " ", (value or "").strip().lower())
    return CANONICAL_NAMES.get(key, value.strip() if value else "")


def parse_people(value: str | None) -> list[str]:
    return [normalize_name(part) for part in (value or "").split(";") if part.strip()]


def parse_date(value: str) -> tuple[str | None, str | None]:
    raw = (value or "").strip()
    try:
        return datetime.strptime(raw, "%d-%m-%Y").date().isoformat(), None
    except ValueError:
        pass
    try:
        parsed = datetime.strptime(raw + "-2026", "%b-%d-%Y").date()
        return parsed.isoformat(), "non_standard_date"
    except ValueError:
        return None, "invalid_date"


def active_on(person: str, expense_date: str) -> bool:
    start, end = MEMBERSHIP_POLICY.get(person, ("2026-02-01", None))
    return start <= expense_date and (end is None or expense_date <= end)


def clean_description(value: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower())
    tokens = [t for t in text.split() if t not in {"at", "the", "order"}]
    return " ".join(tokens)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def init_db() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                base_currency TEXT NOT NULL DEFAULT 'INR'
            );
            CREATE TABLE IF NOT EXISTS group_memberships (
                id INTEGER PRIMARY KEY,
                group_id INTEGER NOT NULL REFERENCES groups(id),
                person_name TEXT NOT NULL,
                joined_on TEXT NOT NULL,
                left_on TEXT
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY,
                group_id INTEGER NOT NULL REFERENCES groups(id),
                source_row INTEGER,
                expense_date TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Uncategorized',
                paid_by TEXT NOT NULL,
                amount_original_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                fx_rate TEXT NOT NULL,
                amount_inr_cents INTEGER NOT NULL,
                split_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'accepted',
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS expense_splits (
                id INTEGER PRIMARY KEY,
                expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
                person_name TEXT NOT NULL,
                share_cents INTEGER NOT NULL,
                basis TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY,
                group_id INTEGER NOT NULL REFERENCES groups(id),
                source_row INTEGER,
                payment_date TEXT NOT NULL,
                paid_by TEXT NOT NULL,
                paid_to TEXT NOT NULL,
                amount_inr_cents INTEGER NOT NULL,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS import_batches (
                id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                accepted_rows INTEGER NOT NULL,
                skipped_rows INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS import_anomalies (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER NOT NULL REFERENCES import_batches(id),
                row_number INTEGER NOT NULL,
                code TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                policy TEXT NOT NULL,
                action TEXT NOT NULL,
                review_required INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        if not conn.execute("SELECT 1 FROM users").fetchone():
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Demo Admin", "admin@example.com", sha256(b"password").hexdigest()),
            )
        if not conn.execute("SELECT 1 FROM groups").fetchone():
            conn.execute("INSERT INTO groups (name, base_currency) VALUES (?, ?)", ("Flatmates", "INR"))
            group_id = conn.execute("SELECT id FROM groups WHERE name='Flatmates'").fetchone()["id"]
            for person, (start, end) in MEMBERSHIP_POLICY.items():
                conn.execute(
                    "INSERT INTO group_memberships (group_id, person_name, joined_on, left_on) VALUES (?, ?, ?, ?)",
                    (group_id, person, start, end),
                )
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(expenses)").fetchall()]
        if "category" not in columns:
            conn.execute("ALTER TABLE expenses ADD COLUMN category TEXT NOT NULL DEFAULT 'Uncategorized'")
        migrations = {
            "import_batches": [
                ("group_id", "INTEGER"),
                ("rolled_back_at", "TEXT"),
                ("rolled_back_by", "TEXT"),
                ("rollback_note", "TEXT"),
            ],
            "expenses": [("batch_id", "INTEGER")],
            "payments": [("batch_id", "INTEGER")],
            "import_anomalies": [
                ("resolved_at", "TEXT"),
                ("resolved_action", "TEXT"),
                ("resolution_note", "TEXT"),
            ],
        }
        for table, additions in migrations.items():
            existing = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            for column, definition in additions:
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def add_anomaly(anomalies, row_num, code, severity, message, policy, action, review=False):
    anomalies.append(
        {
            "row_number": row_num,
            "code": code,
            "severity": severity,
            "message": message,
            "policy": policy,
            "action": action,
            "review_required": 1 if review else 0,
        }
    )


def guess_category(description: str) -> str:
    text = (description or "").lower()
    checks = [
        ("Rent", ["rent"]),
        ("Utilities", ["wifi", "electricity", "cylinder"]),
        ("Groceries", ["groceries", "bigbasket", "dmart"]),
        ("Food", ["dinner", "lunch", "pizza", "brunch", "snacks", "drinks", "cake", "swiggy"]),
        ("Cleaning", ["cleaning", "maid"]),
        ("Trip", ["goa", "flight", "villa", "beach", "scooter", "parasailing", "cab"]),
        ("Furniture", ["furniture"]),
    ]
    for category, words in checks:
        if any(word in text for word in words):
            return category
    return "Uncategorized"


def parse_amount(raw: str, row_num: int, anomalies: list[dict]) -> Decimal | None:
    value = (raw or "").strip()
    if "," in value:
        add_anomaly(anomalies, row_num, "amount_thousands_separator", "info", f"Amount '{value}' contains a comma.", "Remove separators before Decimal parsing.", "normalized")
        value = value.replace(",", "")
    try:
        amount = Decimal(value)
    except Exception:
        add_anomaly(anomalies, row_num, "invalid_amount", "error", f"Amount '{raw}' is not numeric.", "Reject rows with unparseable amounts.", "skipped")
        return None
    if amount == 0:
        add_anomaly(anomalies, row_num, "zero_amount", "warning", "Zero amount does not change balances.", "Skip zero-value expenses and report them.", "skipped")
        return None
    if amount < 0:
        add_anomaly(anomalies, row_num, "negative_amount", "info", "Negative amount treated as a refund/credit.", "Accept refunds as negative expenses using the same split.", "accepted")
    rounded = money(amount)
    if rounded != amount:
        add_anomaly(anomalies, row_num, "amount_precision", "warning", f"Amount {amount} has more than two decimals.", "Round half up to two decimals.", f"rounded_to_{rounded}")
    return rounded


def split_amount(total: Decimal, split_type: str, people: list[str], details: str, row_num: int, anomalies: list[dict]) -> dict[str, Decimal] | None:
    if not people:
        add_anomaly(anomalies, row_num, "missing_split_people", "error", "No split participants were provided.", "Reject rows without split participants.", "skipped")
        return None
    split_type = (split_type or "").strip().lower()
    shares: dict[str, Decimal] = {}
    if split_type == "equal":
        if details.strip():
            add_anomaly(anomalies, row_num, "split_detail_ignored", "warning", "Equal split has extra split_details.", "Keep split_type authoritative and ignore extra details.", "ignored_details")
        each = money(total / Decimal(len(people)))
        shares = {p: each for p in people}
        drift = total - sum(shares.values(), Decimal("0"))
        if drift:
            shares[people[0]] = money(shares[people[0]] + drift)
        return shares
    parts = {}
    for name, value in re.findall(r"([^;]+?)\s+(-?\d+(?:\.\d+)?)%?", details or ""):
        parts[normalize_name(name)] = Decimal(value)
    if split_type == "unequal":
        if set(parts) != set(people):
            add_anomaly(anomalies, row_num, "split_people_mismatch", "error", "Unequal split details do not match split_with.", "Reject unequal splits that cannot be traced to each person.", "skipped")
            return None
        if money(sum(parts.values())) != total:
            add_anomaly(anomalies, row_num, "unequal_total_mismatch", "error", "Unequal split details do not add to total.", "Reject to avoid a silent balancing guess.", "skipped")
            return None
        return {p: money(parts[p]) for p in people}
    if split_type == "percentage":
        pct_total = sum(parts.values())
        if pct_total != Decimal("100"):
            add_anomaly(anomalies, row_num, "percentage_total_mismatch", "warning", f"Percentages add to {pct_total}%.", "Normalize percentages to 100% and report the correction.", "normalized")
        base = pct_total or Decimal("100")
        shares = {p: money(total * parts.get(p, Decimal("0")) / base) for p in people}
    elif split_type == "share":
        unit_total = sum(parts.values())
        if unit_total <= 0:
            add_anomaly(anomalies, row_num, "invalid_share_units", "error", "Share units are missing or zero.", "Reject share splits without positive units.", "skipped")
            return None
        shares = {p: money(total * parts.get(p, Decimal("0")) / unit_total) for p in people}
    else:
        add_anomaly(anomalies, row_num, "missing_or_unknown_split_type", "error", f"Split type '{split_type}' is not supported as an expense.", "Treat settlement-like rows separately; reject unknown expense splits.", "skipped")
        return None
    drift = total - sum(shares.values(), Decimal("0"))
    if drift and people:
        shares[people[0]] = money(shares[people[0]] + drift)
    return shares


def membership_warnings(people: list[str], expense_date: str) -> list[str]:
    return [p for p in people if not active_on(p, expense_date)]


def detect_duplicate(row, parsed, seen_rows, row_num, anomalies):
    key = (parsed["date"], clean_description(row["description"]))
    for prev in seen_rows:
        same_day = prev["date"] == parsed["date"]
        same_people = set(prev["people"]) == set(parsed["people"])
        words = set(clean_description(row["description"]).split())
        prev_words = set(clean_description(prev["description"]).split())
        overlap = len(words & prev_words) / max(1, min(len(words), len(prev_words)))
        if same_day and same_people and overlap >= 0.6:
            if prev["amount"] == parsed["amount"]:
                add_anomaly(anomalies, row_num, "duplicate_expense", "warning", f"Likely duplicate of row {prev['row_number']}.", "Keep the earliest row; later duplicate is excluded until reviewed.", "excluded_pending_review", True)
            else:
                add_anomaly(anomalies, row_num, "conflicting_duplicate", "warning", f"Possible duplicate of row {prev['row_number']} with a different amount.", "Accept the row whose notes indicate the other row is wrong; surface for review.", "accepted_pending_review", True)
            return True
    seen_rows.append({**parsed, "row_number": row_num, "description": row["description"]})
    return False


def import_csv(file_storage, group_id: int) -> int:
    content = file_storage.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    anomalies: list[dict] = []
    accepted = skipped = 0
    seen_rows: list[dict] = []
    now = datetime.utcnow().isoformat(timespec="seconds")
    with db() as conn:
        batch_id = conn.execute(
            "INSERT INTO import_batches (filename, imported_at, accepted_rows, skipped_rows, group_id) VALUES (?, ?, 0, 0, ?)",
            (file_storage.filename or "expenses_export.csv", now, group_id),
        ).lastrowid
        for row_num, row in enumerate(reader, start=2):
            row_anomalies: list[dict] = []
            expense_date, date_code = parse_date(row.get("date", ""))
            if date_code:
                add_anomaly(row_anomalies, row_num, date_code, "warning" if expense_date else "error", f"Date '{row.get('date')}' needed special handling.", "Use DD-MM-YYYY; parse Mar-14 as 2026-03-14; reject unparseable dates.", "normalized" if expense_date else "skipped")
            if not expense_date:
                skipped += 1
                anomalies += row_anomalies
                continue
            if row.get("notes", "").lower().find("format is a mess") >= 0:
                add_anomaly(row_anomalies, row_num, "ambiguous_date", "warning", "Notes say this date may be ambiguous.", "Use the parsed DD-MM-YYYY date but surface the ambiguity.", "accepted_as_dd_mm_yyyy", True)
            payer = normalize_name(row.get("paid_by"))
            if not payer:
                add_anomaly(row_anomalies, row_num, "missing_payer", "error", "Paid_by is blank.", "Reject expenses where the payer cannot be known.", "skipped")
                skipped += 1
                anomalies += row_anomalies
                continue
            if payer != (row.get("paid_by") or "").strip():
                add_anomaly(row_anomalies, row_num, "payer_name_normalized", "info", f"Payer '{row.get('paid_by')}' normalized to '{payer}'.", "Normalize known aliases/casing/whitespace.", "normalized")
            amount = parse_amount(row.get("amount", ""), row_num, row_anomalies)
            if amount is None:
                skipped += 1
                anomalies += row_anomalies
                continue
            currency = (row.get("currency") or "").strip().upper()
            if not currency:
                currency = "INR"
                add_anomaly(row_anomalies, row_num, "missing_currency", "warning", "Currency is blank.", "Default blank currency to INR because surrounding household rows are INR.", "defaulted_to_INR", True)
            fx = USD_TO_INR if currency == "USD" else Decimal("1")
            if currency not in {"INR", "USD"}:
                add_anomaly(row_anomalies, row_num, "unsupported_currency", "error", f"Currency '{currency}' is unsupported.", "Reject currencies without an exchange-rate policy.", "skipped")
                skipped += 1
                anomalies += row_anomalies
                continue
            if currency == "USD":
                add_anomaly(row_anomalies, row_num, "foreign_currency", "info", "USD expense converted to INR.", f"Use fixed assignment FX rate 1 USD = INR {USD_TO_INR}.", "converted")
            people = parse_people(row.get("split_with"))
            for raw, normalized in zip([p for p in (row.get("split_with") or "").split(";") if p.strip()], people):
                if raw.strip() != normalized:
                    add_anomaly(row_anomalies, row_num, "participant_name_normalized", "info", f"Participant '{raw.strip()}' normalized to '{normalized}'.", "Normalize known participant aliases.", "normalized")
            inactive = [p for p in people if not active_on(p, expense_date)]
            if inactive:
                add_anomaly(row_anomalies, row_num, "membership_boundary", "warning", f"Inactive participant(s) on {expense_date}: {', '.join(inactive)}.", "Remove inactive household members from the split; keep guests active only for trip dates.", "adjusted_split", True)
                people = [p for p in people if active_on(p, expense_date)]
            if row.get("description", "").lower().find("paid") >= 0 and row.get("split_type", "").strip() == "":
                paid_to = parse_people(row.get("split_with"))
                conn.execute(
                    "INSERT INTO payments (group_id, batch_id, source_row, payment_date, paid_by, paid_to, amount_inr_cents, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (group_id, batch_id, row_num, expense_date, payer, paid_to[0] if paid_to else "Unknown", cents(amount), row.get("notes")),
                )
                add_anomaly(row_anomalies, row_num, "settlement_in_expense_file", "warning", "Settlement was logged in the expense export.", "Import as payment, not as an expense.", "recorded_payment")
                accepted += 1
                anomalies += row_anomalies
                continue
            amount_inr = money(amount * fx)
            parsed = {"date": expense_date, "amount": amount_inr, "people": people}
            duplicate = detect_duplicate(row, parsed, seen_rows, row_num, row_anomalies)
            splits = split_amount(amount_inr, row.get("split_type", ""), people, row.get("split_details", ""), row_num, row_anomalies)
            if not splits:
                skipped += 1
                anomalies += row_anomalies
                continue
            status = "excluded" if duplicate and any(a["code"] == "duplicate_expense" for a in row_anomalies) else "accepted"
            expense_id = conn.execute(
                """INSERT INTO expenses
                (group_id, batch_id, source_row, expense_date, description, paid_by, amount_original_cents, currency, fx_rate, amount_inr_cents, split_type, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (group_id, batch_id, row_num, expense_date, row.get("description"), payer, cents(amount), currency, str(fx), cents(amount_inr), row.get("split_type"), status, row.get("notes")),
            ).lastrowid
            conn.execute("UPDATE expenses SET category=? WHERE id=?", (guess_category(row.get("description")), expense_id))
            for person, share in splits.items():
                conn.execute(
                    "INSERT INTO expense_splits (expense_id, person_name, share_cents, basis) VALUES (?, ?, ?, ?)",
                    (expense_id, person, cents(share), row.get("split_type")),
                )
            accepted += 1
            anomalies += row_anomalies
        for anomaly in anomalies:
            conn.execute(
                """INSERT INTO import_anomalies
                (batch_id, row_number, code, severity, message, policy, action, review_required)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (batch_id, anomaly["row_number"], anomaly["code"], anomaly["severity"], anomaly["message"], anomaly["policy"], anomaly["action"], anomaly["review_required"]),
            )
        conn.execute("UPDATE import_batches SET accepted_rows=?, skipped_rows=? WHERE id=?", (accepted, skipped, batch_id))
    return batch_id


def balances(group_id: int):
    owed = defaultdict(int)
    paid = defaultdict(int)
    with db() as conn:
        rows = conn.execute(
            """SELECT e.id, e.description, e.expense_date, e.paid_by, e.amount_inr_cents, s.person_name, s.share_cents
            FROM expenses e JOIN expense_splits s ON s.expense_id=e.id
            WHERE e.group_id=? AND e.status='accepted'
            ORDER BY e.expense_date, e.id""",
            (group_id,),
        ).fetchall()
        payments = conn.execute("SELECT * FROM payments WHERE group_id=?", (group_id,)).fetchall()
    trace = defaultdict(list)
    for row in rows:
        paid[row["paid_by"]] += row["amount_inr_cents"]
        owed[row["person_name"]] += row["share_cents"]
        trace[row["person_name"]].append(row)
    for p in payments:
        paid[p["paid_by"]] += p["amount_inr_cents"]
        owed[p["paid_to"]] += p["amount_inr_cents"]
    people = sorted(set(owed) | set(paid) | set(MEMBERSHIP_POLICY))
    net = {p: paid[p] - owed[p] for p in people}
    debtors = [[p, -v] for p, v in net.items() if v < 0]
    creditors = [[p, v] for p, v in net.items() if v > 0]
    settlements = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        amount = min(debtors[i][1], creditors[j][1])
        settlements.append({"from": debtors[i][0], "to": creditors[j][0], "amount": from_cents(amount)})
        debtors[i][1] -= amount
        creditors[j][1] -= amount
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return {p: from_cents(v) for p, v in net.items()}, settlements, trace


def filtered_expenses(group_id: int, filters: dict):
    query = ["SELECT * FROM expenses WHERE group_id=?"]
    params: list = [group_id]
    if filters.get("q"):
        query.append("AND lower(description) LIKE ?")
        params.append(f"%{filters['q'].lower()}%")
    if filters.get("person"):
        query.append("AND (paid_by=? OR id IN (SELECT expense_id FROM expense_splits WHERE person_name=?))")
        params.extend([filters["person"], filters["person"]])
    if filters.get("category"):
        query.append("AND category=?")
        params.append(filters["category"])
    if filters.get("status"):
        query.append("AND status=?")
        params.append(filters["status"])
    if filters.get("currency"):
        query.append("AND currency=?")
        params.append(filters["currency"])
    query.append("ORDER BY id DESC LIMIT 50")
    with db() as conn:
        return conn.execute(" ".join(query), params).fetchall()


def balance_delta_for_expense(expense, splits) -> dict[str, int]:
    if not expense or expense["status"] != "accepted":
        return {}
    delta = defaultdict(int)
    delta[expense["paid_by"]] += expense["amount_inr_cents"]
    for split in splits:
        delta[split["person_name"]] -= split["share_cents"]
    return dict(delta)


def balance_delta_for_payment(payment) -> dict[str, int]:
    if not payment:
        return {}
    return {
        payment["paid_by"]: payment["amount_inr_cents"],
        payment["paid_to"]: -payment["amount_inr_cents"],
    }


def row_impact(group_id: int, source_row: int):
    with db() as conn:
        expense = conn.execute("SELECT * FROM expenses WHERE group_id=? AND source_row=? ORDER BY id DESC LIMIT 1", (group_id, source_row)).fetchone()
        payment = conn.execute("SELECT * FROM payments WHERE group_id=? AND source_row=? ORDER BY id DESC LIMIT 1", (group_id, source_row)).fetchone()
        splits = conn.execute("SELECT * FROM expense_splits WHERE expense_id=?", (expense["id"],)).fetchall() if expense else []
    current = balance_delta_for_expense(expense, splits) if expense else balance_delta_for_payment(payment)
    preview = {}
    if expense:
        copied = dict(expense)
        copied["status"] = "excluded" if expense["status"] == "accepted" else "accepted"
        preview = balance_delta_for_expense(copied, splits)
    return {
        "expense": expense,
        "payment": payment,
        "current": {person: from_cents(amount) for person, amount in sorted(current.items())},
        "preview": {person: from_cents(amount) for person, amount in sorted(preview.items())},
    }


def batch_impact(batch_id: int):
    delta = defaultdict(int)
    with db() as conn:
        expenses = conn.execute("SELECT * FROM expenses WHERE batch_id=? AND status='accepted'", (batch_id,)).fetchall()
        payments = conn.execute("SELECT * FROM payments WHERE batch_id=?", (batch_id,)).fetchall()
        for expense in expenses:
            splits = conn.execute("SELECT * FROM expense_splits WHERE expense_id=?", (expense["id"],)).fetchall()
            for person, amount in balance_delta_for_expense(expense, splits).items():
                delta[person] += amount
        for payment in payments:
            for person, amount in balance_delta_for_payment(payment).items():
                delta[person] += amount
    return {person: from_cents(amount) for person, amount in sorted(delta.items())}


def spending_insights(group_id: int):
    with db() as conn:
        by_category = conn.execute(
            """SELECT category AS label, SUM(amount_inr_cents) AS total
            FROM expenses WHERE group_id=? AND status='accepted'
            GROUP BY category ORDER BY total DESC""",
            (group_id,),
        ).fetchall()
        by_person = conn.execute(
            """SELECT paid_by AS label, SUM(amount_inr_cents) AS total
            FROM expenses WHERE group_id=? AND status='accepted'
            GROUP BY paid_by ORDER BY total DESC""",
            (group_id,),
        ).fetchall()
        monthly = conn.execute(
            """SELECT substr(expense_date, 1, 7) AS label, SUM(amount_inr_cents) AS total
            FROM expenses WHERE group_id=? AND status='accepted'
            GROUP BY substr(expense_date, 1, 7) ORDER BY label""",
            (group_id,),
        ).fetchall()
        top_expenses = conn.execute(
            """SELECT * FROM expenses WHERE group_id=? AND status='accepted'
            ORDER BY amount_inr_cents DESC LIMIT 5""",
            (group_id,),
        ).fetchall()
    return {
        "by_category": chart_rows(by_category),
        "by_person": chart_rows(by_person),
        "monthly": chart_rows(monthly),
        "top_expenses": top_expenses,
    }


def chart_rows(rows):
    max_total = max([row["total"] for row in rows], default=0) or 1
    return [
        {"label": row["label"] or "Uncategorized", "total": row["total"], "width": max(4, round(row["total"] * 100 / max_total))}
        for row in rows
    ]


def person_ledger(group_id: int, person: str):
    events = []
    with db() as conn:
        expenses = conn.execute(
            """SELECT e.*, COALESCE(s.share_cents, 0) AS person_share
            FROM expenses e
            LEFT JOIN expense_splits s ON s.expense_id=e.id AND s.person_name=?
            WHERE e.group_id=? AND e.status='accepted' AND (e.paid_by=? OR s.person_name IS NOT NULL)
            ORDER BY e.expense_date, e.id""",
            (person, group_id, person),
        ).fetchall()
        payments = conn.execute(
            """SELECT * FROM payments
            WHERE group_id=? AND (paid_by=? OR paid_to=?)
            ORDER BY payment_date, id""",
            (group_id, person, person),
        ).fetchall()
    for expense in expenses:
        paid = expense["amount_inr_cents"] if expense["paid_by"] == person else 0
        owed = expense["person_share"] or 0
        events.append(
            {
                "date": expense["expense_date"],
                "kind": "Expense",
                "description": expense["description"],
                "paid": paid,
                "owed": owed,
                "sent": 0,
                "received": 0,
                "delta": paid - owed,
            }
        )
    for payment in payments:
        sent = payment["amount_inr_cents"] if payment["paid_by"] == person else 0
        received = payment["amount_inr_cents"] if payment["paid_to"] == person else 0
        events.append(
            {
                "date": payment["payment_date"],
                "kind": "Payment",
                "description": payment["notes"] or f"{payment['paid_by']} paid {payment['paid_to']}",
                "paid": 0,
                "owed": 0,
                "sent": sent,
                "received": received,
                "delta": sent - received,
            }
        )
    running = 0
    ledger = []
    for event in sorted(events, key=lambda item: (item["date"], item["kind"], item["description"])):
        running += event["delta"]
        event["running"] = running
        ledger.append(event)
    return ledger


def rescale_splits(conn, expense_id: int, old_total: int, new_total: int) -> None:
    splits = conn.execute("SELECT * FROM expense_splits WHERE expense_id=? ORDER BY id", (expense_id,)).fetchall()
    if not splits or old_total == 0:
        return
    allocated = 0
    for index, split in enumerate(splits):
        share = new_total - allocated if index == len(splits) - 1 else round(split["share_cents"] * new_total / old_total)
        allocated += share
        conn.execute("UPDATE expense_splits SET share_cents=? WHERE id=?", (share, split["id"]))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password_hash = sha256(request.form["password"].encode()).hexdigest()
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email=? AND password_hash=?", (email, password_hash)).fetchone()
        if user:
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))
        flash("Invalid login. Try admin@example.com / password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    group_id = int(request.args.get("group_id", 1))
    net, settlements, trace = balances(group_id)
    filters = {
        "q": request.args.get("q", "").strip(),
        "person": request.args.get("person", "").strip(),
        "category": request.args.get("category", "").strip(),
        "status": request.args.get("status", "").strip(),
        "currency": request.args.get("currency", "").strip(),
    }
    with db() as conn:
        groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
        expenses = filtered_expenses(group_id, filters)
        batches = conn.execute("SELECT * FROM import_batches ORDER BY id DESC LIMIT 5").fetchall()
        people = [row["person_name"] for row in conn.execute("SELECT DISTINCT person_name FROM group_memberships ORDER BY person_name").fetchall()]
        categories = [row["category"] for row in conn.execute("SELECT DISTINCT category FROM expenses WHERE group_id=? ORDER BY category", (group_id,)).fetchall()]
    insights = spending_insights(group_id)
    return render_template("dashboard.html", groups=groups, group_id=group_id, net=net, settlements=settlements, expenses=expenses, batches=batches, trace=trace, filters=filters, people=people, categories=categories, insights=insights)


@app.route("/groups", methods=["GET", "POST"])
@login_required
def groups():
    with db() as conn:
        if request.method == "POST":
            conn.execute("INSERT INTO groups (name, base_currency) VALUES (?, 'INR')", (request.form["name"].strip(),))
            flash("Group created.", "ok")
            return redirect(url_for("groups"))
        rows = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
        memberships = conn.execute("SELECT * FROM group_memberships ORDER BY group_id, joined_on").fetchall()
    return render_template("groups.html", groups=rows, memberships=memberships)


@app.route("/memberships", methods=["POST"])
@login_required
def add_membership():
    with db() as conn:
        conn.execute(
            "INSERT INTO group_memberships (group_id, person_name, joined_on, left_on) VALUES (?, ?, ?, ?)",
            (request.form["group_id"], request.form["person_name"].strip(), request.form["joined_on"], request.form.get("left_on") or None),
        )
    flash("Membership saved.", "ok")
    return redirect(url_for("groups"))


@app.route("/expenses/new", methods=["GET", "POST"])
@login_required
def new_expense():
    if request.method == "POST":
        group_id = int(request.form["group_id"])
        amount = money(request.form["amount"])
        people = parse_people(request.form["split_with"])
        row_anomalies = []
        inactive = membership_warnings(people, request.form["expense_date"])
        if inactive:
            flash("Membership warning: " + ", ".join(inactive) + " is outside the saved membership period for this date.", "error")
        shares = split_amount(amount, request.form["split_type"], people, request.form.get("split_details", ""), 0, row_anomalies)
        if not shares or row_anomalies:
            flash("Could not save expense: " + "; ".join(a["message"] for a in row_anomalies), "error")
        else:
            with db() as conn:
                expense_id = conn.execute(
                    """INSERT INTO expenses (group_id, expense_date, description, category, paid_by, amount_original_cents, currency, fx_rate, amount_inr_cents, split_type, status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, 'INR', '1', ?, ?, 'accepted', ?)""",
                    (group_id, request.form["expense_date"], request.form["description"], request.form["category"], normalize_name(request.form["paid_by"]), cents(amount), cents(amount), request.form["split_type"], request.form.get("notes")),
                ).lastrowid
                for person, share in shares.items():
                    conn.execute("INSERT INTO expense_splits (expense_id, person_name, share_cents, basis) VALUES (?, ?, ?, ?)", (expense_id, person, cents(share), request.form["split_type"]))
            flash("Expense saved.", "ok")
            return redirect(url_for("dashboard", group_id=group_id))
    with db() as conn:
        groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
    return render_template("expense_form.html", groups=groups)


@app.route("/people/<person_name>")
@login_required
def person_detail(person_name):
    group_id = int(request.args.get("group_id", 1))
    person = normalize_name(person_name)
    net, settlements, trace = balances(group_id)
    with db() as conn:
        paid_expenses = conn.execute(
            "SELECT * FROM expenses WHERE group_id=? AND paid_by=? AND status='accepted' ORDER BY expense_date DESC, id DESC",
            (group_id, person),
        ).fetchall()
        owed_splits = conn.execute(
            """SELECT e.*, s.share_cents FROM expense_splits s
            JOIN expenses e ON e.id=s.expense_id
            WHERE e.group_id=? AND e.status='accepted' AND s.person_name=?
            ORDER BY e.expense_date DESC, e.id DESC""",
            (group_id, person),
        ).fetchall()
        payments = conn.execute(
            "SELECT * FROM payments WHERE group_id=? AND (paid_by=? OR paid_to=?) ORDER BY payment_date DESC, id DESC",
            (group_id, person, person),
        ).fetchall()
    ledger = person_ledger(group_id, person)
    return render_template("person_detail.html", group_id=group_id, person=person, net=net.get(person, Decimal("0")), paid_expenses=paid_expenses, owed_splits=owed_splits, payments=payments, settlements=settlements, ledger=ledger)


@app.route("/expenses/<int:expense_id>")
@login_required
def expense_detail(expense_id):
    with db() as conn:
        expense = conn.execute("SELECT * FROM expenses WHERE id=?", (expense_id,)).fetchone()
        splits = conn.execute("SELECT * FROM expense_splits WHERE expense_id=? ORDER BY person_name", (expense_id,)).fetchall()
        anomalies = conn.execute("SELECT * FROM import_anomalies WHERE row_number=? ORDER BY id", (expense["source_row"],)).fetchall() if expense else []
    if not expense:
        flash("Expense not found.", "error")
        return redirect(url_for("dashboard"))
    return render_template("expense_detail.html", expense=expense, splits=splits, anomalies=anomalies)


@app.route("/export/balances.csv")
@login_required
def export_balances():
    group_id = int(request.args.get("group_id", 1))
    net, settlements, _ = balances(group_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["person", "net_inr"])
    for person, amount in net.items():
        writer.writerow([person, amount])
    writer.writerow([])
    writer.writerow(["from", "to", "amount_inr"])
    for item in settlements:
        writer.writerow([item["from"], item["to"], item["amount"]])
    return app.response_class(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=balances.csv"})


@app.route("/export/expenses.csv")
@login_required
def export_expenses():
    group_id = int(request.args.get("group_id", 1))
    filters = {
        "q": request.args.get("q", "").strip(),
        "person": request.args.get("person", "").strip(),
        "category": request.args.get("category", "").strip(),
        "status": request.args.get("status", "").strip(),
        "currency": request.args.get("currency", "").strip(),
    }
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "description", "category", "paid_by", "amount_inr", "currency", "status"])
    for row in filtered_expenses(group_id, filters):
        writer.writerow([row["expense_date"], row["description"], row["category"], row["paid_by"], from_cents(row["amount_inr_cents"]), row["currency"], row["status"]])
    return app.response_class(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=expenses.csv"})


@app.route("/payments", methods=["POST"])
@login_required
def payments():
    with db() as conn:
        conn.execute(
            "INSERT INTO payments (group_id, payment_date, paid_by, paid_to, amount_inr_cents, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (request.form["group_id"], request.form["payment_date"], normalize_name(request.form["paid_by"]), normalize_name(request.form["paid_to"]), cents(money(request.form["amount"])), request.form.get("notes")),
        )
    flash("Payment recorded.", "ok")
    return redirect(url_for("dashboard", group_id=request.form["group_id"]))


@app.route("/import", methods=["GET", "POST"])
@login_required
def import_view():
    if request.method == "POST":
        upload = request.files.get("csv_file")
        if not upload:
            flash("Choose a CSV file.", "error")
        else:
            batch_id = import_csv(upload, int(request.form["group_id"]))
            return redirect(url_for("import_report", batch_id=batch_id))
    with db() as conn:
        groups = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
    return render_template("import.html", groups=groups)


@app.route("/import/<int:batch_id>")
@login_required
def import_report(batch_id):
    with db() as conn:
        batch = conn.execute("SELECT * FROM import_batches WHERE id=?", (batch_id,)).fetchone()
        anomalies = conn.execute("SELECT * FROM import_anomalies WHERE batch_id=? ORDER BY row_number, id", (batch_id,)).fetchall()
    if not batch:
        flash("Import batch not found.", "error")
        return redirect(url_for("dashboard"))
    impacts = {a["id"]: row_impact(batch["group_id"] or 1, a["row_number"]) for a in anomalies}
    impact = batch_impact(batch_id)
    return render_template("import_report.html", batch=batch, anomalies=anomalies, impacts=impacts, impact=impact)


@app.route("/import/<int:batch_id>/rollback", methods=["POST"])
@login_required
def rollback_import(batch_id):
    now = datetime.utcnow().isoformat(timespec="seconds")
    with db() as conn:
        batch = conn.execute("SELECT * FROM import_batches WHERE id=?", (batch_id,)).fetchone()
        if not batch:
            flash("Import batch not found.", "error")
            return redirect(url_for("dashboard"))
        if batch["rolled_back_at"]:
            flash("This import was already rolled back.", "error")
            return redirect(url_for("import_report", batch_id=batch_id))
        linked_expenses = conn.execute("SELECT COUNT(*) AS count FROM expenses WHERE batch_id=?", (batch_id,)).fetchone()["count"]
        linked_payments = conn.execute("SELECT COUNT(*) AS count FROM payments WHERE batch_id=?", (batch_id,)).fetchone()["count"]
        if linked_expenses == 0 and linked_payments == 0:
            flash("This batch has no linked imported rows. Older imports created before rollback support cannot be safely undone.", "error")
            return redirect(url_for("import_report", batch_id=batch_id))
        conn.execute("DELETE FROM payments WHERE batch_id=?", (batch_id,))
        conn.execute("DELETE FROM expenses WHERE batch_id=?", (batch_id,))
        conn.execute(
            "UPDATE import_batches SET rolled_back_at=?, rolled_back_by=?, rollback_note=? WHERE id=?",
            (now, session.get("user_name", "user"), request.form.get("rollback_note", ""), batch_id),
        )
        conn.execute(
            "UPDATE import_anomalies SET review_required=0, resolved_at=?, resolved_action='rolled_back', resolution_note='Import batch rolled back.' WHERE batch_id=?",
            (now, batch_id),
        )
    flash("Import batch rolled back. Imported expenses, splits, and payments were removed.", "ok")
    return redirect(url_for("dashboard", group_id=batch["group_id"] or 1))


@app.route("/anomalies/<int:anomaly_id>/approve", methods=["POST"])
@login_required
def approve_anomaly(anomaly_id):
    with db() as conn:
        anomaly = conn.execute("SELECT * FROM import_anomalies WHERE id=?", (anomaly_id,)).fetchone()
        if not anomaly:
            flash("Anomaly not found.", "error")
            return redirect(url_for("dashboard"))
        conn.execute("UPDATE import_anomalies SET review_required=0, action=action || '_approved', resolved_at=?, resolved_action='approve' WHERE id=?", (datetime.utcnow().isoformat(timespec="seconds"), anomaly_id))
        if anomaly["code"] == "duplicate_expense":
            conn.execute("UPDATE expenses SET status='excluded' WHERE source_row=?", (anomaly["row_number"],))
    flash("Review action approved.", "ok")
    return redirect(url_for("import_report", batch_id=anomaly["batch_id"]))


@app.route("/anomalies/<int:anomaly_id>/resolve", methods=["POST"])
@login_required
def resolve_anomaly(anomaly_id):
    action = request.form.get("resolution_action", "approve")
    note = request.form.get("resolution_note", "")
    now = datetime.utcnow().isoformat(timespec="seconds")
    with db() as conn:
        anomaly = conn.execute("SELECT * FROM import_anomalies WHERE id=?", (anomaly_id,)).fetchone()
        if not anomaly:
            flash("Anomaly not found.", "error")
            return redirect(url_for("dashboard"))
        batch = conn.execute("SELECT * FROM import_batches WHERE id=?", (anomaly["batch_id"],)).fetchone()
        group_id = (batch["group_id"] if batch else None) or 1
        expense = conn.execute(
            "SELECT * FROM expenses WHERE group_id=? AND source_row=? ORDER BY id DESC LIMIT 1",
            (group_id, anomaly["row_number"]),
        ).fetchone()
        if action in {"accept_row", "exclude_row"}:
            if not expense:
                flash("No imported expense row exists for this anomaly. It may have been skipped during import.", "error")
                return redirect(url_for("import_report", batch_id=anomaly["batch_id"]))
            conn.execute("UPDATE expenses SET status=? WHERE id=?", ("accepted" if action == "accept_row" else "excluded", expense["id"]))
        elif action == "correct_payer":
            new_payer = normalize_name(request.form.get("new_payer"))
            if not new_payer or not expense:
                flash("Enter a payer for an imported expense row.", "error")
                return redirect(url_for("import_report", batch_id=anomaly["batch_id"]))
            conn.execute("UPDATE expenses SET paid_by=? WHERE id=?", (new_payer, expense["id"]))
        elif action == "change_currency":
            if not expense:
                flash("No imported expense row exists for this anomaly.", "error")
                return redirect(url_for("import_report", batch_id=anomaly["batch_id"]))
            currency = request.form.get("currency", "INR").upper()
            if currency not in {"INR", "USD"}:
                flash("Currency must be INR or USD.", "error")
                return redirect(url_for("import_report", batch_id=anomaly["batch_id"]))
            original = money(request.form.get("amount") or from_cents(expense["amount_original_cents"]))
            fx = USD_TO_INR if currency == "USD" else Decimal("1")
            new_total = cents(money(original * fx))
            old_total = expense["amount_inr_cents"]
            conn.execute(
                "UPDATE expenses SET currency=?, fx_rate=?, amount_original_cents=?, amount_inr_cents=? WHERE id=?",
                (currency, str(fx), cents(original), new_total, expense["id"]),
            )
            rescale_splits(conn, expense["id"], old_total, new_total)
        elif action == "merge_duplicate":
            keep_id = request.form.get("keep_expense_id")
            drop_id = request.form.get("drop_expense_id")
            if keep_id and drop_id and keep_id != drop_id:
                conn.execute("UPDATE expenses SET status='accepted' WHERE id=?", (keep_id,))
                conn.execute("UPDATE expenses SET status='excluded' WHERE id=?", (drop_id,))
            elif expense:
                conn.execute("UPDATE expenses SET status='excluded' WHERE id=?", (expense["id"],))
            else:
                flash("Choose duplicate rows to merge.", "error")
                return redirect(url_for("import_report", batch_id=anomaly["batch_id"]))
        else:
            action = "approve"
        conn.execute(
            """UPDATE import_anomalies
            SET review_required=0, resolved_at=?, resolved_action=?, resolution_note=?
            WHERE id=?""",
            (now, action, note, anomaly_id),
        )
    flash("Anomaly resolved and balances updated.", "ok")
    return redirect(url_for("import_report", batch_id=anomaly["batch_id"]))


@app.template_filter("rupees")
def rupees(value):
    return f"Rs {value:,.2f}"
    return f"₹{value:,.2f}"


@app.template_filter("cents")
def cents_filter(value):
    return f"Rs {from_cents(value):,.2f}"
    return f"₹{from_cents(value):,.2f}"


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
