import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "budget.db"

def get_connection():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    return con

def get_category_id(cur, category_name: str) -> int:
    cur.execute("SELECT CategoryID FROM categories WHERE CategoryName = ?", (category_name,))
    row = cur.fetchone()
    if row:
        return row[0]
    # Category doesn't exist yet — create it
    cur.execute("INSERT INTO categories (CategoryName) VALUES (?)", (category_name,))
    return cur.lastrowid

def get_account_id(cur, account_name: str) -> int:
    cur.execute("SELECT AccountID FROM accounts WHERE AccountName = ?", (account_name,))
    row = cur.fetchone()
    return row[0] if row else None

def write_transactions(reviewed_df, original_txns: list[dict], account_name: str) -> dict:
    with open("debug_log.txt", "a") as f:
        f.write(f"DB path: {DB_PATH}\n")
    """
    Takes the edited DataFrame from st.data_editor, the original enriched
    transaction list (for fields not in the df), and the selected account name.
    Returns a summary dict with counts of inserted and skipped rows.
    """
    con = get_connection()
    cur = con.cursor()

    account_id = get_account_id(cur, account_name)
    imported_at = datetime.now().isoformat()

    original_lookup = {t["id"]: t for t in original_txns}

    inserted = 0
    skipped = 0

    for _, row in reviewed_df.iterrows():
        original = original_lookup.get(row["txn_id"])
        if not original:
            continue

        # Detect manual override — compare category to original
        original_category = original.get("category", "Uncategorized")
        edited_category = row["category"]
        if edited_category != original_category:
            match_rule = "manual"
            confidence = 1.0
        else:
            match_rule = original.get("match_rule", "")
            confidence = original.get("confidence", 0.0)

        category_id = get_category_id(cur, edited_category)

        # Flip sign back to parser convention: positive = expense
        amount = -row["amount"]

        try:
            cur.execute("""
                INSERT INTO transactions (
                    DedupeHash, AccountID, Date, DescriptionRaw, Amount,
                    Type, CategoryID, MatchRule, Confidence, Notes,
                    SourceFile, ImportedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                original["id"],
                account_id,
                row["date"],
                row["description"],
                amount,
                original["type"],
                category_id,
                match_rule,
                confidence,
                row["notes"],
                original["source_file"],
                imported_at,
            ))
            inserted += 1
        #except sqlite3.IntegrityError:
            # DedupeHash already exists — skip duplicate
            #skipped += 1

        except sqlite3.IntegrityError as e:
            print(f"SKIPPED {original['id']} — {original['description_raw']} — reason: {e}")
            skipped += 1

    con.commit()
    con.close()
    return {"inserted": inserted, "skipped": skipped}
def write_chequing_transactions(
    income_df,
    expense_df,
    original_txns: list[dict],
    allocation_data: dict,
    account_name: str,
) -> dict:
    """
    Writes chequing income + expense transactions to the transactions table,
    and writes per-bucket allocation rows to income_allocations for income rows.

    allocation_data shape:
      { txn_id: { bucket_name: { "percentage": float, "amount": float } } }
    """
    con = get_connection()
    cur = con.cursor()

    account_id  = get_account_id(cur, account_name)
    imported_at = datetime.now().isoformat()

    original_lookup = {t["id"]: t for t in original_txns}

    # Build bucket name → BucketID lookup
    cur.execute("SELECT BucketName, BucketID FROM buckets")
    bucket_id_map = {row[0]: row[1] for row in cur.fetchall()}

    inserted             = 0
    skipped              = 0
    allocations_written  = 0

    def _insert_txn(row, original, amount):
        """Insert one transaction row. Returns the new TransactionID or None if skipped."""
        original_category = original.get("category", "Uncategorized")
        edited_category   = row["category"]
        if edited_category != original_category:
            match_rule = "manual"
            confidence = 1.0
        else:
            match_rule = original.get("match_rule", "")
            confidence = original.get("confidence", 0.0)

        category_id = get_category_id(cur, edited_category)

        try:
            cur.execute("""
                INSERT INTO transactions (
                    DedupeHash, AccountID, Date, DescriptionRaw, Amount,
                    Type, CategoryID, MatchRule, Confidence, Notes,
                    SourceFile, ImportedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                original["id"],
                account_id,
                row["date"],
                row["description"],
                amount,
                original.get("type", ""),
                category_id,
                match_rule,
                confidence,
                row.get("notes", ""),
                original["source_file"],
                imported_at,
            ))
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None  # duplicate

    # ── Write expense rows ────────────────────────────────────────────────────
    for _, row in expense_df.iterrows():
        original = original_lookup.get(row["txn_id"])
        if not original:
            continue
        # Flip sign back to parser convention: positive = expense
        amount = -row["amount"]
        txn_id = _insert_txn(row, original, amount)
        if txn_id:
            inserted += 1
        else:
            skipped += 1

    # ── Write income rows + allocations ───────────────────────────────────────
    for _, row in income_df.iterrows():
        original = original_lookup.get(row["txn_id"])
        if not original:
            continue
        # Income: amount is positive in UI (money in), flip to negative for DB
        # (parser convention: positive = expense, negative = income)
        amount = -row["amount"]
        txn_id = _insert_txn(row, original, amount)
        if txn_id is None:
            skipped += 1
            continue
        inserted += 1

        # Write allocation rows for this income transaction
        orig_id     = original["id"]
        allocations = allocation_data.get(orig_id, {})
        for bucket_name, values in allocations.items():
            bucket_id = bucket_id_map.get(bucket_name)
            if bucket_id is None:
                continue
            cur.execute("""
                INSERT INTO income_allocations
                    (TransactionID, BucketID, Percentage, Amount)
                VALUES (?, ?, ?, ?)
            """, (
                txn_id,
                bucket_id,
                values["percentage"],
                values["amount"],
            ))
            allocations_written += 1

    con.commit()
    con.close()
    return {
        "inserted":            inserted,
        "skipped":             skipped,
        "allocations_written": allocations_written,
    }
