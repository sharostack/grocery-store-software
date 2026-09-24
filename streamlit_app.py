"""Streamlit frontend for the Sunshine Mart SQLite inventory system."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st

from database import InventoryDatabase
from employee_auth import employee_details_password_is_valid, employee_records_for_display


LOW_STOCK_THRESHOLD = 20
NAV_PAGES = [
    "Dashboard",
    "Inventory",
    "Billing",
    "Sales & Reports",
    "Employee Details",
    "ETL & Data Quality",
]

PRODUCT_DISPLAY_COLUMNS = {
    "product_id": "Product ID",
    "department": "Department",
    "name": "Product",
    "unit_cost": "Unit Cost (Rs)",
    "initial_quantity": "Initial Qty",
    "quantity_sold": "Qty Sold",
    "quantity_available": "Available",
}


@st.cache_resource
def get_database():
    database = InventoryDatabase()
    database.initialize()
    return database


def frame(rows):
    """Convert SQLite rows into a dataframe for Streamlit display."""
    return pd.DataFrame([dict(row) for row in rows])


def refresh_with_message(message):
    """Persist confirmation across Streamlit's refresh after a database write."""
    st.session_state["database_message"] = message
    st.rerun()


def apply_theme():
    """Apply compact, professional styling without changing Streamlit behavior."""
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid rgba(128, 128, 128, 0.25);
        }
        [data-testid="stSidebar"] .block-container {
            padding-top: 1.2rem;
        }
        .app-sidebar-title {
            font-size: 1.35rem;
            font-weight: 700;
            margin: 0 0 0.15rem 0;
            letter-spacing: -0.02em;
        }
        .app-sidebar-subtitle {
            font-size: 0.85rem;
            opacity: 0.75;
            margin: 0 0 1rem 0;
        }
        .page-kicker {
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            opacity: 0.7;
            margin-bottom: 0.2rem;
        }
        div[data-testid="stMetric"] {
            background: rgba(128, 128, 128, 0.08);
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 10px;
            padding: 0.85rem 1rem;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.35rem;
        }
        .summary-panel {
            background: rgba(11, 110, 79, 0.12);
            border: 1px solid rgba(11, 110, 79, 0.35);
            border-radius: 10px;
            padding: 1rem 1.1rem;
        }
        .summary-total {
            font-size: 1.45rem;
            font-weight: 700;
            color: #1f9d6e;
            margin-top: 0.35rem;
        }
        .status-pill {
            display: inline-block;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .status-success { background: rgba(11, 110, 79, 0.18); color: #1f9d6e; }
        .status-failed { background: rgba(155, 28, 28, 0.18); color: #e03131; }
        .status-running { background: rgba(138, 109, 29, 0.18); color: #e0a800; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def money(value) -> str:
    return f"Rs {float(value):,.2f}"


def integer(value) -> str:
    return f"{int(value):,}"


def page_header(title: str, subtitle: str | None = None, kicker: str | None = None):
    if kicker:
        st.markdown(f'<div class="page-kicker">{kicker}</div>', unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def section_header(title: str, caption: str | None = None):
    st.subheader(title)
    if caption:
        st.caption(caption)


def render_kpi_row(items):
    columns = st.columns(len(items))
    for column, (label, value) in zip(columns, items):
        column.metric(label, value)


def styled_dataframe(data, column_map=None, column_config=None):
    table = data.copy()
    if column_map:
        present = {key: label for key, label in column_map.items() if key in table.columns}
        table = table.rename(columns=present)
        ordered = [label for key, label in column_map.items() if label in table.columns]
        extras = [column for column in table.columns if column not in ordered]
        table = table[ordered + extras]
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
    )


def empty_state(message: str):
    st.info(message)


def render_sidebar():
    st.sidebar.markdown('<p class="app-sidebar-title">Sunshine Mart</p>', unsafe_allow_html=True)
    st.sidebar.markdown(
        '<p class="app-sidebar-subtitle">Inventory &amp; Billing System</p>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("---")
    page = st.sidebar.radio("Navigation", NAV_PAGES, label_visibility="collapsed")
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Current section: **{page}**")
    st.sidebar.caption("SQLite-backed operational data")
    return page


def show_dashboard(db):
    page_header(
        "Sunshine Mart",
        "Inventory, sales and operational overview",
        kicker="Dashboard",
    )
    metrics = db.dashboard_metrics(LOW_STOCK_THRESHOLD)
    render_kpi_row(
        [
            ("Products", integer(metrics["total_products"])),
            ("Inventory Quantity", integer(metrics["total_inventory_quantity"])),
            ("Inventory Value", money(metrics["total_inventory_value"])),
        ]
    )
    render_kpi_row(
        [
            ("Total Revenue", money(metrics["total_revenue"])),
            ("Transactions", integer(metrics["transaction_count"])),
            (f"Low Stock (≤ {LOW_STOCK_THRESHOLD})", integer(metrics["low_stock_products"])),
        ]
    )

    st.markdown("")
    section_header("Sales Overview", "Historic monthly sales totals from the source analytics tables.")
    monthly = frame(db.monthly_totals())
    if monthly.empty:
        empty_state("No monthly sales data is available yet.")
    else:
        left, right = st.columns((2, 1))
        with left:
            st.bar_chart(monthly.set_index("month_name")["total"], height=280)
        with right:
            styled_dataframe(
                monthly[["month_name", "total", "employee_contribution_total"]],
                {
                    "month_name": "Month",
                    "total": "Total Sales",
                    "employee_contribution_total": "Employee Contribution",
                },
                column_config={
                    "Total Sales": st.column_config.NumberColumn(format="Rs %.2f"),
                    "Employee Contribution": st.column_config.NumberColumn(format="Rs %.2f"),
                },
            )

    st.markdown("")
    section_header("Inventory Overview", "Current available stock grouped by department.")
    department_data = frame(db.inventory_by_department())
    if department_data.empty:
        empty_state("No inventory is available yet.")
    else:
        left, right = st.columns(2)
        with left:
            st.bar_chart(department_data.set_index("department")["quantity_available"], height=280)
        with right:
            styled_dataframe(
                department_data,
                {
                    "department": "Department",
                    "quantity_available": "Available Qty",
                    "inventory_value": "Inventory Value",
                },
                column_config={
                    "Available Qty": st.column_config.NumberColumn(format="%d"),
                    "Inventory Value": st.column_config.NumberColumn(format="Rs %.2f"),
                },
            )

    st.markdown("")
    section_header("Top Products", "Best-selling products by quantity from recorded sales.")
    top_products = frame(db.top_products_by_quantity())
    if top_products.empty:
        empty_state("No sales have been recorded yet.")
    else:
        left, right = st.columns((1, 1))
        with left:
            st.bar_chart(top_products.set_index("name")["units_sold"], height=280)
        with right:
            styled_dataframe(
                top_products,
                {
                    "product_id": "Product ID",
                    "name": "Product",
                    "department": "Department",
                    "units_sold": "Units Sold",
                    "revenue": "Revenue",
                },
                column_config={
                    "Units Sold": st.column_config.NumberColumn(format="%d"),
                    "Revenue": st.column_config.NumberColumn(format="Rs %.2f"),
                },
            )


def show_inventory(db):
    page_header("Inventory", "Browse stock, filter products, and manage catalogue records.", kicker="Operations")
    products = frame(db.products())
    if products.empty:
        empty_state("No products are loaded. Run the ETL pipeline or add a product below.")
        products = pd.DataFrame(
            columns=[
                "product_id",
                "department",
                "name",
                "unit_cost",
                "initial_quantity",
                "quantity_sold",
                "quantity_available",
            ]
        )

    low_stock = int((products["quantity_available"] <= LOW_STOCK_THRESHOLD).sum()) if not products.empty else 0
    inventory_value = float((products["unit_cost"] * products["quantity_available"]).sum()) if not products.empty else 0.0
    section_header("Inventory Overview")
    render_kpi_row(
        [
            ("Products", integer(len(products))),
            ("Units Available", integer(products["quantity_available"].sum() if not products.empty else 0)),
            ("Inventory Value", money(inventory_value)),
            (f"Low Stock (≤ {LOW_STOCK_THRESHOLD})", integer(low_stock)),
        ]
    )

    st.markdown("")
    section_header("Search & Filters")
    filter_left, filter_right = st.columns((1, 1))
    with filter_left:
        search = st.text_input("Search by product name or ID", placeholder="e.g. lipstick or 12")
    departments = sorted(products["department"].dropna().unique()) if not products.empty else []
    with filter_right:
        selected_departments = st.multiselect(
            "Department",
            departments,
            default=departments,
            placeholder="Select departments",
        )

    filtered = products[products["department"].isin(selected_departments)] if selected_departments else products.iloc[0:0]
    if search:
        term = search.strip().lower()
        filtered = filtered[
            filtered["name"].str.lower().str.contains(term, na=False)
            | filtered["product_id"].astype(str).str.contains(term, na=False)
        ]

    st.markdown("")
    section_header("Product Table", f"Showing {len(filtered)} of {len(products)} products.")
    if filtered.empty:
        empty_state("No products match the current filters.")
    else:
        styled_dataframe(
            filtered.sort_values(["quantity_available", "product_id"]),
            PRODUCT_DISPLAY_COLUMNS,
            column_config={
                "Unit Cost (Rs)": st.column_config.NumberColumn(format="Rs %.2f"),
                "Initial Qty": st.column_config.NumberColumn(format="%d"),
                "Qty Sold": st.column_config.NumberColumn(format="%d"),
                "Available": st.column_config.NumberColumn(format="%d"),
            },
        )

    st.markdown("")
    section_header("Add / Update / Delete")
    add_tab, stock_tab, delete_tab = st.tabs(["Add product", "Update stock", "Delete product"])
    with add_tab:
        with st.form("add_product_form", clear_on_submit=True):
            left, right = st.columns(2)
            product_id = left.number_input("Product ID", min_value=1, step=1)
            department = right.text_input("Department")
            name = left.text_input("Product name")
            unit_cost = right.number_input("Unit cost (Rs)", min_value=0.0, step=1.0)
            quantity = left.number_input("Available quantity", min_value=0, step=1)
            submitted = st.form_submit_button("Add product", type="primary")
        if submitted:
            try:
                db.add_product(int(product_id), department, name, float(unit_cost), int(quantity))
            except (ValueError, sqlite3.IntegrityError) as error:
                st.error(f"Product was not added: {error}")
            else:
                refresh_with_message("Product added to SQLite.")
    with stock_tab:
        if products.empty:
            empty_state("Add a product before updating stock.")
        else:
            product_options = {f"{row.product_id} — {row.name}": row.product_id for row in products.itertuples()}
            with st.form("update_stock_form"):
                selection = st.selectbox("Product", product_options)
                new_quantity = st.number_input("New available quantity", min_value=0, step=1)
                submitted = st.form_submit_button("Update stock", type="primary")
            if submitted:
                try:
                    db.update_inventory(product_options[selection], int(new_quantity))
                except ValueError as error:
                    st.error(str(error))
                else:
                    refresh_with_message("Inventory updated.")
    with delete_tab:
        st.warning("Products that appear in a completed sale cannot be deleted, preserving sales history.")
        if products.empty:
            empty_state("There are no products to delete.")
        else:
            with st.form("delete_product_form"):
                product_id = st.selectbox("Product to delete", products["product_id"].tolist())
                submitted = st.form_submit_button("Delete product", type="secondary")
            if submitted:
                try:
                    db.delete_product(int(product_id))
                except (ValueError, sqlite3.IntegrityError) as error:
                    st.error(f"Product was not deleted: {error}")
                else:
                    refresh_with_message("Product deleted.")


def show_billing(db):
    page_header("Billing", "Create a sale, review the cart, and record the transaction.", kicker="Operations")
    products = frame(db.products())
    available = products[products["quantity_available"] > 0]
    if available.empty:
        st.warning("No products are currently in stock.")
        return

    section_header("Available Products")
    styled_dataframe(
        available[["product_id", "name", "unit_cost", "quantity_available"]],
        {
            "product_id": "Product ID",
            "name": "Product",
            "unit_cost": "Unit Price",
            "quantity_available": "In Stock",
        },
        column_config={
            "Unit Price": st.column_config.NumberColumn(format="Rs %.2f"),
            "In Stock": st.column_config.NumberColumn(format="%d"),
        },
    )

    st.markdown("")
    section_header("New Sale", "Select products, set quantities, and optionally capture a customer email.")
    choices = {
        f"{row.product_id} — {row.name} (Rs {row.unit_cost:.2f}, stock {row.quantity_available})": row.product_id
        for row in available.itertuples()
    }
    selected = st.multiselect("Products", choices)

    with st.form("billing_form"):
        quantities = {}
        cart_rows = []
        for label in selected:
            product_id = choices[label]
            product_row = available.loc[available["product_id"] == product_id].iloc[0]
            max_quantity = int(product_row["quantity_available"])
            quantity = st.number_input(
                f"Quantity for {label}",
                min_value=1,
                max_value=max_quantity,
                value=1,
                step=1,
            )
            quantities[product_id] = quantity
            line_total = float(product_row["unit_cost"]) * int(quantity)
            cart_rows.append(
                {
                    "Product": product_row["name"],
                    "Quantity": int(quantity),
                    "Unit price": float(product_row["unit_cost"]),
                    "Line total": line_total,
                }
            )

        st.markdown("")
        section_header("Cart")
        if not cart_rows:
            st.caption("Select one or more products to build the cart.")
        else:
            cart = pd.DataFrame(cart_rows)
            styled_dataframe(
                cart,
                column_config={
                    "Quantity": st.column_config.NumberColumn(format="%d"),
                    "Unit price": st.column_config.NumberColumn(format="Rs %.2f"),
                    "Line total": st.column_config.NumberColumn(format="Rs %.2f"),
                },
            )
            subtotal = float(cart["Line total"].sum())
            vat = round(subtotal * 0.05)
            total = subtotal + vat
            st.markdown("")
            section_header("Bill Summary")
            summary_cols = st.columns(3)
            summary_cols[0].metric("Subtotal", money(subtotal))
            summary_cols[1].metric("VAT (5%)", money(vat))
            summary_cols[2].markdown(
                f'<div class="summary-panel">Total<div class="summary-total">{money(total)}</div></div>',
                unsafe_allow_html=True,
            )

        customer_email = st.text_input("Customer email (optional)")
        submitted = st.form_submit_button("Complete sale", type="primary")

    if submitted:
        if not selected:
            st.error("Select at least one product.")
            return
        try:
            sale_id, _, subtotal, vat, total = db.record_sale(
                [(product_id, int(quantity)) for product_id, quantity in quantities.items()],
                customer_email.strip() or None,
            )
        except ValueError as error:
            st.error(f"Sale was not recorded: {error}")
        else:
            refresh_with_message(
                f"Sale #{sale_id} recorded — Subtotal: Rs {subtotal:.2f}, "
                f"VAT: Rs {vat:.2f}, Total: Rs {total:.2f}."
            )


def show_sales_reports(db):
    page_header("Sales & Reports", "Review completed transactions and operational analytics.", kicker="Analytics")
    sales = frame(db.sales_history())
    report = frame(db.product_sales_report())
    department_revenue = frame(db.revenue_by_department())
    top_products = frame(db.top_products_by_quantity())
    turnover = frame(db.inventory_turnover_report())
    monthly = frame(db.monthly_totals())
    analytics = db.transaction_analytics()
    low_stock = frame(db.low_stock_products(LOW_STOCK_THRESHOLD))

    overview, revenue, performance, inventory = st.tabs(
        ["Sales Overview", "Revenue Analysis", "Product Performance", "Inventory Analytics"]
    )

    with overview:
        section_header("Sales Overview")
        render_kpi_row(
            [
                ("Transactions", integer(analytics["transaction_count"])),
                ("Average Transaction", money(analytics["average_transaction_value"])),
                ("Recorded Revenue", money(sales["total"].sum() if not sales.empty else 0)),
            ]
        )
        st.markdown("")
        section_header("Completed Transactions")
        if sales.empty:
            empty_state("No sales have been recorded yet.")
        else:
            styled_dataframe(
                sales,
                {
                    "sale_id": "Sale ID",
                    "sold_at": "Sold At",
                    "customer_email": "Customer Email",
                    "subtotal": "Subtotal",
                    "vat": "VAT",
                    "total": "Total",
                },
                column_config={
                    "Subtotal": st.column_config.NumberColumn(format="Rs %.2f"),
                    "VAT": st.column_config.NumberColumn(format="Rs %.2f"),
                    "Total": st.column_config.NumberColumn(format="Rs %.2f"),
                },
            )

        st.markdown("")
        section_header("Historic Monthly Sales")
        if monthly.empty:
            empty_state("No monthly sales history is available.")
        else:
            st.bar_chart(monthly.set_index("month_name")["total"], height=280)
            with st.expander("View monthly totals table"):
                styled_dataframe(
                    monthly[["month_name", "total", "employee_contribution_total"]],
                    {
                        "month_name": "Month",
                        "total": "Total Sales",
                        "employee_contribution_total": "Employee Contribution",
                    },
                    column_config={
                        "Total Sales": st.column_config.NumberColumn(format="Rs %.2f"),
                        "Employee Contribution": st.column_config.NumberColumn(format="Rs %.2f"),
                    },
                )

    with revenue:
        section_header("Revenue Analysis")
        left, right = st.columns(2)
        with left:
            st.markdown("##### Revenue by department")
            if department_revenue.empty:
                empty_state("Department revenue will appear after completed sales.")
            else:
                st.bar_chart(department_revenue.set_index("department")["revenue"], height=280)
                styled_dataframe(
                    department_revenue,
                    {
                        "department": "Department",
                        "revenue": "Revenue",
                        "units_sold": "Units Sold",
                    },
                    column_config={
                        "Revenue": st.column_config.NumberColumn(format="Rs %.2f"),
                        "Units Sold": st.column_config.NumberColumn(format="%d"),
                    },
                )
        with right:
            st.markdown("##### Monthly recorded revenue")
            monthly_recorded = frame(db.monthly_revenue())
            if monthly_recorded.empty:
                empty_state("Monthly revenue will appear after completed sales.")
            else:
                st.bar_chart(monthly_recorded.set_index("month")["revenue"], height=280)
                styled_dataframe(
                    monthly_recorded,
                    {
                        "month": "Month",
                        "revenue": "Revenue",
                        "transactions": "Transactions",
                    },
                    column_config={
                        "Revenue": st.column_config.NumberColumn(format="Rs %.2f"),
                        "Transactions": st.column_config.NumberColumn(format="%d"),
                    },
                )

    with performance:
        section_header("Product Performance")
        st.markdown("##### Revenue by product")
        if report.empty or report["revenue"].sum() == 0:
            empty_state("Product revenue will appear after completed sales.")
        else:
            st.bar_chart(report.set_index("name")["revenue"], height=280)
            styled_dataframe(
                report,
                {
                    "product_id": "Product ID",
                    "name": "Product",
                    "sale_lines": "Sale Lines",
                    "units_sold": "Units Sold",
                    "revenue": "Revenue",
                },
                column_config={
                    "Sale Lines": st.column_config.NumberColumn(format="%d"),
                    "Units Sold": st.column_config.NumberColumn(format="%d"),
                    "Revenue": st.column_config.NumberColumn(format="Rs %.2f"),
                },
            )

        st.markdown("")
        st.markdown("##### Top products by quantity")
        if top_products.empty:
            empty_state("Top products will appear after completed sales.")
        else:
            styled_dataframe(
                top_products,
                {
                    "product_id": "Product ID",
                    "name": "Product",
                    "department": "Department",
                    "units_sold": "Units Sold",
                    "revenue": "Revenue",
                },
                column_config={
                    "Units Sold": st.column_config.NumberColumn(format="%d"),
                    "Revenue": st.column_config.NumberColumn(format="Rs %.2f"),
                },
            )

    with inventory:
        section_header("Inventory Analytics")
        left, right = st.columns(2)
        with left:
            st.markdown("##### Low-stock products")
            if low_stock.empty:
                empty_state("No low-stock products found.")
            else:
                styled_dataframe(
                    low_stock,
                    {
                        "product_id": "Product ID",
                        "department": "Department",
                        "name": "Product",
                        "quantity_available": "Available",
                    },
                    column_config={"Available": st.column_config.NumberColumn(format="%d")},
                )
        with right:
            st.markdown("##### Inventory value by department")
            department_stock = frame(db.inventory_by_department())
            if department_stock.empty:
                empty_state("No inventory value data is available.")
            else:
                st.bar_chart(department_stock.set_index("department")["inventory_value"], height=280)

        st.markdown("")
        st.markdown("##### Inventory turnover from source history")
        if turnover.empty:
            empty_state("No turnover data is available.")
        else:
            styled_dataframe(
                turnover,
                {
                    "product_id": "Product ID",
                    "name": "Product",
                    "department": "Department",
                    "initial_quantity": "Initial Qty",
                    "quantity_sold": "Qty Sold",
                    "turnover_rate": "Turnover Rate",
                },
                column_config={
                    "Initial Qty": st.column_config.NumberColumn(format="%d"),
                    "Qty Sold": st.column_config.NumberColumn(format="%d"),
                    "Turnover Rate": st.column_config.NumberColumn(format="%.3f"),
                },
            )


def _streamlit_secrets():
    try:
        return st.secrets
    except Exception:
        return None


def show_employees(db):
    st.title("Employee Details")
    if st.session_state.get("employee_details_authenticated"):
        st.caption("Authorized employee records loaded from SQLite.")
        employees = employee_records_for_display(db, authenticated=True)
        table = frame(employees).rename(
            columns={
                "employee_id": "Employee ID",
                "name": "Name",
                "job_title": "Job",
                "address": "Address",
                "phone": "Phone Number",
                "monthly_salary": "Monthly Salary",
                "gender": "Gender",
            }
        )
        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Monthly Salary": st.column_config.NumberColumn(format="Rs %.2f"),
            },
        )
        return

    st.write("Enter password to view employee information.")
    with st.form("employee_details_auth"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("View Employee Details", type="primary")
    if submitted:
        if employee_details_password_is_valid(password, _streamlit_secrets()):
            st.session_state["employee_details_authenticated"] = True
            st.rerun()
        else:
            st.error("Wrong Password! ACCESS DENIED!")


def show_etl_monitoring(db):
    page_header(
        "ETL & Data Quality",
        "Monitor source ingestion, validation, loading, and pipeline health.",
        kicker="Data Engineering",
    )
    latest = db.latest_etl_run()
    if latest is None:
        empty_state("Run the ETL pipeline to populate source data.")
        st.caption("Use `python etl.py` to ingest the CSV source files.")
        return

    status = latest["status"]
    status_class = {
        "SUCCESS": "status-success",
        "FAILED": "status-failed",
        "RUNNING": "status-running",
    }.get(status, "status-running")
    render_kpi_row(
        [
            ("Last Run Status", status),
            ("Records Extracted", integer(latest["records_extracted"])),
            ("Records Loaded", integer(latest["records_loaded"])),
            ("Records Rejected", integer(latest["records_rejected"])),
        ]
    )
    st.markdown(
        f'<span class="status-pill {status_class}">{status}</span>',
        unsafe_allow_html=True,
    )

    duration = "—"
    if latest["completed_at"]:
        duration = str(
            datetime.fromisoformat(latest["completed_at"]) - datetime.fromisoformat(latest["started_at"])
        )

    st.markdown("")
    section_header("Latest Run")
    detail_cols = st.columns(4)
    detail_cols[0].markdown(f"**Run ID**  \n#{latest['run_id']}")
    detail_cols[1].markdown(f"**Started**  \n{latest['started_at']}")
    detail_cols[2].markdown(f"**Completed**  \n{latest['completed_at'] or '—'}")
    detail_cols[3].markdown(f"**Duration**  \n{duration}")
    if latest["error_message"]:
        st.error(latest["error_message"])
    elif status == "SUCCESS":
        st.success("The latest ETL run completed successfully.")
    elif status == "FAILED":
        st.error("The latest ETL run failed.")
    else:
        st.info("An ETL run is currently in progress.")

    st.markdown("")
    section_header("Recent Runs", "Pipeline execution history from SQLite monitoring tables.")
    history = frame(db.etl_run_history())
    if history.empty:
        empty_state("No ETL run history is available.")
    else:
        styled_dataframe(
            history,
            {
                "run_id": "Run ID",
                "started_at": "Started",
                "completed_at": "Completed",
                "status": "Status",
                "records_extracted": "Extracted",
                "records_loaded": "Loaded",
                "records_rejected": "Rejected",
                "error_message": "Error",
            },
            column_config={
                "Extracted": st.column_config.NumberColumn(format="%d"),
                "Loaded": st.column_config.NumberColumn(format="%d"),
                "Rejected": st.column_config.NumberColumn(format="%d"),
            },
        )

    st.markdown("")
    section_header("Data Quality", "Rejected source rows captured during validation.")
    rejections = frame(db.etl_rejection_summary())
    if rejections.empty:
        st.success("No rejected source records have been logged.")
    else:
        styled_dataframe(
            rejections,
            {
                "run_id": "Run ID",
                "dataset": "Dataset",
                "row_number": "Row",
                "reason": "Reason",
                "record_data": "Record",
            },
        )


def main():
    st.set_page_config(
        page_title="Sunshine Mart",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_theme()
    db = get_database()
    if message := st.session_state.pop("database_message", None):
        st.success(message)
    page = render_sidebar()
    {
        "Dashboard": show_dashboard,
        "Inventory": show_inventory,
        "Billing": show_billing,
        "Sales & Reports": show_sales_reports,
        "Employee Details": show_employees,
        "ETL & Data Quality": show_etl_monitoring,
    }[page](db)


if __name__ == "__main__":
    main()
