"""
Run once to migrate hardcoded rules from categorizer.py into CategoryRules table.
Usage: python -m src.seed_rules
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "budget.db"

RULES = [
    # ── Payments ──────────────────────────────────────────────────────────
    (r"payment\s+thank\s+you|internet\s+payment|online\s+payment|autopay", "Payment", "regex", 100),
    # ── Transit ───────────────────────────────────────────────────────────
    (r"presto|go\s+transit|metrolinx|ttc|brampton\s+transit|mississauga\s+transit|miway", "Transit", "regex", 90),
    (r"TVM|go\s*tvm|metrolinx\s*tvm", "Transit", "regex", 90),
    # ── Rideshare ─────────────────────────────────────────────────────────
    (r"uber\s*(?!eats)|lyft|taxi|via\s+ride", "Transit", "regex", 90),
    # ── Coffee ────────────────────────────────────────────────────────────
    (r"tim\s+horton|starbucks|second\s+cup|coffee", "Coffee", "regex", 90),
    (r"tsujiri|matcha|bubble\s*tea|boba", "Coffee", "regex", 80),
    # ── Fast Food ─────────────────────────────────────────────────────────
    (r"mcdonald|burger\s+king|wendy.s|harveys|a&w|popeyes|kfc|taco\s+bell|subway\s+(?!.*transit)|five\s+guys|chipotle", "Fast Food", "regex", 90),
    # ── Restaurants ───────────────────────────────────────────────────────
    (r"chicha\s+san\s+chen|earls|kelseys|boston\s+pizza|jack\s+astor|milestones|montanas|moxies|the\s+keg|mucho\s+burrito|grill|bistro|kitchen|tavern|pub|brewery|sushi|ramen|pho|shawarma|pizz|noodle|diner|barbeque|bbq", "Restaurants", "regex", 80),
    (r"mos\s+mos|TST-|SQ\s+\*|square\s+\*", "Restaurants", "regex", 80),
    # ── Work Meals ────────────────────────────────────────────────────────
    (r"eurest|otpp\s*caf|office\s*caf|workplace\s*caf|canteen", "Work Meals", "regex", 90),
    # ── Groceries ─────────────────────────────────────────────────────────
    (r"freshco|loblaws|no\s+frills|metro\s+(?!.*park)|sobeys|food\s+basics|zehrs|valumart|farm\s*boy|whole\s+foods|superstore|grocery|supermarket", "Groceries", "regex", 90),
    (r"wal.mart|walmart", "Groceries", "regex", 90),
    # ── Online Shopping ───────────────────────────────────────────────────
    (r"amazon|amzn", "Online Shopping", "regex", 90),
    (r"ebay|etsy|aliexpress|shein|wish\.com|temu", "Online Shopping", "regex", 90),
    (r"yesstyle|ssense|aritzia|revolve", "Online Shopping", "regex", 90),
    # ── Fitness ───────────────────────────────────────────────────────────
    (r"goodlife|anytime\s+fitness|planet\s+fitness|ymca|gym|crossfit", "Fitness", "regex", 90),
    (r"gore\s+meadows|community\s+centre|rec\s+centre|recreation\s+centre", "Fitness", "regex", 80),
    # ── Gas & Fuel ────────────────────────────────────────────────────────
    (r"petro.canada|esso|shell|husky|ultramar|sunoco|costco\s+gas|gas\s+station", "Gas & Fuel", "regex", 90),
    (r"pioneer\s*#|pioneer\s+gas|pioneer\s+petro", "Gas & Fuel", "regex", 90),
    # ── Clothing ─────────────────────────────────────────────────────────
    (r"winners|marshalls|h&m|zara|uniqlo|gap|old\s+navy|banana\s+republic|lululemon|sport\s+chek|nike|adidas|foot\s+locker", "Clothing", "regex", 90),
    (r"HM\s+CA|h\s*&\s*m\b", "Clothing", "regex", 90),
    (r"\bgarage\b(?!.*parking)", "Clothing", "regex", 90),
    (r"platos\s+closet|value\s+village|thrift|consignment", "Clothing", "regex", 80),
    # ── Shopping ─────────────────────────────────────────────────────────
    (r"spencer\s+gifts|chapter|indigo|coles\b", "Shopping", "regex", 80),
    # ── Alcohol ───────────────────────────────────────────────────────────
    (r"watering\s+can|winery|vineyard|wine\s+co|wine\s+shop", "Alcohol", "regex", 80),
    # ── Education ─────────────────────────────────────────────────────────
    (r"coursera|udemy|skillshare|linkedin\s+learning|tuition|university|college", "Education", "regex", 80),
    (r"mycreds|mescertif|credential|transcript", "Education", "regex", 80),
    # ── Professional Services ─────────────────────────────────────────────
    (r"chartered\s+professional|CPA\b|accounting|accountant", "Professional Services", "regex", 80),
]

def seed_rules():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Make sure all categories referenced exist
    categories = set(r[1] for r in RULES)
    cur.executemany(
        "INSERT OR IGNORE INTO categories (CategoryName) VALUES (?)",
        [(c,) for c in categories]
    )

    # Clear existing rules and re-seed fresh
    cur.execute("DELETE FROM CategoryRules")

    for pattern, category, match_type, priority in RULES:
        cur.execute("SELECT CategoryID FROM categories WHERE CategoryName = ?", (category,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "INSERT INTO CategoryRules (Pattern, CategoryID, MatchType, Priority) VALUES (?, ?, ?, ?)",
                (pattern, row[0], match_type, priority)
            )

    con.commit()
    con.close()
    print(f"Seeded {len(RULES)} rules into CategoryRules.")

if __name__ == "__main__":
    seed_rules()