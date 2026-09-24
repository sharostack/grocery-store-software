# Sunshine Mart Inventory & Billing System

A small Python command-line project for inventory management, employee viewing, billing, and sales charts. It was migrated from CSV-backed pandas dataframes to a SQLite relational database to demonstrate practical Python + SQL data handling.

## Architecture

**Previous:** Python script → pandas reads/writes `inventory.csv`; employee and monthly-chart data read from CSV files.

**Current:** Python CLI → Python's built-in `sqlite3` module → `sunshine_mart.db` → inventory, employee, billing, reporting, and chart queries.

SQLite was selected because this is a local, single-user student application: it is relational, uses real SQL, requires no server setup, and is included with Python.

## Database schema

| Table | Purpose |
| --- | --- |
| `products` | Inventory product ID, department, name, price, historical quantity metrics, and available stock. |
| `employees` | Employee details from `empdet.csv`. |
| `sales` | One completed bill: timestamp, optional customer email, subtotal, VAT, and total. |
| `sale_items` | Purchased products for each bill; references `sales` and `products`. |
| `monthly_sales` | Historic monthly totals used by the existing pie chart. |
| `monthly_employee_sales` | Historic per-employee monthly figures from `sales.csv`; references `monthly_sales`. |

`sale_items.sale_id → sales.sale_id`, `sale_items.product_id → products.product_id`, and `monthly_employee_sales.month_name → monthly_sales.month_name` are foreign keys. Primary keys, unique values where appropriate, `NOT NULL`, and non-negative `CHECK` constraints provide basic validation.

## CSV migration

The original CSV files are retained as seed data and are not edited or removed:

- `inventory.csv` imports into `products`.
- `empdet.csv` imports into `employees`; its report-title row is skipped.
- `sales.csv` imports into `monthly_sales` and `monthly_employee_sales`; its report-title row is skipped.

Completed bills are now persisted in `sales` and `sale_items`; the old program printed bills but did not save them.

## Run from a fresh clone

Python 3.10+ is recommended. Charts require matplotlib:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python3 database.py
python3 code
```

`database.py` creates tables and imports CSV seed data only when the related table is empty. To replace a local database with a fresh import:

```bash
python3 database.py --reset
```

Promotional email is disabled unless both environment variables are configured:

```bash
export SUNSHINE_MART_EMAIL='your-address@example.com'
export SUNSHINE_MART_EMAIL_PASSWORD='your-app-password'
```

## SQL demonstrated

- `SELECT` for inventory, employee, graph, and report retrieval.
- `INSERT` for products, imported data, bills, and bill line items.
- `UPDATE` to reduce available stock and increase sold quantity in the same transaction.
- `DELETE` for product removal when it has no referenced sale items.
- `JOIN`, `GROUP BY`, `SUM`, and `COUNT` in monthly-sales and product-sales reports.
- Primary keys, foreign keys, `UNIQUE`, `NOT NULL`, and `CHECK` constraints.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests verify initialization/import, product add/delete and duplicate-ID protection, bill and bill-line creation, inventory updates, JOIN/GROUP BY reporting, and stock-underflow protection.
