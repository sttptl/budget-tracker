"""
One-time migration: drop the BucketRules table and add BucketID column to categories.
Run from the project root: python drop_bucket_rules.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "budget.db"

def migrate():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("DROP TABLE IF EXISTS BucketRules")
    print("✅ Dropped BucketRules table.")

    # Add BucketID to categories while we're here (idempotent)
    existing_cols = [row[1] for row in cur.execute("PRAGMA table_info(categories)")]
    if "BucketID" not in existing_cols:
        cur.execute("ALTER TABLE categories ADD COLUMN BucketID INTEGER REFERENCES buckets(BucketID)")
        print("✅ Added BucketID column to categories.")
    else:
        print("ℹ️  BucketID column already exists on categories — skipped.")

    con.commit()
    con.close()
    print("Done.")

if __name__ == "__main__":
    migrate()