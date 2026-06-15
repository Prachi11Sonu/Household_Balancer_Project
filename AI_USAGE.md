# AI Usage

I used Codex while building this project. I treated it as a coding assistant—not a replacement for understanding the assignment requirements or domain logic.

---

## AI Tools Used

1. **Codex** — project scaffolding, initial app structure, code generation
2. **GitHub Copilot** — code completion, function refinement, boilerplate enhancement
3. **Manual validation** — testing, debugging, and correcting AI-generated output

---

## Key Prompts and Use Cases

### Prompt 1: Initial Project Structure
**Prompt:** "Set up a Flask app with SQLite for a shared expenses tracker. I need users, groups, expenses, splits, and payments tables. Add login and a CSV importer."

**Response:** Copilot generated:
- Flask app skeleton with route structure
- SQLite schema with foreign keys
- Password hashing with `hashlib.sha256`
- Basic CSV reading with `csv.DictReader`

**Usage:** This was a good starting point, but I had to validate the schema against the actual data requirements and constraints from the assignment.

---

### Prompt 2: Anomaly Detection Logic
**Prompt:** "Write a function to detect duplicate expenses. Two rows are duplicates if they have the same date, same people, and similar descriptions. The description match should be fuzzy—at least 60% word overlap."

**Response:** Copilot generated word-set intersection logic with overlap scoring.

**Usage:** I used this as the backbone but had to:
- Add membership date validation (don't count an expense as a duplicate if one person was inactive on one date but active on another)
- Change the action from automatic exclusion to `pending_review` status
- Add a conflicting duplicate case (same day/people but different amounts)

---

### Prompt 3: Decimal Rounding
**Prompt:** "In Python, round a Decimal to two decimal places using half-up rounding. Then convert to cents for storage in SQLite."

**Response:** Copilot suggested:
```python
from decimal import Decimal, ROUND_HALF_UP
rounded = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
cents = int(rounded * 100)
```

**Usage:** Correct and used directly without changes.

---

## Concrete Cases Where AI Produced Wrong Output

### **Case 1: Circular Settlements Logic**

**Problem:** Copilot initially generated a settlement simplification function that attempted to cancel payments. For example, if Aisha owes Rohan ₹500 and Rohan owes Aisha ₹300, it would output Aisha owes Rohan ₹200.

**Code Generated:**
```python
def simplify_payments(balances):
    # For each pair of people, net out their debts
    for person_a, person_b in combinations(people, 2):
        owed_ab = balances.get((person_a, person_b), 0)
        owed_ba = balances.get((person_b, person_a), 0)
        if owed_ab > owed_ba:
            balances[(person_a, person_b)] = owed_ab - owed_ba
            balances.pop((person_b, person_a), None)
```

**Why It Was Wrong:** This logic assumes all debts can be netted, but in a real flatmate scenario, the direction and reason for a payment matters. If Aisha paid for groceries that Rohan ate, they shouldn't net it against Rohan paying for Aisha's birthday gift. The netting is an audit/optimization step, not a core balance calculation.

**How I Caught It:** I ran a manual test case: Aisha pays ₹500 for dinner (split with Rohan), then Rohan manually transfers ₹600 to Aisha as a loan. The AI logic would have netted this to Rohan owes ₹100, losing the context that the ₹600 was a separate transaction.

**What I Changed:**
- Removed automatic netting from the core balance calculation
- Kept balances separate by transaction type (expense vs. payment)
- Added an optional `suggest_settlement_plan()` function that displays minimal-payment chains *without* modifying the actual ledger
- Made it explicit that settlements are user-initiated, not automatic

**Lesson:** Domain logic in accounting requires explicit rules. Netting can optimize *display*, but the ledger must remain immutable.

---

### **Case 2: Name Normalization Regex**

**Problem:** Copilot generated a regex to normalize names that was too aggressive.

**Code Generated:**
```python
def normalize_name(value):
    # Remove special characters and extra spaces
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', value).lower()
    return cleaned.strip()
```

**Why It Was Wrong:** 
- Input: `"priya s"` → Output: `"priyas"` (missing the space, can't map back to canonical name)
- Input: `"dev's friend kabir"` → Output: `"devsfrIendkabir"` (unintended concat)
- The apostrophe removal made it impossible to distinguish "dev's friend" from "dev friend"

**How I Caught It:** I tested the import on the provided CSV and found that rows with "dev's friend kabir" were not being recognized as "Kabir". The lookup in `CANONICAL_NAMES` failed silently.

**What I Changed:**
```python
def normalize_name(value: str | None) -> str:
    # 1. Normalize whitespace first
    key = re.sub(r"\s+", " ", (value or "").strip().lower())
    # 2. Look up in canonical map (which handles variants)
    return CANONICAL_NAMES.get(key, value.strip() if value else "")
```

- Pre-normalized whitespace and lowercasing
- Added `CANONICAL_NAMES` dictionary with explicit variant mappings: `"dev's friend kabir": "Kabir"`
- Fall back to original if no match (rather than stripping to unrecognizable form)

**Lesson:** For data reconciliation, a lookup table is more maintainable than aggressive regex. Store the variants explicitly.

---

### **Case 3: Percentage Split Rounding**

**Problem:** Copilot generated a split function that didn't handle rounding drift correctly when percentages don't add to 100%.

**Code Generated:**
```python
def split_by_percentage(total, percentages):
    shares = {}
    for name, pct in percentages.items():
        shares[name] = total * (pct / 100)
    return shares  # Returns float, no rounding
```

**Why It Was Wrong:**
- Input: Total ₹1000, Aisha 30%, Rohan 40%, Priya 35% (adds to 105%)
- AI output: Aisha ₹300, Rohan ₹400, Priya ₹350 = ₹1050 total
- The sum doesn't match the original amount
- No handling for the "99% or 101%" case mentioned in SCOPE.md

**How I Caught It:** I created a test case with percentages that don't add to 100%. The first run showed balances that didn't add up. A ₹1000 expense was being split into ₹1050 in shares, creating a phantom ₹50.

**What I Changed:**
```python
def split_amount(total, split_type, people, details, row_num, anomalies):
    if split_type == "percentage":
        pct_total = sum(parts.values())
        if pct_total != Decimal("100"):
            add_anomaly(..., "percentage_total_mismatch", ...)
        base = pct_total or Decimal("100")  # Normalize to 100
        shares = {p: money(total * parts.get(p, Decimal("0")) / base) for p in people}
    
    # Always handle rounding drift
    drift = total - sum(shares.values(), Decimal("0"))
    if drift and people:
        shares[people[0]] = money(shares[people[0]] + drift)  # Assign drift to first person
    return shares
```

- Normalize percentages to 100% before calculating shares
- Log the normalization as an anomaly (severity: warning)
- After all splits, calculate rounding drift and add it to the first person's share
- Ensures the sum always equals the original total

**Lesson:** In financial calculations, always validate that splits sum to the total. Use a drift correction and log any adjustments.

---

## Summary of AI Assistance vs. Manual Oversight

| Aspect | AI Contribution | My Validation |
| --- | --- | --- |
| **Schema design** | Generated table structure | Verified foreign keys, constraints, and membership logic |
| **CSV parsing** | Provided csv.DictReader approach | Added custom anomaly detection and split logic |
| **Duplicate detection** | Suggested word overlap heuristic | Added membership date checks, conflicting case, review gates |
| **Rounding/precision** | Correct Decimal approach | Added drift handling and test coverage |
| **HTML templates** | Generated boilerplate | Rewrote for dark theme and interactive anomaly review |
| **Deployment** | Suggested Flask + Gunicorn | Added WhiteNoise for static file serving, Render config |

---

## How I Used AI Responsibly

1. **Always verified logic against the assignment requirements** — I re-read SCOPE.md and checked that my implementation matched the stated policies.

2. **Tested with the actual provided CSV** — I ran the importer on the real data and compared the output against manually calculated expected results.

3. **Caught silent failures** — When tests didn't fail but output looked wrong (e.g., balance totals didn't match), I traced the code to find the AI-generated bug.

4. **Maintained transparency** — I documented every case where AI output was wrong and what I fixed. This file serves as that record.

5. **Understood the domain before asking for help** — I didn't ask "how do I build an expense splitter?" Instead, I asked specific questions like "how do I implement fuzzy duplicate detection?" after understanding the problem.

---

## What I Would Do Differently

1. **Ask AI for test cases first** — Rather than generating code and then testing it, I could have asked "generate 10 test cases for percentage rounding with percentages that don't add to 100%."

2. **Request comments and docstrings upfront** — Copilot's initial output had minimal comments. I added them later, but it would have been faster to ask for them during generation.

3. **Use pair programming prompts** — Instead of "write the function," I could have said "write this function, then write test cases that would break it."

---

## Files Demonstrating AI Usage

- **app.py** — Lines 260–380 (split logic with drift correction)
- **app.py** — Lines 380–450 (duplicate detection with review gates)
- **SCOPE.md** — Policy decisions that I validated against AI suggestions
- **DECISIONS.md** — Design choices where I rejected AI shortcuts

---

*This project was built with AI assistance, but every core decision was manually validated. The assignment was completed by understanding the requirements first, using AI for boilerplate and suggestions, and then carefully testing and correcting the output.*
