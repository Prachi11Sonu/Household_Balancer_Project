# Decisions

This file records the main choices I made while building the app. I wrote these down because most of the assignment is not just "calculate a number", but deciding what to do when the data is messy.

## 1. Keep The Stack Small

I used Flask and SQLite.

I considered building a React frontend with a separate API, but that felt like extra moving parts for this assignment. The live review will probably focus on the importer and the balance math, so I wanted those parts to stay easy to follow in one codebase.

SQLite still satisfies the relational database requirement. The schema uses separate tables for expenses, splits, payments, memberships, import batches, and anomalies.

## 2. Store Import Problems Instead Of Only Showing Them

Every anomaly found during import is written to `import_anomalies`.

I considered only displaying warnings on the import page, but then the report would disappear after refresh. Keeping anomalies in the database makes the import auditable and lets the reviewer trace a CSV row later.

## 3. Use A Fixed USD Rate

I used:

```text
1 USD = INR 83.25
```

The CSV has USD expenses from the Goa trip. A live exchange-rate API would make the result change depending on the day the import runs, which is bad for a review assignment. A fixed documented rate makes the math repeatable.

## 4. Do Not Guess A Missing Payer

Rows with no payer are skipped.

For example, "House cleaning supplies" has no `paid_by`. It would be possible to guess from the notes, but that would create a fake debt. I chose to surface it as an error and skip the row.

## 5. Treat Settlements As Payments

The row "Rohan paid Aisha back" is not an expense. I import it into `payments`, not `expenses`.

This matters because expenses create shares for multiple people, while a payment only moves balance between two people.

## 6. Membership Dates Matter

The app has membership windows for Aisha, Rohan, Priya, Meera, Sam, Dev, and Kabir.

If someone appears in `split_with` outside their active dates, the importer flags it and removes them from that split. This is mainly for Meera after March and Sam before he moved in.

## 7. Duplicate Rows Need Review

I did not permanently delete duplicate-looking rows during import.

Exact likely duplicates are marked as excluded and review-required. Conflicting duplicates are accepted but flagged. This follows Meera's request: the app should clean up duplicates, but she should be able to approve what changed.

## 8. Split Type Is The Source Of Truth

If `split_type` says `equal`, the app uses an equal split even if `split_details` has extra text.

That happens in the furniture row. I chose this because the CSV has a dedicated `split_type` column, so it should control how the split is interpreted. The extra detail is still reported as an anomaly.

## 9. Use Decimal For Money

I used Python `Decimal` and round half-up to two decimal places.

Using floats for money can create small errors that are hard to explain in a balance review. Decimal keeps the settlement numbers stable.
