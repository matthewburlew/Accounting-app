import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime, date
import io

# ── Theme ─────────────────────────────────────────────────────────────────────

CSS = """
<style>
.stApp { background: linear-gradient(160deg, #0f1923 0%, #1a2634 50%, #0f1923 100%); }
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #1a2634, #0f1923);
    border: 1px solid #00b89440;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 0 12px #00b89420;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0a1520 0%, #1a2634 100%);
    border-right: 1px solid #00b89430;
}
hr { border-color: #00b89430 !important; }
.stButton > button { border-radius: 8px; font-weight: 600; transition: all 0.2s; }
.stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px #00b89440; }
.stTabs [data-baseweb="tab-list"] { background: #1a2634; border-radius: 10px; padding: 4px; }
.stTabs [data-baseweb="tab"] { border-radius: 8px; font-weight: 600; }
[data-testid="stAlert"] { border-radius: 10px; }
</style>
"""

# ── Categories ────────────────────────────────────────────────────────────────

INCOME_CATS = ["Sales", "Services", "Consulting", "Freelance", "Rental Income", "Investment", "Refund", "Other Income"]
EXPENSE_CATS = ["Rent", "Utilities", "Supplies", "Software", "Marketing", "Payroll", "Travel", "Insurance",
                "Equipment", "Taxes", "Meals", "Subscriptions", "Shipping", "Legal", "Other Expense"]
PAYMENT_METHODS = ["Cash", "Credit Card", "Bank Transfer", "Check", "PayPal", "Venmo", "Stripe", "Other"]
INVOICE_STATUS = ["Unpaid", "Paid", "Overdue", "Cancelled"]


# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect("bookkeeping.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, type TEXT, category TEXT, amount REAL,
            description TEXT, payment_method TEXT, client TEXT, notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE, email TEXT, phone TEXT, address TEXT, notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT, client TEXT, date_issued TEXT, due_date TEXT,
            items TEXT, subtotal REAL, tax_rate REAL, total REAL, status TEXT, notes TEXT
        )
    """)
    conn.commit()
    conn.close()


def q(sql, params=(), fetch=False):
    conn = sqlite3.connect("bookkeeping.db")
    cur = conn.execute(sql, params)
    conn.commit()
    result = cur.fetchall() if fetch else None
    conn.close()
    return result


def get_df(sql, params=()):
    conn = sqlite3.connect("bookkeeping.db")
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


# ── Helpers ───────────────────────────────────────────────────────────────────

def next_invoice_number():
    rows = q("SELECT invoice_number FROM invoices ORDER BY id DESC LIMIT 1", fetch=True)
    if not rows:
        return "INV-0001"
    try:
        num = int(rows[0][0].split("-")[1]) + 1
        return f"INV-{num:04d}"
    except Exception:
        return "INV-0001"


def get_clients():
    rows = q("SELECT name FROM clients ORDER BY name", fetch=True)
    return [r[0] for r in rows] if rows else []


# ── Dashboard ─────────────────────────────────────────────────────────────────

def show_dashboard():
    st.title("📊 Dashboard")

    df = get_df("SELECT * FROM transactions")
    invoices = get_df("SELECT * FROM invoices")

    if df.empty:
        st.info("No transactions yet. Go to **Add Transaction** to get started!")
        return

    df["date"] = pd.to_datetime(df["date"])
    now = datetime.now()
    this_month = df[df["date"].dt.month == now.month]

    total_income = df[df["type"] == "Income"]["amount"].sum()
    total_expenses = df[df["type"] == "Expense"]["amount"].sum()
    net_profit = total_income - total_expenses
    mo_income = this_month[this_month["type"] == "Income"]["amount"].sum()
    mo_expense = this_month[this_month["type"] == "Expense"]["amount"].sum()
    mo_profit = mo_income - mo_expense
    unpaid = invoices[invoices["status"] == "Unpaid"]["total"].sum() if not invoices.empty else 0
    overdue = invoices[invoices["status"] == "Overdue"]["total"].sum() if not invoices.empty else 0

    st.markdown("#### All-Time Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Revenue", f"${total_income:,.2f}")
    c2.metric("Total Expenses", f"${total_expenses:,.2f}")
    c3.metric("Net Profit", f"${net_profit:+,.2f}")
    c4.metric("Outstanding Invoices", f"${unpaid:,.2f}",
              delta=f"${overdue:.2f} overdue" if overdue else None)

    st.markdown("#### This Month")
    c1, c2, c3 = st.columns(3)
    c1.metric("Revenue", f"${mo_income:,.2f}")
    c2.metric("Expenses", f"${mo_expense:,.2f}")
    c3.metric("Net", f"${mo_profit:+,.2f}")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Monthly Revenue vs Expenses")
        df["month"] = df["date"].dt.to_period("M").astype(str)
        monthly = df.groupby(["month", "type"])["amount"].sum().reset_index()
        fig = px.bar(monthly, x="month", y="amount", color="type", barmode="group",
                     color_discrete_map={"Income": "#00b894", "Expense": "#d63031"})
        fig.update_layout(margin=dict(t=0, b=0), xaxis_title="", yaxis_title="$",
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Spending by Category")
        expenses = df[df["type"] == "Expense"]
        if not expenses.empty:
            cat_totals = expenses.groupby("category")["amount"].sum().reset_index()
            fig2 = px.pie(cat_totals, values="amount", names="category", hole=0.4)
            fig2.update_layout(margin=dict(t=0, b=0), plot_bgcolor="rgba(0,0,0,0)",
                               paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("#### Profit Over Time")
    df_sorted = df.sort_values("date")
    df_sorted["profit_contribution"] = df_sorted.apply(
        lambda r: r["amount"] if r["type"] == "Income" else -r["amount"], axis=1
    )
    df_sorted["cumulative_profit"] = df_sorted["profit_contribution"].cumsum()
    fig3 = px.area(df_sorted, x="date", y="cumulative_profit", color_discrete_sequence=["#00b894"])
    fig3.add_hline(y=0, line_dash="dash", line_color="gray")
    fig3.update_layout(xaxis_title="", yaxis_title="Profit ($)", margin=dict(t=0, b=0),
                       plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown("#### Recent Transactions")
    recent = df.sort_values("date", ascending=False).head(8)
    for _, row in recent.iterrows():
        icon = "🟢" if row["type"] == "Income" else "🔴"
        c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
        c1.write(f"{icon} {row['date'].strftime('%Y-%m-%d')}")
        c2.write(f"**{row['description'] or row['category']}**\n\n{row['category']}")
        c3.write(row.get("client") or "—")
        amount_str = f"+${row['amount']:,.2f}" if row["type"] == "Income" else f"-${row['amount']:,.2f}"
        c4.write(f"**{amount_str}**")


# ── Add Transaction ───────────────────────────────────────────────────────────

def show_add_transaction():
    st.title("➕ Add Transaction")
    st.caption("Record any money coming in (income) or going out (expense).")

    clients = ["— None —"] + get_clients()

    with st.form("transaction_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            trans_type = st.selectbox("Type", ["Income", "Expense"],
                                      help="Income = money you received. Expense = money you spent.")
            category = st.selectbox("Category",
                                    INCOME_CATS if trans_type == "Income" else EXPENSE_CATS)
            amount = st.number_input("Amount ($)", min_value=0.01, step=1.0, format="%.2f")
            trans_date = st.date_input("Date", value=date.today())
        with c2:
            description = st.text_input("Description", placeholder="e.g. Website design for client")
            client = st.selectbox("Client (optional)", clients)
            payment_method = st.selectbox("Payment Method", PAYMENT_METHODS)
            notes = st.text_area("Notes (optional)", height=80)

        if st.form_submit_button("Save Transaction", use_container_width=True, type="primary"):
            client_val = client if client != "— None —" else ""
            q("INSERT INTO transactions (date,type,category,amount,description,payment_method,client,notes) VALUES (?,?,?,?,?,?,?,?)",
              (str(trans_date), trans_type, category, amount, description, payment_method, client_val, notes))
            st.success(f"Saved! {trans_type} of **${amount:,.2f}** — {category}")
            st.balloons()


# ── Transactions ──────────────────────────────────────────────────────────────

def show_transactions():
    st.title("📋 All Transactions")

    df = get_df("SELECT * FROM transactions ORDER BY date DESC")
    if df.empty:
        st.info("No transactions yet.")
        return

    df["date"] = pd.to_datetime(df["date"])

    c1, c2, c3 = st.columns(3)
    with c1:
        type_filter = st.selectbox("Type", ["All", "Income", "Expense"])
    with c2:
        months = ["All"] + sorted(df["date"].dt.to_period("M").astype(str).unique().tolist(), reverse=True)
        month_filter = st.selectbox("Month", months)
    with c3:
        all_cats = ["All"] + sorted(df["category"].unique().tolist())
        cat_filter = st.selectbox("Category", all_cats)

    filtered = df.copy()
    if type_filter != "All":
        filtered = filtered[filtered["type"] == type_filter]
    if month_filter != "All":
        filtered = filtered[filtered["date"].dt.to_period("M").astype(str) == month_filter]
    if cat_filter != "All":
        filtered = filtered[filtered["category"] == cat_filter]

    total_in = filtered[filtered["type"] == "Income"]["amount"].sum()
    total_out = filtered[filtered["type"] == "Expense"]["amount"].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Income (filtered)", f"${total_in:,.2f}")
    c2.metric("Expenses (filtered)", f"${total_out:,.2f}")
    c3.metric("Net (filtered)", f"${total_in - total_out:+,.2f}")

    csv_buf = io.StringIO()
    filtered.to_csv(csv_buf, index=False)
    st.download_button("⬇️ Export to CSV", csv_buf.getvalue(), "transactions.csv", "text/csv")

    st.divider()

    for _, row in filtered.iterrows():
        icon = "🟢" if row["type"] == "Income" else "🔴"
        c1, c2, c3, c4, c5, c6 = st.columns([2, 3, 2, 2, 2, 1])
        c1.write(f"{icon} {row['date'].strftime('%Y-%m-%d')}")
        c2.write(f"**{row['description'] or '—'}**\n\n{row['category']}")
        c3.write(row.get("client") or "—")
        c4.write(row.get("payment_method") or "—")
        amount_str = f"+${row['amount']:,.2f}" if row["type"] == "Income" else f"-${row['amount']:,.2f}"
        c5.write(f"**{amount_str}**")
        if c6.button("🗑", key=f"del_t_{row['id']}"):
            q("DELETE FROM transactions WHERE id=?", (int(row["id"]),))
            st.rerun()
        st.divider()


# ── Clients ───────────────────────────────────────────────────────────────────

def show_clients():
    st.title("👥 Clients")

    tab1, tab2 = st.tabs(["Client List", "Add Client"])

    with tab1:
        df = get_df("SELECT * FROM clients ORDER BY name")
        if df.empty:
            st.info("No clients yet. Add one using the tab above.")
        else:
            transactions = get_df("SELECT * FROM transactions")
            for _, row in df.iterrows():
                with st.expander(f"**{row['name']}**   {row.get('email') or ''}"):
                    c1, c2 = st.columns(2)
                    c1.write(f"📧 {row.get('email') or '—'}")
                    c1.write(f"📞 {row.get('phone') or '—'}")
                    c2.write(f"📍 {row.get('address') or '—'}")
                    if row.get("notes"):
                        st.caption(row["notes"])
                    if not transactions.empty:
                        client_txns = transactions[transactions["client"] == row["name"]]
                        if not client_txns.empty:
                            revenue = client_txns[client_txns["type"] == "Income"]["amount"].sum()
                            st.metric("Total Revenue from Client", f"${revenue:,.2f}")
                    if st.button("Delete Client", key=f"del_c_{row['id']}"):
                        q("DELETE FROM clients WHERE id=?", (int(row["id"]),))
                        st.rerun()

    with tab2:
        st.subheader("Add a New Client")
        with st.form("client_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Full Name / Business Name *")
                email = st.text_input("Email")
            with c2:
                phone = st.text_input("Phone")
                address = st.text_area("Address", height=80)
            notes = st.text_input("Notes (optional)")
            if st.form_submit_button("Add Client", use_container_width=True, type="primary"):
                if not name:
                    st.error("Name is required.")
                else:
                    try:
                        q("INSERT INTO clients (name,email,phone,address,notes) VALUES (?,?,?,?,?)",
                          (name, email, phone, address, notes))
                        st.success(f"Client **{name}** added!")
                    except Exception:
                        st.error("A client with that name already exists.")


# ── Invoices ──────────────────────────────────────────────────────────────────

def show_invoices():
    st.title("🧾 Invoices")

    tab1, tab2 = st.tabs(["All Invoices", "Create Invoice"])

    with tab1:
        df = get_df("SELECT * FROM invoices ORDER BY date_issued DESC")
        if df.empty:
            st.info("No invoices yet. Create one using the tab above.")
        else:
            status_filter = st.selectbox("Filter by Status", ["All"] + INVOICE_STATUS)
            filtered = df if status_filter == "All" else df[df["status"] == status_filter]

            unpaid = df[df["status"] == "Unpaid"]["total"].sum()
            overdue = df[df["status"] == "Overdue"]["total"].sum()
            paid = df[df["status"] == "Paid"]["total"].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Unpaid", f"${unpaid:,.2f}")
            c2.metric("Overdue", f"${overdue:,.2f}")
            c3.metric("Collected", f"${paid:,.2f}")
            st.divider()

            for _, row in filtered.iterrows():
                status_color = {"Paid": "🟢", "Unpaid": "🟡", "Overdue": "🔴", "Cancelled": "⚫"}.get(row["status"], "⚪")
                with st.expander(f"{status_color} **{row['invoice_number']}** — {row['client']} — ${row['total']:,.2f}"):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Issued:** {row['date_issued']}")
                    c1.write(f"**Due:** {row['due_date']}")
                    c2.write(f"**Subtotal:** ${row['subtotal']:,.2f}")
                    c2.write(f"**Tax ({row['tax_rate']}%):** ${row['subtotal'] * row['tax_rate'] / 100:,.2f}")
                    c3.write(f"**Total: ${row['total']:,.2f}**")
                    if row.get("notes"):
                        st.caption(f"Notes: {row['notes']}")
                    new_status = st.selectbox("Update Status", INVOICE_STATUS,
                                              index=INVOICE_STATUS.index(row["status"]),
                                              key=f"status_{row['id']}")
                    col1, col2 = st.columns(2)
                    if col1.button("Update Status", key=f"upd_{row['id']}"):
                        q("UPDATE invoices SET status=? WHERE id=?", (new_status, int(row["id"])))
                        if new_status == "Paid":
                            q("INSERT INTO transactions (date,type,category,amount,description,payment_method,client,notes) VALUES (?,?,?,?,?,?,?,?)",
                              (date.today().isoformat(), "Income", "Services",
                               row["total"], f"Invoice {row['invoice_number']}", "Other", row["client"], ""))
                            st.success("Status updated and income recorded!")
                        st.rerun()
                    if col2.button("Delete", key=f"del_inv_{row['id']}"):
                        q("DELETE FROM invoices WHERE id=?", (int(row["id"]),))
                        st.rerun()

    with tab2:
        st.subheader("Create a New Invoice")
        clients = get_clients()
        if not clients:
            st.warning("Add a client first before creating an invoice.")
            return
        with st.form("invoice_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                client = st.selectbox("Client", clients)
                date_issued = st.date_input("Date Issued", value=date.today())
                due_date = st.date_input("Due Date")
            with c2:
                inv_number = st.text_input("Invoice Number", value=next_invoice_number())
                tax_rate = st.number_input("Tax Rate (%)", min_value=0.0, max_value=50.0, value=0.0, step=0.5)
                status = st.selectbox("Status", INVOICE_STATUS)
            st.markdown("**Line Items** — one per line as: Description, Amount")
            items_raw = st.text_area("Items", height=120,
                                     placeholder="Web Design, 500\nHosting Setup, 150\nLogo Design, 200")
            notes = st.text_input("Notes (optional)")

            subtotal = 0.0
            if items_raw:
                for line in items_raw.strip().split("\n"):
                    parts = line.rsplit(",", 1)
                    if len(parts) == 2:
                        try:
                            subtotal += float(parts[1].strip())
                        except ValueError:
                            pass
            total = subtotal * (1 + tax_rate / 100)
            st.info(f"Subtotal: **${subtotal:,.2f}** · Tax: **${subtotal * tax_rate / 100:,.2f}** · Total: **${total:,.2f}**")

            if st.form_submit_button("Create Invoice", use_container_width=True, type="primary"):
                q("INSERT INTO invoices (invoice_number,client,date_issued,due_date,items,subtotal,tax_rate,total,status,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (inv_number, client, str(date_issued), str(due_date), items_raw, subtotal, tax_rate, total, status, notes))
                st.success(f"Invoice **{inv_number}** created for {client} — **${total:,.2f}**")


# ── P&L Report ────────────────────────────────────────────────────────────────

def show_reports():
    st.title("📈 Profit & Loss Report")

    df = get_df("SELECT * FROM transactions")
    if df.empty:
        st.info("No transactions to report on yet.")
        return

    df["date"] = pd.to_datetime(df["date"])
    c1, c2 = st.columns(2)
    with c1:
        year_options = sorted(df["date"].dt.year.unique().tolist(), reverse=True)
        selected_year = st.selectbox("Year", year_options)
    with c2:
        month_options = ["Full Year", "January", "February", "March", "April", "May", "June",
                         "July", "August", "September", "October", "November", "December"]
        selected_month = st.selectbox("Month", month_options)

    filtered = df[df["date"].dt.year == selected_year]
    if selected_month != "Full Year":
        month_num = month_options.index(selected_month)
        filtered = filtered[filtered["date"].dt.month == month_num]

    income = filtered[filtered["type"] == "Income"]
    expenses = filtered[filtered["type"] == "Expense"]
    total_income = income["amount"].sum()
    total_expenses = expenses["amount"].sum()
    net = total_income - total_expenses
    margin = (net / total_income * 100) if total_income > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Revenue", f"${total_income:,.2f}")
    c2.metric("Total Expenses", f"${total_expenses:,.2f}")
    c3.metric("Net Profit", f"${net:+,.2f}")
    c4.metric("Profit Margin", f"{margin:.1f}%")

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Income by Category")
        if not income.empty:
            inc_cat = income.groupby("category")["amount"].sum().reset_index()
            inc_cat.columns = ["Category", "Amount"]
            fig = px.bar(inc_cat, x="Category", y="Amount", color_discrete_sequence=["#00b894"])
            fig.update_layout(margin=dict(t=0), xaxis_title="", yaxis_title="$",
                               plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Expenses by Category")
        if not expenses.empty:
            exp_cat = expenses.groupby("category")["amount"].sum().reset_index()
            exp_cat.columns = ["Category", "Amount"]
            fig2 = px.pie(exp_cat, values="Amount", names="Category", hole=0.4)
            fig2.update_layout(margin=dict(t=0), plot_bgcolor="rgba(0,0,0,0)",
                               paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.markdown("#### P&L Statement")
    st.markdown(f"""
| | Amount |
|---|---|
| **Total Revenue** | **${total_income:,.2f}** |
| Total Expenses | ${total_expenses:,.2f} |
| **Net Profit** | **${net:+,.2f}** |
| Profit Margin | {margin:.1f}% |
""")
    csv_buf = io.StringIO()
    filtered.to_csv(csv_buf, index=False)
    st.download_button("⬇️ Export Report as CSV", csv_buf.getvalue(), "pl_report.csv", "text/csv")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Bookkeeping", page_icon="📒", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    init_db()

    with st.sidebar:
        st.title("📒 Bookkeeping")
        st.divider()
        page = st.radio("", [
            "📊 Dashboard",
            "➕ Add Transaction",
            "📋 Transactions",
            "👥 Clients",
            "🧾 Invoices",
            "📈 P&L Report",
        ], label_visibility="collapsed")
        st.divider()
        st.caption("Track income, expenses, clients & invoices all in one place.")

    page_name = page.split(" ", 1)[-1]
    if page_name == "Dashboard":
        show_dashboard()
    elif page_name == "Add Transaction":
        show_add_transaction()
    elif page_name == "Transactions":
        show_transactions()
    elif page_name == "Clients":
        show_clients()
    elif page_name == "Invoices":
        show_invoices()
    elif page_name == "P&L Report":
        show_reports()


if __name__ == "__main__":
    main()
