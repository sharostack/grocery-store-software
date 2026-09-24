# Sunshine Mart Inventory & Billing System

A compact Data Engineering portfolio project combining a Python operational application with a visible CSV-to-SQLite ETL pipeline, SQL analytics, and a Streamlit dashboard.

## Architecture

```text
CSV Source Data → ETL / Validation → SQLite → SQL Analytics → Streamlit

inventory.csv / empdet.csv / sales.csv
                 ↓
      Python: extract → validate → transform → load
                 ↓
      SQLite operational and ETL-monitoring tables
                 ↓
        Reusable analytical SQL queries
                 ↓
     Streamlit dashboard and reporting pages
```

The original command-line interface is retained. Streamlit is an alternative frontend; both use the same `InventoryDatabase` data-access layer.

## Data model

| Layer | Tables | Purpose |
| --- | --- | --- |
| Operational (OLTP) | `products`, `employees`, `sales`, `sale_items` | Inventory CRUD and completed billing transactions. |
| Historical source analytics | `monthly_sales`, `monthly_employee_sales` | Aggregate monthly source data used by charts. |
| Pipeline monitoring | `etl_runs`, `etl_rejections` | ETL status, record counts, errors, and rejected source rows. |

Foreign keys, primary keys, unique constraints, `NOT NULL`, and non-negative `CHECK` constraints protect data quality. A separate star schema is intentionally not added: `sales.csv` is monthly aggregate data, not transaction-level product sales tied to real employee IDs, so a fact/dimension model would duplicate data and misrepresent its grain.

## ETL pipeline

[`etl.py`](etl.py) exposes `extract()`, `validate()`, `transform()`, `load()`, and `run_pipeline()`.

- Extract reads the actual CSV headers and skips source title rows.
- Validation separates accepted and rejected rows. It checks product IDs, names, costs, quantities and quantity consistency; employee IDs, names and salaries; and sales months, duplicates, and numeric values.
- Transformation trims values and converts numeric strings to typed database records.
- Load uses the SQLite data-access layer transactionally. Each run logs `RUNNING`, `SUCCESS`, or `FAILED` in `etl_runs` and stores rejection reasons in `etl_rejections`.

`python etl.py` performs a full refresh for a fresh demo database, replacing source-derived and transactional sales data. `python etl.py --incremental` is a non-destructive upsert for employees and historical monthly records; existing products are not overwritten because available stock may have changed through billing. The CSV sources have no timestamp, version, or reliable watermark, so true changed-record detection is not claimed or implemented.

## SQL analytics

Reusable database methods provide revenue and units by department, monthly recorded revenue, top products by revenue and quantity, transaction count and average value, inventory value, low-stock products, department contribution, and source-history inventory turnover. They demonstrate `JOIN`, `GROUP BY`, `SUM`, `COUNT`, `AVG`, `ORDER BY`, `WHERE`, `HAVING`, `COALESCE`, and parameterized SQL.

## Setup and run

Python 3.10+ is recommended.

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Initialize database
python database.py

# Run ETL
python etl.py

# Run CLI
python code

# Run Streamlit
streamlit run streamlit_app.py

# Run tests
python -m unittest discover -s tests -v
```

The Streamlit app includes Dashboard, Inventory, Billing, Sales & Reports, Employee Details, and **ETL & Data Quality**. Employee Details is password-protected and shows the full employee records stored in SQLite after authentication.

Set `EMPLOYEE_DETAILS_PASSWORD` in the environment, or as a Streamlit secret of the same name, before viewing employee information. Do not commit that value.

To replace the local database with the legacy seed import only:

```bash
python database.py --reset
```

## Data Engineering concepts demonstrated

- Batch ETL from CSV into a relational database.
- Data validation, rejection capture, and data-quality summaries.
- Typed transformation and transactional SQL loading.
- Pipeline monitoring with status, timestamps, counts, errors, and rejected records.
- OLTP modeling plus SQL-based analytical reporting.
- A Streamlit layer that calls database methods rather than embedding raw SQL.
