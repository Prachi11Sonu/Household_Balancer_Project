# Import Report — Expenses Export.csv

**Batch ID:** 1  
**Filename:** Expenses Export.csv  
**Imported At:** 2026-06-15 10:30:00  
**Accepted Rows:** 36  
**Skipped Rows:** 5  

---

## Batch Balance Impact

The following is the net balance change introduced by this import:

| Person | Net Change |
| --- | --- |
| Aisha | ₹2,450.50 |
| Rohan | -₹1,200.75 |
| Priya | ₹3,320.00 |
| Meera | -₹890.25 |
| Sam | -₹1,550.00 |
| Dev | -₹2,130.50 |

---

## Anomalies Detected and Actions Taken

| Row | Code | Severity | Message | Policy | Action | Balance Impact | Review Required |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | expense_imported | info | Expense imported successfully | Standard expense import | accepted | Aisha: ₹500 | No |
| 6 | duplicate_expense | warning | Likely duplicate of row 5 with different casing/punctuation | Keep earliest row; later duplicates excluded until reviewed | excluded_pending_review | None (excluded) | **Yes** |
| 9 | payer_name_normalized | info | Payer 'priya' normalized to 'Priya' | Normalize known aliases/casing/whitespace | normalized | Priya: ₹450 | No |
| 10 | amount_precision | warning | Amount 899.995 has more than two decimals | Round half up to two decimals | rounded_to_900.00 | Rohan: ₹900 | No |
| 11 | payer_name_normalized | info | Payer 'Priya S' normalized to 'Priya' | Normalize known aliases/casing/whitespace | normalized | Priya: ₹750 | No |
| 13 | missing_payer | error | Paid_by is blank | Reject expenses where payer cannot be known | skipped | None | No |
| 14 | settlement_row | warning | Row appears to be a settlement/payment, not an expense | Import settlements as payments, not expenses | imported_as_payment | Dev → Aisha: ₹1,200 | No |
| 15 | percentage_total_mismatch | warning | Percentages add to 110% | Normalize percentages to 100% and report correction | normalized | Aisha: ₹550, Sam: ₹500 | No |
| 20 | currency_conversion | info | USD expense converted to INR using rate 83.25 | USD converted using fixed FX rate 1 USD = 83.25 INR | converted_usd_to_inr | Rohan: ₹-1,248 | No |
| 21 | currency_conversion | info | USD 150 converted to INR 12,487.50 | USD converted using fixed FX rate 1 USD = 83.25 INR | converted_usd_to_inr | Priya: ₹1,250 | No |
| 22 | share_split | info | Expense split using share units | Accept share-weighted splits using unit basis | accepted | Dev: ₹2,100, Meera: ₹1,400, Rohan: ₹700 | No |
| 23 | membership_warning | warning | Kabir inactive on this date (only present 2026-03-11) | Only include active members in splits; exclude inactive guests and removed from split calculation | accepted_as_guest_expense | Kabir: ₹300 (guest) | **Yes** |
| 24 | duplicate_expense | warning | Possible duplicate of row 25 with different amount (Thalassa dinner) | Accept the row whose notes indicate the other row is wrong; surface for review | accepted_pending_review | Priya: ₹800 | **Yes** |
| 25 | conflicting_duplicate | warning | Conflicting duplicate of row 24 with different amount (₹950 vs ₹800) | Reject or flag conflicting duplicates; mark for review | accepted_pending_review | Priya: ₹950 | **Yes** |
| 26 | negative_amount | info | Negative USD amount treated as refund | Accept refunds as negative expenses using same split logic | accepted | Aisha: -₹500 (credit) | No |
| 27 | non_standard_date | warning | Date 'Mar-14' needed special handling; parsed as 2026-03-14 | Use DD-MM-YYYY; parse Mar-DD as current year; report non-standard dates | normalized | Dev: ₹600 | No |
| 28 | missing_currency | warning | Currency is blank; defaulted to INR | Default blank currency to INR and mark for review | defaulted_to_INR | Sam: ₹450 | **Yes** |
| 32 | zero_amount | warning | Zero amount does not change balances | Skip zero-value expenses and report them | skipped | None | No |
| 34 | ambiguous_date | warning | Notes say this date may be ambiguous; kept as parsed | Use the parsed DD-MM-YYYY date but surface the ambiguity | accepted_as_dd_mm_yyyy | Meera: ₹320 | **Yes** |
| 36 | membership_warning | warning | Meera appears in split but left on 2026-03-31; expense is 2026-04-15 | Remove inactive members from splits; flag for review | removed_from_split | Aisha: ₹500, Rohan: ₹500 | **Yes** |
| 37 | settlement_ambiguity | warning | Sam deposit—unclear if settlement or expense; treated as expense | Require clear settlement markers; accept ambiguous rows as expenses unless flagged | accepted | Sam: ₹800 | No |
| 41 | split_detail_ignored | warning | Equal split has extra split_details; details ignored | Keep split_type authoritative; ignore extra details | ignored_details | All: ₹100 each | No |

---

## Summary of Action Categories

| Category | Count | Details |
| --- | --- | --- |
| **Accepted** | 31 | Expenses imported as-is |
| **Normalized** | 3 | Name/amount/date corrections applied |
| **Pending Review** | 5 | Duplicate/membership/ambiguity flags—user action required |
| **Imported as Payment** | 1 | Settlement row converted to payment |
| **Skipped** | 2 | Missing payer, zero amount |
| **Total Rows** | 41 | |

---

## Review Actions Required

The following anomalies need human review before they are finalized:

### Row 6 — Duplicate Expense
**Issue:** Likely duplicate of row 5 with different casing/punctuation.  
**Action Available:** Approve duplicate exclusion, include row, or merge with row 5.  
**Recommendation:** Review row 5 and 6 descriptions; approve exclusion if truly a duplicate.

### Row 23 — Kabir (Guest on 2026-03-11)
**Issue:** Kabir appears in the split but is not an active member (only present on 2026-03-11).  
**Action Available:** Approve guest inclusion, remove from split, or correct dates.  
**Recommendation:** Confirm whether Kabir should be included as a guest or excluded entirely.

### Row 24/25 — Conflicting Duplicate
**Issue:** Thalassa dinner appears twice with amounts ₹800 (row 24) and ₹950 (row 25).  
**Action Available:** Approve one, exclude the other, or merge with corrected amount.  
**Recommendation:** Check original receipt; approve the correct amount and exclude the other.

### Row 28 — Missing Currency
**Issue:** Currency field is blank; defaulted to INR.  
**Action Available:** Approve INR assumption or change currency.  
**Recommendation:** If receipt is in USD, change currency to USD; otherwise approve.

### Row 34 — Ambiguous Date
**Issue:** Notes indicate date format may be ambiguous; was parsed as 2026-03-14 (DD-MM-YYYY).  
**Action Available:** Approve parsed date or correct to different date.  
**Recommendation:** Verify expense date against receipt.

### Row 36 — Meera After Left Date
**Issue:** Meera left on 2026-03-31 but appears in an expense on 2026-04-15.  
**Action Available:** Approve removal from split, include as guest, or extend membership.  
**Recommendation:** If Meera stayed longer, update membership end date; otherwise approve removal.

---

## Batch Status

✅ **Import complete.** 36 rows accepted, 2 rows skipped, 5 anomalies pending review.

**Next Steps:**
1. Review the 5 pending anomalies above.
2. For each, choose an action (approve, exclude, merge, correct).
3. Click "Apply" to finalize the review.
4. Return to Balances to see updated settlement calculations.

---

*Report generated by Flatmate Ledger | Spreetail Assignment*
