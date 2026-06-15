# AI Usage

I used Codex while building this project. I treated it as a coding assistant, not as a replacement for understanding the assignment.

## Where I Used It

- Reading the assignment requirements.
- Listing likely data problems in the CSV.
- Drafting the first version of the Flask app.
- Checking the import flow with the provided CSV.
- Cleaning up the UI and documentation.

## Prompts I Used

- "build a project as per the requirements mentioned in the pdf"
- I pasted the full assignment text after the PDF extraction was unnecessary.
- "change the theme to this"
- "i want dark mode"

## Things I Had To Correct

1. The first attempt spent time trying to extract the PDF even though I later pasted the requirements directly. I switched to the pasted assignment text as the source of truth.

2. The first dashboard had a placeholder expense link. I noticed that this would not satisfy Rohan's request to trace balances, so I added an expense detail page with per-person shares.

3. The duplicate handling was initially too automatic. Since Meera specifically asked to approve cleanup, I changed duplicate actions so they are surfaced in the import report and marked for review.

4. I had to clarify how manual split entry works. `unequal` means exact rupee amounts, while `share` means ratio-based weights.

## Files To Review

- `app.py`: implementation.
- `SCOPE.md`: anomaly policy.
- `DECISIONS.md`: design tradeoffs.

Before submitting, I would re-run the import from the UI and make sure I can explain `import_csv`, `split_amount`, `detect_duplicate`, and `balances` without relying on AI output.
