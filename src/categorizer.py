"""
Part B — Categorizer, Rules Engine & Tags
budget-tracker/src/categorizer.py

Receives the list of transaction dicts from parse_visa_csv() and enriches
each with:
  - category   : str  (e.g. "Dining", "Groceries", "Transit")
  - tags       : list[str]  (e.g. ["work", "recurring"])
  - match_rule : str  (which rule fired, for debugging)
  - confidence : str  ("high" | "medium" | "low")

Usage:
    from visa_parser import parse_visa_csv
    from categorizer import categorize_transactions

    transactions = parse_visa_csv("Imports/04_VISA_Apr2025.csv")
    enriched    = categorize_transactions(transactions)
"""

from __future__ import annotations
import re
from typing import TypedDict
import datetime


# ---------------------------------------------------------------------------
# Type hint (mirrors visa_parser output + new fields)
# ---------------------------------------------------------------------------

class Transaction(TypedDict, total=False):
    id: str
    date: datetime.date
    description_raw: str
    amount: float
    type: str
    card_last4: str
    source_file: str
    # added by this module
    category: str
    tags: list[str]
    match_rule: str
    confidence: str


# ---------------------------------------------------------------------------
# Rules table
# Each rule is a dict with:
#   pattern   : regex applied (case-insensitive) to description_raw
#   category  : human-readable bucket name
#   tags      : list of extra labels
#   confidence: "high" if the pattern is very specific, "medium" otherwise
#
# Rules are evaluated TOP-TO-BOTTOM; first match wins.
# ---------------------------------------------------------------------------

RULES: list[dict] = [
    # ── Payments / credits ────────────────────────────────────────────────
    {
        "pattern": r"payment\s+thank\s+you|internet\s+payment|online\s+payment|autopay",
        "category": "Payment",
        "tags": ["payment"],
        "confidence": "high",
    },

    # ── Transit & travel ──────────────────────────────────────────────────
    {
        "pattern": r"presto|go\s+transit|metrolinx|ttc|brampton\s+transit|mississauga\s+transit|miway",
        "category": "Transit",
        "tags": ["transit", "recurring"],
        "confidence": "high",
    },
    {
        "pattern": r"air\s+transat|westjet|air\s+canada|porter\s+air|sunwing|flair\s+air",
        "category": "Travel – Flights",
        "tags": ["travel"],
        "confidence": "high",
    },
    {
        "pattern": r"expedia|booking\.com|airbnb|hotels\.com|trivago|priceline|vrbo",
        "category": "Travel – Accommodation",
        "tags": ["travel"],
        "confidence": "high",
    },
    {
        "pattern": r"uber\s*(?!eats)|lyft|taxi|via\s+ride",
        "category": "Rideshare",
        "tags": ["transit"],
        "confidence": "high",
    },
    {
        "pattern": r"parking|impark|greenp|honk\s+mobile",
        "category": "Parking",
        "tags": ["transit"],
        "confidence": "high",
    },

    # ── Dining & coffee ───────────────────────────────────────────────────
    {
        "pattern": r"tim\s+horton|starbucks|second\s+cup|coffee",
        "category": "Coffee",
        "tags": ["dining"],
        "confidence": "high",
    },
    {
        "pattern": r"mcdonald|burger\s+king|wendy.s|harveys|a&w|popeyes|kfc|taco\s+bell|subway\s+(?!.*transit)|five\s+guys|chipotle",
        "category": "Fast Food",
        "tags": ["dining"],
        "confidence": "high",
    },
    {
        "pattern": r"chicha\s+san\s+chen|earls|kelseys|boston\s+pizza|jack\s+astor|milestones|montanas|moxies|the\s+keg|mucho\s+burrito|grill|bistro|kitchen|tavern|pub|brewery|sushi|ramen|pho|shawarma|pizz|noodle|diner|barbeque|bbq",
        "category": "Restaurants",
        "tags": ["dining"],
        "confidence": "medium",
    },
    {
        "pattern": r"uber\s*eats|doordash|skip\s*the\s*dishes|instacart\s*(?!.*grocery)|grubhub",
        "category": "Food Delivery",
        "tags": ["dining"],
        "confidence": "high",
    },

    # ── Work meals ────────────────────────────────────────────────────────
    {
        "pattern": r"eurest|otpp\s*caf|office\s*caf|workplace\s*caf|canteen",
        "category": "Work Meals",
        "tags": ["dining", "work"],
        "confidence": "high",
    },

    # ── Groceries ─────────────────────────────────────────────────────────
    {
        "pattern": r"freshco|loblaws|no\s+frills|metro\s+(?!.*park)|sobeys|food\s+basics|walmart\s*(?!.*online)|zehrs|valumart|farm\s*boy|whole\s+foods|superstore|grocery|supermarket",
        "category": "Groceries",
        "tags": ["groceries"],
        "confidence": "high",
    },

    # ── Online shopping ───────────────────────────────────────────────────
    {
        "pattern": r"amazon|amzn",
        "category": "Online Shopping",
        "tags": ["shopping"],
        "confidence": "high",
    },
    {
        "pattern": r"ebay|etsy|aliexpress|shein|wish\.com|temu",
        "category": "Online Shopping",
        "tags": ["shopping"],
        "confidence": "high",
    },

    # ── Home improvement / hardware ───────────────────────────────────────
    {
        "pattern": r"home\s+depot|rona|lowes|canadian\s+tire|tools|hardware",
        "category": "Home & Hardware",
        "tags": ["home"],
        "confidence": "high",
    },

    # ── Entertainment / events ────────────────────────────────────────────
    {
        "pattern": r"ticketmaster|eventbrite|stubhub|livenation|cineplex|landmark\s+cinema|imax",
        "category": "Entertainment",
        "tags": ["entertainment"],
        "confidence": "high",
    },
    {
        "pattern": r"netflix|spotify|apple\s*(?:music|tv|one)|disney\+|crave|amazon\s+prime|youtube\s+premium|hbo|paramount\+|peacock",
        "category": "Subscriptions",
        "tags": ["entertainment", "recurring"],
        "confidence": "high",
    },

    # ── Health & fitness ──────────────────────────────────────────────────
    {
        "pattern": r"shoppers|rexall|pharma|drug\s*mart|london\s*drugs",
        "category": "Pharmacy",
        "tags": ["health"],
        "confidence": "high",
    },
    {
        "pattern": r"goodlife|anytime\s+fitness|planet\s+fitness|ymca|gym|crossfit",
        "category": "Fitness",
        "tags": ["health", "recurring"],
        "confidence": "high",
    },
    {
        "pattern": r"doctor|dentist|physio|optom|clinic|hospital|ohip|massage\s*therapy|chiropractic",
        "category": "Healthcare",
        "tags": ["health"],
        "confidence": "medium",
    },

    # ── Utilities & phone ─────────────────────────────────────────────────
    {
        "pattern": r"rogers|bell\s+(?:canada|mobility)|telus|freedom\s+mobile|fido|public\s+mobile|koodo|virgin\s+plus",
        "category": "Phone / Internet",
        "tags": ["utilities", "recurring"],
        "confidence": "high",
    },
    {
        "pattern": r"hydro|enbridge|gas\s*(?:utility|co\.|company)|utility|utilities|water\s+bill",
        "category": "Utilities",
        "tags": ["utilities", "recurring"],
        "confidence": "high",
    },

    # ── Gas / fuel ────────────────────────────────────────────────────────
    {
        "pattern": r"petro.canada|esso|shell|husky|pioneer\s+gas|ultramar|sunoco|costco\s+gas|gas\s+station",
        "category": "Gas & Fuel",
        "tags": ["car"],
        "confidence": "high",
    },

    # ── Insurance ─────────────────────────────────────────────────────────
    {
        "pattern": r"intact|td\s+insurance|belair|aviva|desjardin|allstate|wawanesa|insurance",
        "category": "Insurance",
        "tags": ["insurance", "recurring"],
        "confidence": "medium",
    },

    # ── Clothing & personal care ──────────────────────────────────────────
    {
        "pattern": r"winners|marshalls|h&m|zara|uniqlo|gap|old\s+navy|banana\s+republic|lululemon|sport\s+chek|nike|adidas|foot\s+locker",
        "category": "Clothing",
        "tags": ["shopping"],
        "confidence": "high",
    },
    {
        "pattern": r"sephora|ulta|mac\s+cosmetics|bath\s+&\s+body|lush|salon|hair|barber|spa\b",
        "category": "Personal Care",
        "tags": ["personal"],
        "confidence": "medium",
    },

    # ── Education ─────────────────────────────────────────────────────────
    {
        "pattern": r"coursera|udemy|skillshare|linkedin\s+learning|tuition|university|college",
        "category": "Education",
        "tags": ["education"],
        "confidence": "medium",
    },

    # ── Bank fees ─────────────────────────────────────────────────────────
    {
        "pattern": r"interest\s+charge|annual\s+fee|service\s+charge|nsf\s+fee|bank\s+fee|foreign\s+transaction",
        "category": "Bank Fees",
        "tags": ["fees"],
        "confidence": "high",
    },

    # ── Custom rules from real data ───────────────────────────────────────
    {
        "pattern": r"TVM|go\s*tvm|metrolinx\s*tvm",
        "category": "Transit",
        "tags": ["transit", "recurring"],
        "confidence": "high",
    },
    {
        "pattern": r"gore\s+meadows|community\s+centre|rec\s+centre|recreation\s+centre",
        "category": "Fitness",
        "tags": ["health"],
        "confidence": "medium",
    },
    {
        "pattern": r"HM\s+CA|h\s*&\s*m\b",
        "category": "Clothing",
        "tags": ["shopping"],
        "confidence": "high",
    },
    {
        "pattern": r"\bgarage\b(?!.*parking)",
        "category": "Clothing",
        "tags": ["shopping"],
        "confidence": "high",
    },
    {
        "pattern": r"mos\s+mos|TST-|SQ\s+\*|square\s+\*",
        "category": "Restaurants",
        "tags": ["dining"],
        "confidence": "medium",
    },
    {
        "pattern": r"wal.mart|walmart",
        "category": "Groceries",
        "tags": ["groceries"],
        "confidence": "high",
    },
    {
        "pattern": r"chartered\s+professional|CPA\b|accounting|accountant",
        "category": "Professional Services",
        "tags": ["fees"],
        "confidence": "medium",
    },
    {
        "pattern": r"mycreds|mescertif|credential|transcript",
        "category": "Education",
        "tags": ["education"],
        "confidence": "medium",
    },
    {
        "pattern": r"tsujiri|matcha|bubble\s*tea|boba",
        "category": "Coffee",
        "tags": ["dining"],
        "confidence": "medium",
    },
    {
        "pattern": r"platos\s+closet|value\s+village|thrift|consignment",
        "category": "Clothing",
        "tags": ["shopping"],
        "confidence": "medium",
    },
    {
        "pattern": r"watering\s+can|winery|vineyard|wine\s+co|wine\s+shop",
        "category": "Alcohol",
        "tags": ["dining"],
        "confidence": "medium",
    },
    {
        "pattern": r"spencer\s+gifts|chapter|indigo|coles\b",
        "category": "Shopping",
        "tags": ["shopping"],
        "confidence": "medium",
    },
    {
        "pattern": r"yesstyle|ssense|aritzia|revolve",
        "category": "Online Shopping",
        "tags": ["shopping"],
        "confidence": "high",
    },
    {
        "pattern": r"pioneer\s*#|pioneer\s+gas|pioneer\s+petro",
        "category": "Gas & Fuel",
        "tags": ["car"],
        "confidence": "high",
    },
]

# Compile patterns once at import time for performance
_COMPILED_RULES = [
    {**rule, "_re": re.compile(rule["pattern"], re.IGNORECASE)}
    for rule in RULES
]

UNCATEGORIZED = "Uncategorized"


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def categorize_transaction(txn: Transaction) -> Transaction:
    """
    Add category, tags, match_rule, and confidence fields to a single
    transaction dict (mutates a copy and returns it).
    """
    result = dict(txn)  # shallow copy so we don't mutate the original
    desc = txn.get("description_raw", "")

    for rule in _COMPILED_RULES:
        if rule["_re"].search(desc):
            result["category"]   = rule["category"]
            result["tags"]       = list(rule["tags"])  # copy the list
            result["match_rule"] = rule["pattern"]
            result["confidence"] = rule["confidence"]
            return result  # type: ignore[return-value]

    # No rule matched
    result["category"]   = UNCATEGORIZED
    result["tags"]       = []
    result["match_rule"] = None
    result["confidence"] = "low"
    return result  # type: ignore[return-value]


def categorize_transactions(transactions: list[Transaction]) -> list[Transaction]:
    """
    Categorize a list of transactions. Returns a new list of enriched dicts.
    """
    return [categorize_transaction(t) for t in transactions]


# ---------------------------------------------------------------------------
# Custom rule support — add your own rules at runtime
# ---------------------------------------------------------------------------

def add_rule(
    pattern: str,
    category: str,
    tags: list[str] | None = None,
    confidence: str = "high",
    insert_at_top: bool = True,
) -> None:
    """
    Dynamically add a rule (e.g. from a config file or user settings).

    insert_at_top=True means the new rule takes priority over built-in ones.
    """
    entry = {
        "pattern": pattern,
        "category": category,
        "tags": tags or [],
        "confidence": confidence,
        "_re": re.compile(pattern, re.IGNORECASE),
    }
    if insert_at_top:
        _COMPILED_RULES.insert(0, entry)
    else:
        _COMPILED_RULES.append(entry)


# ---------------------------------------------------------------------------
# Diagnostics / reporting helpers
# ---------------------------------------------------------------------------

def summary_by_category(transactions: list[Transaction]) -> dict[str, dict]:
    """
    Return a dict of { category: { count, total_amount } } for quick review.
    Excludes Payment-type transactions from the total.
    """
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
    """Return only the transactions that couldn't be categorized."""
    return [t for t in transactions if t.get("category") == UNCATEGORIZED]


# ---------------------------------------------------------------------------
# Quick smoke-test (run: python src/categorizer.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import os

    # Try to import from the real parser if it exists alongside this file
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from visa_parser import parse_visa_csv  # type: ignore

        # Walk Imports/ folder and find the first CSV
        imports_dir = os.path.join(os.path.dirname(__file__), "..", "Imports")
        csv_files = [
            os.path.join(imports_dir, f)
            for f in os.listdir(imports_dir)
            if f.lower().endswith(".csv")
        ] if os.path.isdir(imports_dir) else []

        if not csv_files:
            raise FileNotFoundError("No CSVs found in Imports/")

        raw = parse_visa_csv(csv_files[0])
        print(f"Parsed {len(raw)} transactions from {os.path.basename(csv_files[0])}")

    except Exception as exc:
        print(f"[visa_parser not available — using synthetic test data] ({exc})")

        # Synthetic fallback so the module can be tested standalone
        import datetime

        raw = [
            {"id": "a1", "date": datetime.date(2025, 4, 1), "description_raw": "TIM HORTONS #1234", "amount": 3.75, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "a2", "date": datetime.date(2025, 4, 2), "description_raw": "PRESTO RELOAD TORONTO ON", "amount": 50.00, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "a3", "date": datetime.date(2025, 4, 3), "description_raw": "FRESHCO BRAMPTON ON", "amount": 87.42, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "a4", "date": datetime.date(2025, 4, 4), "description_raw": "EUREST-OTPP TORONTO ON", "amount": 12.50, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "a5", "date": datetime.date(2025, 4, 5), "description_raw": "AMAZON.CA MARKETPLACE", "amount": 34.99, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "a6", "date": datetime.date(2025, 4, 6), "description_raw": "AIR TRANSAT MONTREAL QC", "amount": 450.00, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "a7", "date": datetime.date(2025, 4, 7), "description_raw": "TICKETMASTER TORONTO ON", "amount": 110.00, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "a8", "date": datetime.date(2025, 4, 8), "description_raw": "EXPEDIA CA HOTEL", "amount": 220.00, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "a9", "date": datetime.date(2025, 4, 9), "description_raw": "HOME DEPOT 1234 BRAMPTON", "amount": 67.88, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "a0", "date": datetime.date(2025, 4, 10), "description_raw": "CHICHA SAN CHEN TORONTO ON", "amount": 10.11, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "b1", "date": datetime.date(2025, 4, 11), "description_raw": "SOME RANDOM VENDOR XYZ", "amount": 9.99, "type": "debit", "card_last4": "xxxx-1234", "source_file": "test.csv"},
            {"id": "b2", "date": datetime.date(2025, 4, 12), "description_raw": "PAYMENT THANK YOU", "amount": -500.00, "type": "payment", "card_last4": "xxxx-1234", "source_file": "test.csv"},
        ]

    enriched = categorize_transactions(raw)

    print("\n── Categorized transactions ──────────────────────────────────")
    for t in enriched:
        conf_icon = {"high": "✓", "medium": "~", "low": "?"}.get(t["confidence"], "?")
        print(
            f"  {conf_icon} [{t['category']:<30}]  "
            f"${t['amount']:>8.2f}  "
            f"tags={t['tags']}  "
            f"  {t['description_raw']}"
        )

    print("\n── Summary by category ───────────────────────────────────────")
    for cat, data in summary_by_category(enriched).items():
        print(f"  {cat:<30}  {data['count']:>3} txns   ${data['total']:>9.2f}")

    uncat = uncategorized_list(enriched)
    print(f"\n── Uncategorized ({len(uncat)}) ────────────────────────────────────")
    for t in uncat:
        print(f"  {t['description_raw']}")