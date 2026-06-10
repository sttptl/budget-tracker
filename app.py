import streamlit as st
import pandas as pd
from src.visa_parser import parse_visa_csv
from src.categorizer import categorize_transactions
from src.db_setup import get_connection

st.set_page_config(page_title="Budget Tracker", layout="wide")

# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Budget Tracker")
    page = st.radio(
        "Navigation",
        ["Import", "Categories", "Rules"],
        label_visibility="collapsed"
    )

# ── Import page ───────────────────────────────────────────────────────────────
if page == "Import":
    st.header("Import Transactions")

    ACCOUNTS = ["TD Visa", "TD Chequing"]
    selected_account = st.selectbox("Select account", ACCOUNTS)

    uploaded_file = st.file_uploader("Upload a transaction CSV", type="csv")

    if uploaded_file is not None:
        if st.button("Process"):
            with st.spinner("Parsing and categorizing..."):
                txns = parse_visa_csv(uploaded_file)
                enriched = categorize_transactions(txns)
                for t in enriched:
                    t["amount"] = -t["amount"]
                st.session_state["transactions"] = enriched
                st.session_state["account"] = selected_account
            st.success(f"Loaded {len(enriched)} transactions.")

    if "transactions" in st.session_state:
        txns = st.session_state["transactions"]

        total_spent   = sum(t["amount"] for t in txns if t["amount"] < 0)
        payments_in   = sum(t["amount"] for t in txns if t["amount"] > 0)
        uncategorized = sum(1 for t in txns if t["category"] == "Uncategorized")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Spent",    f"${abs(total_spent):,.2f}")
        col2.metric("Payments In",    f"${payments_in:,.2f}")
        col3.metric("Transactions",   len(txns))
        col4.metric("Uncategorized",  uncategorized)

        st.divider()

        # Pull categories fresh from DB for the dropdown
        con = get_connection()
        cur = con.cursor()
        cur.execute("SELECT CategoryName FROM categories ORDER BY CategoryName")
        CATEGORIES = [r[0] for r in cur.fetchall()]
        con.close()

        df = pd.DataFrame([{
            "date":        t["date"].strftime("%Y-%m-%d"),
            "description": t["description_raw"],
            "amount":      t["amount"],
            "category":    t["category"],
            "match_rule":  t.get("match_rule", ""),
            "confidence":  t.get("confidence", 0.0),
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

    if "edited_df" in st.session_state:
        if st.button("Submit Review"):
            from src.db_writer import write_transactions
            result = write_transactions(
                st.session_state["edited_df"],
                st.session_state["transactions"],
                st.session_state["account"],
            )
            st.success(f"Done! {result['inserted']} transactions saved, {result['skipped']} duplicates skipped.")
            del st.session_state["transactions"]
            del st.session_state["edited_df"]
            del st.session_state["account"]

# ── Categories page ───────────────────────────────────────────────────────────
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

# ── Rules page ────────────────────────────────────────────────────────────────
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

    new_pattern  = st.text_input("Pattern (text to match in description)", key="new_rule_pattern")
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
        rule_labels = [f"[{r[0]}] {r[1]} → {r[2]}" for r in rules]
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