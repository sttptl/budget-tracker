"""
Part A — TD Visa CSV Parser
============================
Reads a TD Visa statement CSV export and returns a clean list of
normalized transaction dictionaries, ready for Part B (categorizer).

Usage:
    python visa_parser.py
    -- or import and call parse_visa_csv() from another script --
"""

import pandas as pd
import hashlib
import re
from pathlib import Path


# ── 1. THE MAIN FUNCTION ───────────────────────────────────────────────────────

def parse_visa_csv(file_path: str) -> list[dict]:
    """
    Takes a path to a TD Visa CSV export.
    Returns a list of clean transaction dicts.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Could not find file: {file_path}")

    # ── Step 1: Read the raw CSV (TD exports no header row) ────────────────────
    df = pd.read_csv(
        path,
        header=None,
        names=["date", "description_raw", "debit", "credit", "card"],
    )

    # ── Step 2: Parse dates ────────────────────────────────────────────────────
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date

    # ── Step 3: Normalize debit/credit into a single signed amount ─────────────
    # Positive = money you spent. Negative = payment or refund coming back.
    df["debit"]  = pd.to_numeric(df["debit"],  errors="coerce").fillna(0)
    df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0)
    df["amount"] = df["debit"] - df["credit"]

    # ── Step 4: Tag the transaction type ──────────────────────────────────────
    def get_type(row):
        desc = str(row["description_raw"]).upper()
        if "PAYMENT THANK YOU" in desc or "PAIEMEN T MERCI" in desc:
            return "payment"
        elif row["credit"] > 0:
            return "refund"
        else:
            return "debit"

    df["type"] = df.apply(get_type, axis=1)

    # ── Step 5: Clean up the merchant name and extract location ───────────────
    #df["merchant"]  = df["description_raw"].apply(extract_merchant)
    #df["location"]  = df["description_raw"].apply(extract_location)

    # ── Step 6: Generate a unique ID per transaction (for dedup later) ─────────
    def make_id(row):
        raw = f"{row['date']}|{row['description_raw']}|{row['amount']}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    df["id"] = df.apply(make_id, axis=1)

    # ── Step 7: Extract last 4 of card (TD masks everything, but keep it) ─────
    df["card_last4"] = df["card"].str.strip()

    # ── Step 8: Add source file name for traceability ─────────────────────────
    df["source_file"] = path.name

    # ── Step 9: Build final output list ───────────────────────────────────────
    columns = [
        "id", "date", "description_raw", "amount", "type", "card_last4", "source_file"
    ]

    transactions = df[columns].to_dict(orient="records")
    return transactions


# ── 2. HELPER FUNCTIONS ────────────────────────────────────────────────────────

def extract_merchant(description: str) -> str:
    desc = str(description).strip()

    # Remove store numbers like #3333
    desc = re.sub(r'#\w+', '', desc)
    # Remove order codes like Q04
    desc = re.sub(r'\bQ\d{2}\b', '', desc)
    # Remove phone numbers
    desc = re.sub(r'\d{3}-\d{3}-\d{4}', '', desc)
    # Remove URL-like patterns (amazon.ca/pri, WWW.AMAZON.CA)
    desc = re.sub(r'\S*\.\S*/\S*', '', desc)   # anything/path
    desc = re.sub(r'WWW\.\S+', '', desc)
    # Remove stuff after * (e.g. CA*NA5I28YY2)
    desc = re.sub(r'\*\S+', '', desc)

    # Strip the trailing "CITY, XX" — province is always exactly 2 uppercase letters
    # followed by end of string. City is the word(s) immediately before the comma.
    desc = re.sub(r'\s+\S[\w\s\.\-]*,\s*[A-Z]{2}\s*$', '', desc.strip())

    return re.sub(r'\s+', ' ', desc).strip().title() or str(description).strip()


def extract_location(description: str) -> str:
    desc = str(description).strip()
    # Match: CITY NAME, XX at the very end (province = exactly 2 uppercase letters)
    match = re.search(r'((?:[A-Z][A-Z\s\.\-]+)),\s*([A-Z]{2})\s*$', desc)
    if match:
        city = match.group(1).strip().title()
        province = match.group(2)
        return f"{city}, {province}"
    return ""

# ── 3. RUN IT & PRINT RESULTS ─────────────────────────────────────────────────

if __name__ == "__main__":

    FILE_PATH = r"C:\Users\stuti\Downloads\NEW Budget Tracking Project\Imports\04_VISA_Apr2025.csv"

    print(f"Reading: {FILE_PATH}\n")

    try:
        transactions = parse_visa_csv(FILE_PATH)

        # Split into expenses vs payments for the summary
        expenses = [t for t in transactions if t["type"] == "debit"]
        payments = [t for t in transactions if t["type"] == "payment"]
        refunds  = [t for t in transactions if t["type"] == "refund"]

        print(f"✅ Parsed {len(transactions)} total rows")
        print(f"   → {len(expenses)} expenses")
        print(f"   → {len(payments)} payments")
        print(f"   → {len(refunds)} refunds")
        print(f"   → Total spent: ${sum(t['amount'] for t in expenses):,.2f}")
        print()

        # Print first 5 transactions as a preview
        print("── First 5 transactions ──────────────────────────────")
        for t in transactions[:5]:
            print(f"  {t['date']}  {t['description_raw']:<45} ${t['amount']:>8.2f}  [{t['type']}]")

        print()
        print("── Full output (first record) ────────────────────────")
        import pprint
        pprint.pprint(transactions[0])

    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
        print("   Double-check the FILE_PATH at the bottom of this script.")