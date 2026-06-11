"""
Part A2 — TD Chequing CSV Parser
=================================
Reads a TD Chequing statement CSV export and returns a clean list of
normalized transaction dictionaries, ready for the categorizer.

CSV format: no header row, 4 columns:
  date | description | withdrawal (debit) | deposit (credit)

Usage:
    python chequing_parser.py
    -- or import and call parse_chequing_csv() from another script --
"""

import io
import hashlib
import pandas as pd
from pathlib import Path


def parse_chequing_csv(source) -> list[dict]:
    """
    Takes a file path (str/Path) or file-like object (e.g. from Streamlit uploader).
    Returns a list of clean transaction dicts.

    Sign convention (matches visa_parser):
      positive amount = money out (expense/withdrawal)
      negative amount = money in (income/deposit)

    Each dict also carries a 'flow' key:
      'expense' = withdrawal (debit column had a value)
      'income'  = deposit   (credit column had a value)
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Could not find file: {source}")
        file_to_read = path
        source_name = path.name
    else:
        file_to_read = io.TextIOWrapper(source, encoding="utf-8-sig")
        source_name = source.name

    df = pd.read_csv(
        file_to_read,
        header=None,
        names=["date", "description_raw", "withdrawal", "deposit"],
    )

    # ── Parse dates ────────────────────────────────────────────────────────
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d").dt.date

    # ── Normalize withdrawal/deposit into a single signed amount ───────────
    # Positive = expense (money out), negative = income (money in)
    # Mirrors the visa_parser convention: positive = expense
    df["withdrawal"] = pd.to_numeric(df["withdrawal"], errors="coerce").fillna(0)
    df["deposit"]    = pd.to_numeric(df["deposit"],    errors="coerce").fillna(0)
    df["amount"]     = df["withdrawal"] - df["deposit"]

    # ── Tag flow direction ─────────────────────────────────────────────────
    # 'income' for deposits (credit column), 'expense' for withdrawals (debit column)
    df["flow"] = df.apply(
        lambda row: "income" if row["deposit"] > 0 else "expense", axis=1
    )

    # ── Tag transaction type ───────────────────────────────────────────────
    def get_type(row):
        desc = str(row["description_raw"]).upper()
        if row["flow"] == "income":
            if "CREDIT MEMO" in desc:
                return "payroll"
            elif "DEPOSIT CANADA" in desc or "DEPOSIT TPS" in desc or "DEPOSIT GST" in desc:
                return "government"
            else:
                return "deposit"
        else:
            if "E-TRANSFER" in desc:
                return "etransfer"
            elif "INTERNET TRANSFER" in desc or "INTERNET BANKING" in desc:
                return "transfer"
            elif "SERVICE CHARGE" in desc:
                return "fee"
            else:
                return "debit"

    df["type"] = df.apply(get_type, axis=1)

    # ── Generate dedup hash ────────────────────────────────────────────────
    def make_id(row):
        raw = f"{row['date']}|{row['description_raw']}|{row['amount']}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    df["id"] = df.apply(make_id, axis=1)

    # ── Source file ────────────────────────────────────────────────────────
    df["source_file"] = source_name

    # ── Build output ───────────────────────────────────────────────────────
    columns = ["id", "date", "description_raw", "amount", "flow", "type", "source_file"]
    return df[columns].to_dict(orient="records")


# ── Run & preview ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pprint

    FILE_PATH = r"C:\Users\stuti\Downloads\NEW Budget Tracking Project\Imports\06_CHEQUING_Jun2025.csv"

    print(f"Reading: {FILE_PATH}\n")

    try:
        transactions = parse_chequing_csv(FILE_PATH)

        income   = [t for t in transactions if t["flow"] == "income"]
        expenses = [t for t in transactions if t["flow"] == "expense"]

        print(f"✅ Parsed {len(transactions)} total rows")
        print(f"   → {len(income)} income (deposits)")
        print(f"   → {len(expenses)} expenses (withdrawals)")
        print(f"   → Total in:  ${abs(sum(t['amount'] for t in income)):,.2f}")
        print(f"   → Total out: ${sum(t['amount'] for t in expenses):,.2f}")
        print()

        print("── Income transactions ───────────────────────────────")
        for t in income:
            print(f"  {t['date']}  {t['description_raw']:<60} ${abs(t['amount']):>8.2f}  [{t['type']}]")

        print()
        print("── Expense transactions ──────────────────────────────")
        for t in expenses:
            print(f"  {t['date']}  {t['description_raw']:<60} ${t['amount']:>8.2f}  [{t['type']}]")

        print()
        print("── First record (full) ───────────────────────────────")
        pprint.pprint(transactions[0])

    except FileNotFoundError as e:
        print(f"❌ {e}")