import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "budget.db"

CATEGORIES = [
    "Alcohol", "Clothing", "Coffee", "Education", "Fast Food", "Fitness",
    "Gas & Fuel", "Groceries", "Online Shopping", "Payment",
    "Professional Services", "Restaurants", "Shopping", "Transit",
    "Uncategorized", "Work Meals"
]

ACCOUNTS = [
    ("TD Visa", "credit", "TD"),
    ("TD Chequing", "chequing", "TD"),
]

def get_connection():
    return sqlite3.connect(DB_PATH)

def setup_db():
    con = get_connection()
    cur = con.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            AccountID       INTEGER PRIMARY KEY,
            AccountName     TEXT,
            AccountType     TEXT,
            InstitutionName TEXT
        );

        CREATE TABLE IF NOT EXISTS categories (
            CategoryID   INTEGER PRIMARY KEY,
            CategoryName TEXT UNIQUE
        );

        CREATE TABLE IF NOT EXISTS buckets (
            BucketID   INTEGER PRIMARY KEY,
            BucketName TEXT
        );

        CREATE TABLE IF NOT EXISTS CategoryRules (
            CatRuleID  INTEGER PRIMARY KEY,
            Pattern    TEXT,
            CategoryID INTEGER REFERENCES categories(CategoryID),
            MatchType  TEXT,
            Priority   INTEGER
        );

        CREATE TABLE IF NOT EXISTS BucketRules (
            CategoryID INTEGER REFERENCES categories(CategoryID),
            BucketID   INTEGER REFERENCES buckets(BucketID),
            PRIMARY KEY (CategoryID, BucketID)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            TransactionID  INTEGER PRIMARY KEY,
            DedupeHash     TEXT UNIQUE,
            AccountID      INTEGER REFERENCES accounts(AccountID),
            Date           DATE,
            DescriptionRaw TEXT,
            Amount         REAL,
            Type           TEXT,
            CategoryID     INTEGER REFERENCES categories(CategoryID),
            MatchRule      TEXT,
            Confidence     REAL,
            Notes          TEXT,
            SourceFile     TEXT,
            ImportedAt     DATETIME
        );
    """)

    # Seed categories
    cur.executemany(
        "INSERT OR IGNORE INTO categories (CategoryName) VALUES (?)",
        [(c,) for c in CATEGORIES]
    )

    # Seed accounts
    cur.executemany(
        "INSERT OR IGNORE INTO accounts (AccountName, AccountType, InstitutionName) VALUES (?, ?, ?)",
        ACCOUNTS
    )

    con.commit()
    con.close()
    print(f"DB ready at {DB_PATH}")

if __name__ == "__main__":
    setup_db()