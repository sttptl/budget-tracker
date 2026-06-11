import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "budget.db"


ACCOUNTS = [
    ("TD Visa", "credit", "TD"),
    ("TD Chequing", "chequing", "TD"),
]


def get_connection():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    return con


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
            CategoryName TEXT UNIQUE,
            BucketID     INTEGER REFERENCES buckets(BucketID)
        );

        CREATE TABLE IF NOT EXISTS buckets (
            BucketID   INTEGER PRIMARY KEY,
            BucketName TEXT UNIQUE
        );

        CREATE TABLE IF NOT EXISTS CategoryRules (
            CatRuleID  INTEGER PRIMARY KEY,
            Pattern    TEXT,
            CategoryID INTEGER REFERENCES categories(CategoryID),
            MatchType  TEXT,
            Priority   INTEGER
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

        -- One row per bucket per income transaction.
        -- Percentage and Amount are stored so the dashboard
        -- can use either without recomputing.
        CREATE TABLE IF NOT EXISTS income_allocations (
            AllocationID  INTEGER PRIMARY KEY,
            TransactionID INTEGER REFERENCES transactions(TransactionID) ON DELETE CASCADE,
            BucketID      INTEGER REFERENCES buckets(BucketID),
            Percentage    REAL,   -- e.g. 40.0 for 40%
            Amount        REAL    -- computed: transaction amount * percentage / 100
        );
    """)

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