# Scope And Data Notes

This is my anomaly log for the provided `Expenses Export.csv`, plus the schema summary. The importer is intentionally conservative: it accepts rows when the policy is clear, skips rows when the missing data would require a guess, and stores every issue in the import report.

## Import Policies

- The app's base currency is INR.
- USD expenses are converted using `1 USD = INR 83.25`.
- Amounts are parsed with `Decimal`, then rounded half-up to two decimal places.
- Normal dates should be `DD-MM-YYYY`.
- `Mar-14` is accepted as `2026-03-14`, but reported.
- Blank currency is assumed to be INR and marked for review.
- Blank payer is not guessed; the row is skipped.
- Settlements are imported as payments.
- Negative amounts are treated as refunds.
- Zero amount rows are skipped because they do not affect balances.
- Known name variants are normalized, such as `priya`, `Priya S`, and `rohan `.
- Membership dates are enforced when calculating splits.
- Duplicate cleanup is review-required.

## Anomalies Found In The CSV

| Row | Problem | Handling |
| --- | --- | --- |
| 6 | Duplicate of row 5 with different casing/punctuation | Excluded as likely duplicate and marked for review |
| 9 | Payer is `priya` instead of `Priya` | Normalized |
| 10 | Amount is `899.995` | Rounded half-up to two decimals |
| 11 | Payer is `Priya S` | Normalized to `Priya` |
| 13 | Missing payer | Skipped |
| 14 | Settlement logged in expense file | Imported as a payment |
| 15 | Percentages add to 110% | Normalized and reported |
| 20 | USD expense | Converted to INR |
| 21 | USD expense | Converted to INR |
| 22 | Weighted share split | Imported using share units |
| 23 | Kabir appears as a guest | Allowed only for the trip date |
| 24/25 | Thalassa dinner appears twice with different amounts | Flagged as conflicting duplicate |
| 26 | Negative USD amount | Treated as refund and converted |
| 27 | Date is `Mar-14` | Parsed as `2026-03-14` |
| 28 | Missing currency | Defaulted to INR and marked for review |
| 32 | Zero amount | Skipped |
| 34 | Date note says format is ambiguous | Parsed as DD-MM-YYYY and marked for review |
| 36 | Meera appears after moving out | Removed from split and marked for review |
| 37 | Sam deposit share | Imported as an expense because the row is not clearly marked as a settlement |
| 41 | `equal` split has extra split details | Equal split is used; details are ignored and reported |

The import report may contain more than one anomaly for a row. For example, one row can have both a normalized name and a currency conversion.

## Schema Summary

`users`
: Demo login account.

`groups`
: Expense groups. The seeded group is `Flatmates`.

`group_memberships`
: Membership periods with `joined_on` and optional `left_on`.

`expenses`
: One row per imported or manually created expense. Stores original currency, FX rate, INR amount, source CSV row, and status.

`expense_splits`
: One row per person share for each expense.

`payments`
: Settlements or repayments between two people.

`import_batches`
: One row per CSV import.

`import_anomalies`
: The import report. Stores row number, issue code, severity, policy, action taken, and whether review is still required.
