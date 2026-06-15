"""
One-time setup: seeds buckets, categories, and category rules into the DB.
Run after db_setup.py and drop_bucket_rules.py.

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

# (Pattern, CategoryName, MatchType, Priority)
RULES = [
    ("Reitmans",                                 "Clothing",         "regex", 80),
    ("A&W",                                      "Food",             "regex", 80),
    ("WAL-MART",                                 "Groceries",        "regex", 80),
    ("WENDY'S",                                  "Food",             "regex", 80),
    ("WINNERS",                                  "Shopping",         "regex", 80),
    ("YESSTYLE",                                 "Skincare",         "regex", 80),
    ("VALUE VILLAGE",                            "Shopping",         "regex", 80),
    ("Uniqlo",                                   "Clothing",         "regex", 80),
    ("GO TVM TORONTO",                           "Transit",          "regex", 80),
    ("Oretta",                                   "Coffee",           "regex", 80),
    ("Brindle Food Co",                          "Food",             "regex", 80),
    ("TIM HORTON'S",                             "Coffee",           "regex", 80),
    ("TIM HORTONS",                              "Coffee",           "regex", 80),
    ("TICKETMASTER",                             "Concerts & Shows", "regex", 80),
    ("BELL CANADA",                              "Wifi",             "regex", 80),
    ("CHAPTERS",                                 "Books",            "regex", 80),
    ("CHARTERED PROFESSIONAL",                   "CPA",              "regex", 80),
    ("STARBUCKS COFFEE",                         "Coffee",           "regex", 80),
    ("COFFEE TIME BOLTON",                       "Coffee",           "regex", 80),
    ("SHOPPERS DRUG MART",                       "Skincare",         "regex", 80),
    ("SAMOSA AND SWEET FACTORY",                 "Food",             "regex", 80),
    ("Shelbys",                                  "Food",             "regex", 80),
    ("PRESTO MOBL TORONTO, ON",                  "Transit",          "regex", 80),
    ("PRESTO AUTL TORONTO, ON",                  "Transit",          "regex", 80),
    ("EUREST-OTPP-23336",                        "Coffee",           "regex", 80),
    ("FRESH BURRITO",                            "Food",             "regex", 80),
    ("Garage",                                   "Clothing",         "regex", 80),
    ("GORE MEADOWS BRAMPTON, ON",                "Fitness",          "regex", 80),
    ("GOA",                                      "Hair Salon",       "regex", 80),
    ("FRESHCO",                                  "Groceries",        "regex", 80),
    ("Amazon.ca Prime Member amazon.ca/pri, BC", "Subscriptions",    "regex", 80),
    ("Subway",                                   "Food",             "regex", 80),
    ("PIONEER",                                  "Gas & Fuel",       "regex", 80),
    ("MALTON - GO TVM MISSISSAUGA, ON",          "Transit",          "regex", 80),
    ("MOS MOS",                                  "Coffee",           "regex", 80),
    ("CHICHA SAN CHEN",                          "Coffee",           "regex", 80),
    ("PETRO-CANADA",                             "Gas & Fuel",       "regex", 80),
    ("SPENCER GIFTS",                            "Gifts",            "regex", 80),
    ("GYMSHARK",                                 "Gifts",            "regex", 80),
    ("HM CA0005 Vaughan, ON",                    "Clothing",         "regex", 80),
    ("MYCREDSMESCERTIF",                         "Education",        "regex", 80),
    ("PLATOS CLOSET",                            "Clothing",         "regex", 80),
    ("THE WATERING CAN",                         "Coffee",           "regex", 80),
    ("SQ *BEECHWOOD DOUGHNUTS",                  "Food",             "regex", 80),
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

    # ── Category Rules ────────────────────────────────────────────────────────
    cur.execute("SELECT CategoryName, CategoryID FROM categories")
    cat_map = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("DELETE FROM CategoryRules")

    inserted = 0
    skipped = 0
    for pattern, category, match_type, priority in RULES:
        cat_id = cat_map.get(category)
        if cat_id is None:
            print(f"  ⚠️  Category not found: '{category}' (pattern: '{pattern}') — skipped.")
            skipped += 1
            continue
        cur.execute(
            "INSERT INTO CategoryRules (Pattern, CategoryID, MatchType, Priority) VALUES (?, ?, ?, ?)",
            (pattern, cat_id, match_type, priority),
        )
        inserted += 1
    print(f"✅ Seeded {inserted} category rules." + (f" {skipped} skipped." if skipped else ""))

    con.commit()
    con.close()
    print("Done.")


if __name__ == "__main__":
    seed()