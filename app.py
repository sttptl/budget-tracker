import streamlit as st
import pandas as pd
from src.visa_parser import parse_visa_csv
from src.chequing_parser import parse_chequing_csv
from src.categorizer import categorize_transactions
from src.db_setup import get_connection

st.set_page_config(page_title="Budget Tracker", layout="wide")


# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS  (defined first so pages can call them)
# ══════════════════════════════════════════════════════════════════════════════

def _get_categories() -> list:
    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT CategoryName FROM categories ORDER BY CategoryName")
    cats = [r[0] for r in cur.fetchall()]
    con.close()
    return cats


def _get_buckets() -> list:
    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT BucketName FROM buckets ORDER BY BucketName")
    buckets = [r[0] for r in cur.fetchall()]
    con.close()
    return buckets


def _stat_cards(txns):
    total_spent   = sum(t["amount"] for t in txns if t["amount"] < 0)
    payments_in   = sum(t["amount"] for t in txns if t["amount"] > 0)
    uncategorized = sum(1 for t in txns if t["category"] == "Uncategorized")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Spent",   f"${abs(total_spent):,.2f}")
    col2.metric("Payments In",   f"${payments_in:,.2f}")
    col3.metric("Transactions",  len(txns))
    col4.metric("Uncategorized", uncategorized)


def _stat_cards_chequing(income_txns, expense_txns):
    total_in      = sum(abs(t["amount"]) for t in income_txns)
    total_out     = sum(abs(t["amount"]) for t in expense_txns)
    uncategorized = sum(1 for t in income_txns + expense_txns if t["category"] == "Uncategorized")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total In",      f"${total_in:,.2f}")
    col2.metric("Total Out",     f"${total_out:,.2f}")
    col3.metric("Transactions",  len(income_txns) + len(expense_txns))
    col4.metric("Uncategorized", uncategorized)


def _fmt_date(t):
    """Return date as YYYY-MM-DD string regardless of whether it's a date obj or string."""
    d = t["date"]
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else d


def _render_visa_review():
    txns = st.session_state["transactions"]
    _stat_cards(txns)
    st.divider()

    CATEGORIES = _get_categories()

    df = pd.DataFrame([{
        "date":        _fmt_date(t),
        "description": t["description_raw"],
        "amount":      t["amount"],
        "category":    t["category"],
        "match_rule":  t.get("match_rule", ""),
        "confidence":  t.get("confidence", ""),
        "notes":       "",
    } for t in txns])

    edited_df = st.data_editor(
        df,
        use_container_width=True,
        column_config={
            "date":        st.column_config.TextColumn("Date", disabled=True),
            "description": st.column_config.TextColumn("Description", disabled=True),
            "amount":      st.column_config.NumberColumn("Amount", format="$%.2f", disabled=True),
            "category":    st.column_config.SelectboxColumn("Category", options=CATEGORIES),
            "match_rule":  st.column_config.TextColumn("Match Rule", disabled=True),
            "confidence":  st.column_config.TextColumn("Confidence", disabled=True),
            "notes":       st.column_config.TextColumn("Notes"),
        },
        hide_index=True,
    )
    st.session_state["edited_df"] = edited_df

    if st.button("Submit Review"):
        from src.db_writer import write_transactions
        result = write_transactions(
            st.session_state["edited_df"],
            st.session_state["transactions"],
            st.session_state["account"],
        )
        st.success(
            f"Done! {result['inserted']} transactions saved, "
            f"{result['skipped']} duplicates skipped."
        )
        for key in ["transactions", "edited_df", "account"]:
            st.session_state.pop(key, None)


def _render_chequing_review():
    txns         = st.session_state["transactions"]
    income_txns  = [t for t in txns if t.get("flow") == "income"]
    expense_txns = [t for t in txns if t.get("flow") == "expense"]

    _stat_cards_chequing(income_txns, expense_txns)
    st.divider()

    tab_income, tab_expenses = st.tabs([
        f"Income ({len(income_txns)})",
        f"Expenses ({len(expense_txns)})",
    ])

    # ── Income tab ────────────────────────────────────────────────────────────
    with tab_income:
        buckets = _get_buckets()

        if not buckets:
            st.warning("No buckets found. Go to the **Buckets** page to add some before reviewing income.")
        else:
            CATEGORIES = _get_categories()

            income_df = pd.DataFrame([{
                "date":        _fmt_date(t),
                "description": t["description_raw"],
                "amount":      t["amount"],
                "type":        t.get("type", ""),
                "category":    t["category"],
                "notes":       "",
            } for t in income_txns])

            st.subheader("Review Income Transactions")
            edited_income_df = st.data_editor(
                income_df,
                use_container_width=True,
                column_config={
                    "date":        st.column_config.TextColumn("Date", disabled=True),
                    "description": st.column_config.TextColumn("Description", disabled=True),
                    "amount":      st.column_config.NumberColumn("Amount", format="$%.2f", disabled=True),
                    "type":        st.column_config.TextColumn("Type", disabled=True),
                    "category":    st.column_config.SelectboxColumn("Category", options=CATEGORIES),
                    "notes":       st.column_config.TextColumn("Notes"),
                },
                hide_index=True,
                key="income_editor",
            )
            st.session_state["edited_income_df"] = edited_income_df

            st.divider()
            st.subheader("Bucket Allocations")
            st.caption("Enter the % to allocate to each bucket per income row. Each row must sum to 100%.")

            # Initialise allocation state on first render
            if "allocations" not in st.session_state:
                st.session_state["allocations"] = {
                    t["id"]: {b: 0.0 for b in buckets}
                    for t in income_txns
                }

            all_valid      = True
            allocation_data = {}

            for t in income_txns:
                txn_id = t["id"]
                amount = abs(t["amount"])
                label  = f"{_fmt_date(t)} — {t['description_raw'][:55]}  (${amount:,.2f})"

                with st.expander(label, expanded=True):
                    cols = st.columns(len(buckets) + 1)  # one col per bucket + total

                    pct_values = {}
                    for i, bucket in enumerate(buckets):
                        saved = st.session_state["allocations"].get(txn_id, {}).get(bucket, 0.0)
                        pct = cols[i].number_input(
                            bucket,
                            min_value=0.0,
                            max_value=100.0,
                            value=saved,
                            step=5.0,
                            format="%.1f",
                            key=f"alloc_{txn_id}_{bucket}",
                        )
                        pct_values[bucket] = pct

                    total_pct = sum(pct_values.values())
                    colour    = "green" if abs(total_pct - 100.0) < 0.01 else "red"
                    cols[-1].markdown("**Total**")
                    cols[-1].markdown(f":{colour}[{total_pct:.1f}%]")

                    if abs(total_pct - 100.0) >= 0.01:
                        all_valid = False

                    allocation_data[txn_id] = {
                        bucket: {
                            "percentage": pct_values[bucket],
                            "amount":     round(amount * pct_values[bucket] / 100, 2),
                        }
                        for bucket in buckets
                    }
                    st.session_state["allocations"][txn_id] = pct_values

            st.session_state["allocation_data"]    = allocation_data
            st.session_state["allocations_valid"]  = all_valid

            if not all_valid:
                st.warning("All income rows must sum to exactly 100% before you can submit.")

    # ── Expenses tab ──────────────────────────────────────────────────────────
    with tab_expenses:
        if not expense_txns:
            st.info("No expense transactions in this file.")
        else:
            CATEGORIES = _get_categories()

            expense_df = pd.DataFrame([{
                "date":        _fmt_date(t),
                "description": t["description_raw"],
                "amount":      t["amount"],
                "type":        t.get("type", ""),
                "category":    t["category"],
                "match_rule":  t.get("match_rule", ""),
                "confidence":  t.get("confidence", ""),
                "notes":       "",
            } for t in expense_txns])

            edited_expense_df = st.data_editor(
                expense_df,
                use_container_width=True,
                column_config={
                    "date":        st.column_config.TextColumn("Date", disabled=True),
                    "description": st.column_config.TextColumn("Description", disabled=True),
                    "amount":      st.column_config.NumberColumn("Amount", format="$%.2f", disabled=True),
                    "type":        st.column_config.TextColumn("Type", disabled=True),
                    "category":    st.column_config.SelectboxColumn("Category", options=CATEGORIES),
                    "match_rule":  st.column_config.TextColumn("Match Rule", disabled=True),
                    "confidence":  st.column_config.TextColumn("Confidence", disabled=True),
                    "notes":       st.column_config.TextColumn("Notes"),
                },
                hide_index=True,
                key="expense_editor",
            )
            st.session_state["edited_expense_df"] = edited_expense_df

    # ── Submit button (outside tabs, always visible) ──────────────────────────
    st.divider()

    income_txns      = [t for t in st.session_state["transactions"] if t.get("flow") == "income"]
    allocations_valid = st.session_state.get("allocations_valid", True) if income_txns else True

    if st.button("Submit Review", disabled=not allocations_valid):
        from src.db_writer import write_chequing_transactions

        result = write_chequing_transactions(
            st.session_state.get("edited_income_df",  pd.DataFrame()),
            st.session_state.get("edited_expense_df", pd.DataFrame()),
            st.session_state["transactions"],
            st.session_state.get("allocation_data", {}),
            st.session_state["account"],
        )
        st.success(
            f"Done! {result['inserted']} transactions saved, "
            f"{result['skipped']} duplicates skipped, "
            f"{result['allocations_written']} allocation rows written."
        )
        for key in ["transactions", "edited_income_df", "edited_expense_df",
                    "account", "allocations", "allocation_data", "allocations_valid"]:
            st.session_state.pop(key, None)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR NAV
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("Budget Tracker")
    page = st.radio(
        "Navigation",
        ["Import", "Categories", "Buckets", "Rules"],
        label_visibility="collapsed",
    )


# ══════════════════════════════════════════════════════════════════════════════
# IMPORT PAGE
# ══════════════════════════════════════════════════════════════════════════════

if page == "Import":
    st.header("Import Transactions")

    ACCOUNTS = ["TD Visa", "TD Chequing"]
    selected_account = st.selectbox("Select account", ACCOUNTS)

    uploaded_file = st.file_uploader("Upload a transaction CSV", type="csv")

    if uploaded_file is not None:
        if st.button("Process"):
            with st.spinner("Parsing and categorizing..."):
                if selected_account == "TD Chequing":
                    txns = parse_chequing_csv(uploaded_file)
                else:
                    txns = parse_visa_csv(uploaded_file)

                enriched = categorize_transactions(txns)

                # Flip sign for UI: positive = income received, negative = spending
                for t in enriched:
                    t["amount"] = -t["amount"]

                st.session_state["transactions"] = enriched
                st.session_state["account"]      = selected_account
            st.success(f"Loaded {len(enriched)} transactions.")

    if "transactions" in st.session_state:
        if st.session_state.get("account") == "TD Chequing":
            _render_chequing_review()
        else:
            _render_visa_review()


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORIES PAGE
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Categories":
    st.header("Categories")

    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT CategoryID, CategoryName FROM categories ORDER BY CategoryName")
    cats = cur.fetchall()
    con.close()

    cat_df = pd.DataFrame(cats, columns=["ID", "Category"])
    st.dataframe(cat_df, use_container_width=True, hide_index=True)

    st.divider()
    st.write("**Add new category**")
    new_cat = st.text_input("Category name", key="new_cat_input")
    if st.button("Add Category"):
        if new_cat.strip():
            con = get_connection()
            cur = con.cursor()
            try:
                cur.execute("INSERT INTO categories (CategoryName) VALUES (?)", (new_cat.strip(),))
                con.commit()
                st.success(f"Added: {new_cat.strip()}")
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                con.close()
            st.rerun()
        else:
            st.warning("Please enter a category name.")

    st.divider()
    st.write("**Delete category**")
    cat_names = [c[1] for c in cats]
    if cat_names:
        cat_to_delete = st.selectbox("Select category to delete", cat_names, key="delete_cat")
        if st.button("Delete Category"):
            con = get_connection()
            cur = con.cursor()
            cur.execute("DELETE FROM categories WHERE CategoryName = ?", (cat_to_delete,))
            con.commit()
            con.close()
            st.success(f"Deleted: {cat_to_delete}")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# BUCKETS PAGE
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Buckets":
    st.header("Buckets")

    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT BucketID, BucketName FROM buckets ORDER BY BucketName")
    bucket_rows = cur.fetchall()
    con.close()

    if bucket_rows:
        bucket_df = pd.DataFrame(bucket_rows, columns=["ID", "Bucket"])
        st.dataframe(bucket_df, use_container_width=True, hide_index=True)
    else:
        st.info("No buckets yet. Add one below.")

    st.divider()
    st.write("**Add new bucket**")
    new_bucket = st.text_input("Bucket name", key="new_bucket_input")
    if st.button("Add Bucket"):
        if new_bucket.strip():
            con = get_connection()
            cur = con.cursor()
            try:
                cur.execute("INSERT INTO buckets (BucketName) VALUES (?)", (new_bucket.strip(),))
                con.commit()
                st.success(f"Added: {new_bucket.strip()}")
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                con.close()
            st.rerun()
        else:
            st.warning("Please enter a bucket name.")

    st.divider()
    st.write("**Delete bucket**")
    if bucket_rows:
        bucket_names    = [b[1] for b in bucket_rows]
        bucket_to_delete = st.selectbox("Select bucket to delete", bucket_names, key="delete_bucket")
        if st.button("Delete Bucket"):
            con = get_connection()
            cur = con.cursor()
            cur.execute("DELETE FROM buckets WHERE BucketName = ?", (bucket_to_delete,))
            con.commit()
            con.close()
            st.success(f"Deleted: {bucket_to_delete}")
            st.rerun()
    else:
        st.info("No buckets to delete.")


# ══════════════════════════════════════════════════════════════════════════════
# RULES PAGE
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Rules":
    st.header("Category Rules")

    con = get_connection()
    cur = con.cursor()
    cur.execute("""
        SELECT cr.CatRuleID, cr.Pattern, c.CategoryName, cr.MatchType, cr.Priority
        FROM CategoryRules cr
        JOIN categories c ON cr.CategoryID = c.CategoryID
        ORDER BY cr.Priority DESC
    """)
    rules = cur.fetchall()
    con.close()

    rules_df = pd.DataFrame(rules, columns=["ID", "Pattern", "Category", "Match Type", "Priority"])
    st.dataframe(rules_df, use_container_width=True, hide_index=True)

    st.divider()
    st.write("**Add new rule**")

    con = get_connection()
    cur = con.cursor()
    cur.execute("SELECT CategoryName FROM categories ORDER BY CategoryName")
    all_cats = [r[0] for r in cur.fetchall()]
    con.close()

    new_pattern  = st.text_input("Pattern (regex matched against description)", key="new_rule_pattern")
    new_rule_cat = st.selectbox("Category", all_cats, key="new_rule_cat")
    new_priority = st.slider("Priority (higher = evaluated first)", 1, 100, 80, key="new_rule_priority")

    if st.button("Add Rule"):
        if new_pattern.strip():
            con = get_connection()
            cur = con.cursor()
            cur.execute("SELECT CategoryID FROM categories WHERE CategoryName = ?", (new_rule_cat,))
            cat_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO CategoryRules (Pattern, CategoryID, MatchType, Priority) VALUES (?, ?, ?, ?)",
                (new_pattern.strip(), cat_id, "regex", new_priority)
            )
            con.commit()
            con.close()
            st.success(f"Added rule: '{new_pattern.strip()}' → {new_rule_cat}")
            st.rerun()
        else:
            st.warning("Please enter a pattern.")

    st.divider()
    st.write("**Delete rule**")
    if rules:
        rule_labels    = [f"[{r[0]}] {r[1]} → {r[2]}" for r in rules]
        rule_to_delete = st.selectbox("Select rule to delete", rule_labels, key="delete_rule")
        if st.button("Delete Rule"):
            rule_id = int(rule_to_delete.split("]")[0].replace("[", ""))
            con = get_connection()
            cur = con.cursor()
            cur.execute("DELETE FROM CategoryRules WHERE CatRuleID = ?", (rule_id,))
            con.commit()
            con.close()
            st.success("Rule deleted.")
            st.rerun()
    else:
        st.info("No rules found.")