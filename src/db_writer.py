import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "budget.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

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
    """
    Takes the edited DataFrame from st.data_editor, the original enriched
    transaction list (for fields not in the df), and the selected account name.
    Returns a summary dict with counts of inserted and skipped rows.
    """
    con = get_connection()
    cur = con.cursor()

    account_id = get_account_id(cur, account_name)
    imported_at = datetime.now().isoformat()

    # Build a lookup from description+date → original txn for dedup hash and type
    original_lookup = {
        (t["description_raw"], t["date"].strftime("%Y-%m-%d")): t
        for t in original_txns
    }

    inserted = 0
    skipped = 0

    for _, row in reviewed_df.iterrows():
        original = original_lookup.get((row["description"], row["date"]))
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
        except sqlite3.IntegrityError:
            # DedupeHash already exists — skip duplicate
            skipped += 1

    con.commit()
    con.close()
    return {"inserted": inserted, "skipped": skipped}