"""
One-time setup: seeds buckets and categories (with bucket assignments) into the DB.
Run after db_setup.py and drop_bucket_rules.py, before seed_rules.py.

Usage: python -m src.seed_buckets_and_categories
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "budget.db"

# BucketID → BucketName (for reference)
# 1 = Big Spend
# 2 = Education
# 3 = Bills
# 4 = Pocket Money
# 5 = Savings
# 6 = Beauty

BUCKETS = [
    "Big Spend",    # 1
    "Education",    # 2
    "Bills",        # 3
    "Pocket Money", # 4
    "Savings",      # 5
    "Beauty",       # 6
]

# (CategoryName, BucketID)
CATEGORIES = [
    ("Clothing",         4),
    ("Coffee",           4),
    ("Education",        2),
    ("Fitness",          4),
    ("Gas & Fuel",       3),
    ("Groceries",        3),
    ("Payment",          4),
    ("Restaurants",      4),
    ("Shopping",         4),
    ("Transit",          3),
    ("CPA",              2),
    ("Socializing",      4),
    ("Skincare",         4),
    ("Flights",          1),
    ("Hotels",           1),
    ("Trip",             1),
    ("Concerts & Shows", 1),
    ("Side Hustle",      2),
    ("Subscriptions",    4),
    ("Donations",        3),
    ("Books",            4),
    ("Gifts",            1),
    ("Wifi",             3),
    ("Food",             4),
    ("Hair Salon",       6),
]


def seed():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # ── Buckets ───────────────────────────────────────────────────────────────
    for bucket in BUCKETS:
        cur.execute("INSERT OR IGNORE INTO buckets (BucketName) VALUES (?)", (bucket,))
    print(f"✅ Seeded {len(BUCKETS)} buckets.")

    # ── Categories ────────────────────────────────────────────────────────────
    seeded = 0
    for cat_name, bucket_id in CATEGORIES:
        cur.execute("""
            INSERT INTO categories (CategoryName, BucketID)
            VALUES (?, ?)
            ON CONFLICT(CategoryName) DO UPDATE SET BucketID = excluded.BucketID
        """, (cat_name, bucket_id))
        seeded += 1

    print(f"✅ Seeded {seeded} categories with bucket assignments.")

    con.commit()
    con.close()
    print("Done.")


if __name__ == "__main__":
    seed()