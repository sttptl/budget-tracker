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
        "txn_id":      t["id"],
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
            "txn_id":      None,
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


    uncat_count = (edited_df["category"] == "Uncategorized").sum()
    if uncat_count > 0:
        st.warning(f"{uncat_count} transaction(s) still uncategorized — assign a category to each before submitting.")

    if st.button("Submit Review", disabled=uncat_count > 0):
        if not st.session_state.get("submitted"):
            st.session_state["submitted"] = True
            from src.db_writer import write_transactions
            result = write_transactions(
                st.session_state["edited_df"],
                st.session_state["transactions"],
                st.session_state["account"],
            )
            for key in ["transactions", "edited_df", "account"]:
                st.session_state.pop(key, None)
            st.success(
                f"Done! {result['inserted']} transactions saved, "
                f"{result['skipped']} duplicates skipped."
            )


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
                "txn_id":      t["id"],
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
                    "txn_id":      None,
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
                "txn_id":      t["id"],
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
                    "txn_id":      None,
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

    allocations_valid = st.session_state.get("allocations_valid", True) if income_txns else True
    edited_expense_df = st.session_state.get("edited_expense_df", pd.DataFrame())
    edited_income_df  = st.session_state.get("edited_income_df",  pd.DataFrame())
    uncat_expenses = (edited_expense_df["category"] == "Uncategorized").sum() if not edited_expense_df.empty else 0
    uncat_income   = (edited_income_df["category"]  == "Uncategorized").sum() if not edited_income_df.empty  else 0
    uncat_total    = uncat_expenses + uncat_income
    if uncat_total > 0:
        st.warning(f"{uncat_total} transaction(s) still uncategorized — assign a category to each before submitting.")

    if st.button("Submit Review", disabled=not allocations_valid or uncat_total > 0):
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
        ["Import", "Configuration"],
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
                st.session_state["submitted"]    = False  # reset guard for new import
            st.success(f"Loaded {len(enriched)} transactions.")

    if "transactions" in st.session_state:
        if st.session_state.get("account") == "TD Chequing":
            _render_chequing_review()
        else:
            _render_visa_review()


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION PAGE
# ══════════════════════════════════════════════════════════════════════════════

elif page == "Configuration":
    st.header("Configuration")
    tab_rules, tab_cats, tab_buckets = st.tabs(["Rules", "Categories", "Buckets"])

    # ── RULES TAB ─────────────────────────────────────────────────────────────
    with tab_rules:
        st.subheader("Category Rules")

        con = get_connection()
        cur = con.cursor()
        cur.execute("""
            SELECT cr.CatRuleID, cr.Pattern, c.CategoryName, cr.MatchType, cr.Priority
            FROM CategoryRules cr
            JOIN categories c ON cr.CategoryID = c.CategoryID
            ORDER BY cr.Priority DESC
        """)
        rules = cur.fetchall()
        cur.execute("SELECT CategoryName FROM categories ORDER BY CategoryName")
        all_cats = [r[0] for r in cur.fetchall()]
        con.close()

        rules_df = pd.DataFrame(rules, columns=["ID", "Pattern", "Category", "Match Type", "Priority"])
        st.dataframe(rules_df, use_container_width=True, hide_index=True)

        st.divider()
        st.write("**Add new rule**")

        new_pattern  = st.text_input("Pattern (regex matched against description)", key="new_rule_pattern")
        new_priority = st.slider("Priority (higher = evaluated first)", 1, 100, 80, key="new_rule_priority")

        ADD_CAT_SENTINEL = "➕ Add new category..."
        cat_options = all_cats + [ADD_CAT_SENTINEL]
        selected_cat = st.selectbox("Category", cat_options, key="new_rule_cat")

        # Cascading: adding a new category
        final_category = selected_cat  # will be overridden below if user is creating one
        if selected_cat == ADD_CAT_SENTINEL:
            new_cat_name = st.text_input("New category name", key="inline_new_cat_name")

            ADD_BUCKET_SENTINEL = "➕ Add new bucket..."
            buckets = _get_buckets()
            bucket_options = buckets + [ADD_BUCKET_SENTINEL]
            selected_bucket = st.selectbox("Assign to bucket", bucket_options, key="inline_new_cat_bucket")

            # Cascading: adding a new bucket
            final_bucket = selected_bucket
            if selected_bucket == ADD_BUCKET_SENTINEL:
                new_bucket_name = st.text_input("New bucket name", key="inline_new_bucket_name")
                final_bucket = new_bucket_name.strip() if new_bucket_name.strip() else None
            
            final_category = new_cat_name.strip() if new_cat_name.strip() else None
        
        if st.button("Add Rule"):
            if not new_pattern.strip():
                st.warning("Please enter a pattern.")
            elif not final_category:
                st.warning("Please enter a category name.")
            else:
                con = get_connection()
                cur = con.cursor()
                try:
                    # 1. Create bucket if needed
                    if selected_cat == ADD_CAT_SENTINEL:
                        if not final_bucket:
                            st.warning("Please enter a bucket name.")
                            con.close()
                            st.stop()
                        cur.execute("INSERT OR IGNORE INTO buckets (BucketName) VALUES (?)", (final_bucket,))
                        cur.execute("SELECT BucketID FROM buckets WHERE BucketName = ?", (final_bucket,))
                        bucket_id = cur.fetchone()[0]
                        # 2. Create category if needed
                        cur.execute(
                            "INSERT OR IGNORE INTO categories (CategoryName, BucketID) VALUES (?, ?)",
                            (final_category, bucket_id),
                        )
                    # 3. Resolve category ID
                    cur.execute("SELECT CategoryID FROM categories WHERE CategoryName = ?", (final_category,))
                    cat_id = cur.fetchone()[0]
                    # 4. Insert rule
                    cur.execute(
                        "INSERT INTO CategoryRules (Pattern, CategoryID, MatchType, Priority) VALUES (?, ?, ?, ?)",
                        (new_pattern.strip(), cat_id, "regex", new_priority),
                    )
                    con.commit()
                    st.success(f"Added rule: '{new_pattern.strip()}' → {final_category}")
                except Exception as e:
                    st.error(f"Error: {e}")
                finally:
                    con.close()
                st.rerun()

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

    # ── CATEGORIES TAB ────────────────────────────────────────────────────────
    with tab_cats:
        st.subheader("Categories")

        con = get_connection()
        cur = con.cursor()
        cur.execute("""
            SELECT c.CategoryID, c.CategoryName, COALESCE(b.BucketName, '⚠ Unassigned') AS Bucket
            FROM categories c
            LEFT JOIN buckets b ON c.BucketID = b.BucketID
            ORDER BY c.CategoryName
        """)
        cats = cur.fetchall()
        con.close()

        cat_df = pd.DataFrame(cats, columns=["ID", "Category", "Bucket"])
        st.dataframe(cat_df, use_container_width=True, hide_index=True)

        st.divider()
        st.write("**Add new category**")
        buckets = _get_buckets()
        if not buckets:
            st.warning("You need at least one bucket before adding categories. Go to the **Buckets** tab first.")
        else:
            new_cat        = st.text_input("Category name", key="new_cat_input")
            new_cat_bucket = st.selectbox("Assign to bucket", buckets, key="new_cat_bucket")
            if st.button("Add Category"):
                if new_cat.strip():
                    con = get_connection()
                    cur = con.cursor()
                    try:
                        cur.execute("SELECT BucketID FROM buckets WHERE BucketName = ?", (new_cat_bucket,))
                        bucket_id = cur.fetchone()[0]
                        cur.execute(
                            "INSERT INTO categories (CategoryName, BucketID) VALUES (?, ?)",
                            (new_cat.strip(), bucket_id),
                        )
                        con.commit()
                        st.success(f"Added: {new_cat.strip()} → {new_cat_bucket}")
                    except Exception as e:
                        st.error(f"Error: {e}")
                    finally:
                        con.close()
                    st.rerun()
                else:
                    st.warning("Please enter a category name.")

        st.divider()
        st.write("**Reassign bucket**")
        unassigned = [c for c in cats if c[2] == "⚠ Unassigned"]
        if unassigned:
            st.warning(f"{len(unassigned)} categor{'y' if len(unassigned) == 1 else 'ies'} not yet assigned to a bucket.")
        if cats and buckets:
            cat_names         = [c[1] for c in cats]
            cat_to_reassign   = st.selectbox("Select category", cat_names, key="reassign_cat")
            new_bucket_assign = st.selectbox("Assign to bucket", buckets, key="reassign_bucket")
            if st.button("Save Assignment"):
                con = get_connection()
                cur = con.cursor()
                cur.execute("SELECT BucketID FROM buckets WHERE BucketName = ?", (new_bucket_assign,))
                bucket_id = cur.fetchone()[0]
                cur.execute(
                    "UPDATE categories SET BucketID = ? WHERE CategoryName = ?",
                    (bucket_id, cat_to_reassign),
                )
                con.commit()
                con.close()
                st.success(f"Updated: {cat_to_reassign} → {new_bucket_assign}")
                st.rerun()

        st.divider()
        st.write("**Delete category**")
        cat_names = [c[1] for c in cats]
        if cat_names:
            cat_to_delete = st.selectbox("Select category to delete", cat_names, key="delete_cat")
            if st.button("Delete Category"):
                con = get_connection()
                cur = con.cursor()
                cur.execute("SELECT CategoryID FROM categories WHERE CategoryName = ?", (cat_to_delete,))
                row = cur.fetchone()
                if row:
                    cur.execute("DELETE FROM CategoryRules WHERE CategoryID = ?", (row[0],))
                cur.execute("DELETE FROM categories WHERE CategoryName = ?", (cat_to_delete,))
                con.commit()
                con.close()
                st.success(f"Deleted: {cat_to_delete}")
                st.rerun()
                
    # ── BUCKETS TAB ───────────────────────────────────────────────────────────
    with tab_buckets:
        st.subheader("Buckets")

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
            bucket_names     = [b[1] for b in bucket_rows]
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
