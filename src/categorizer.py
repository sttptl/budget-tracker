"""
Part B — Categorizer (DB-driven)
budget-tracker/src/categorizer.py

Pulls rules from the CategoryRules table in SQLite instead of hardcoded dicts.
Falls back to "Uncategorized" if no rule matches.
"""

from __future__ import annotations
import re
import sqlite3
import datetime
from pathlib import Path
from typing import TypedDict

DB_PATH = Path(__file__).parent.parent / "data" / "budget.db"

UNCATEGORIZED = "Uncategorized"


class Transaction(TypedDict, total=False):
    id: str
    date: datetime.date
    description_raw: str
    amount: float
    type: str
    card_last4: str
    source_file: str
    category: str
    tags: list[str]
    match_rule: str
    confidence: str


# ---------------------------------------------------------------------------
# Load rules from DB
# ---------------------------------------------------------------------------

def load_rules_from_db() -> list[dict]:
    """
    Fetches all rules from CategoryRules joined with categories.
    Returns a list of dicts ready for regex matching, ordered by Priority DESC.
    """
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        SELECT cr.Pattern, c.CategoryName, cr.MatchType, cr.Priority
        FROM CategoryRules cr
        JOIN categories c ON cr.CategoryID = c.CategoryID
        ORDER BY cr.Priority DESC
    """)
    rows = cur.fetchall()
    con.close()

    rules = []
    for pattern, category, match_type, priority in rows:
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            rules.append({
                "pattern": pattern,
                "category": category,
                "match_type": match_type,
                "priority": priority,
                "_re": compiled,
            })
        except re.error:
            print(f"[categorizer] Skipping invalid regex: {pattern}")
    return rules


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def categorize_transaction(txn: Transaction, rules: list[dict]) -> Transaction:
    result = dict(txn)
    desc = txn.get("description_raw", "")

    for rule in rules:
        if rule["_re"].search(desc):
            result["category"]   = rule["category"]
            result["tags"]       = []
            result["match_rule"] = rule["pattern"]
            result["confidence"] = "high" if rule["priority"] >= 90 else "medium"
            return result

    result["category"]   = UNCATEGORIZED
    result["tags"]       = []
    result["match_rule"] = None
    result["confidence"] = "low"
    return result


def categorize_transactions(transactions: list[Transaction]) -> list[Transaction]:
    """
    Categorize a list of transactions. Loads rules fresh from DB on each call.
    """
    rules = load_rules_from_db()
    return [categorize_transaction(t, rules) for t in transactions]


# ---------------------------------------------------------------------------
# Diagnostics helpers
# ---------------------------------------------------------------------------

def summary_by_category(transactions: list[Transaction]) -> dict[str, dict]:
    buckets: dict[str, dict] = {}
    for t in transactions:
        cat = t.get("category", UNCATEGORIZED)
        if cat not in buckets:
            buckets[cat] = {"count": 0, "total": 0.0}
        buckets[cat]["count"] += 1
        if t.get("type") != "payment":
            buckets[cat]["total"] = round(buckets[cat]["total"] + t.get("amount", 0.0), 2)
    return dict(sorted(buckets.items()))


def uncategorized_list(transactions: list[Transaction]) -> list[Transaction]:
    return [t for t in transactions if t.get("category") == UNCATEGORIZED]