"""SQLite persistence and CSV seed-data import for Sunshine Mart."""

from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = PROJECT_DIR / "sunshine_mart.db"


class InventoryDatabase:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self, seed_directory: str | Path = PROJECT_DIR, seed_data=True) -> None:
        """Create tables and import supplied CSV data when tables are empty."""
        seed_directory = Path(seed_directory)
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    product_id INTEGER PRIMARY KEY,
                    department TEXT NOT NULL,
                    name TEXT NOT NULL,
                    unit_cost REAL NOT NULL CHECK (unit_cost >= 0),
                    initial_quantity INTEGER NOT NULL DEFAULT 0 CHECK (initial_quantity >= 0),
                    quantity_sold INTEGER NOT NULL DEFAULT 0 CHECK (quantity_sold >= 0),
                    quantity_available INTEGER NOT NULL CHECK (quantity_available >= 0),
                    UNIQUE (department, name)
                );
                CREATE TABLE IF NOT EXISTS employees (
                    employee_id TEXT PRIMARY KEY, name TEXT NOT NULL, job_title TEXT NOT NULL,
                    address TEXT NOT NULL, phone TEXT NOT NULL UNIQUE,
                    monthly_salary REAL NOT NULL CHECK (monthly_salary >= 0), gender TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sales (
                    sale_id INTEGER PRIMARY KEY AUTOINCREMENT, sold_at TEXT NOT NULL,
                    customer_email TEXT, subtotal REAL NOT NULL CHECK (subtotal >= 0),
                    vat REAL NOT NULL CHECK (vat >= 0), total REAL NOT NULL CHECK (total >= 0)
                );
                CREATE TABLE IF NOT EXISTS sale_items (
                    sale_item_id INTEGER PRIMARY KEY AUTOINCREMENT, sale_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL, quantity INTEGER NOT NULL CHECK (quantity > 0),
                    unit_price REAL NOT NULL CHECK (unit_price >= 0), line_total REAL NOT NULL CHECK (line_total >= 0),
                    FOREIGN KEY (sale_id) REFERENCES sales(sale_id) ON DELETE RESTRICT,
                    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE RESTRICT
                );
                CREATE TABLE IF NOT EXISTS monthly_sales (
                    month_name TEXT PRIMARY KEY, display_order INTEGER NOT NULL UNIQUE CHECK (display_order > 0),
                    total REAL NOT NULL CHECK (total >= 0)
                );
                CREATE TABLE IF NOT EXISTS monthly_employee_sales (
                    month_name TEXT NOT NULL, employee_name TEXT NOT NULL, amount REAL NOT NULL CHECK (amount >= 0),
                    PRIMARY KEY (month_name, employee_name),
                    FOREIGN KEY (month_name) REFERENCES monthly_sales(month_name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS etl_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
                    records_extracted INTEGER NOT NULL DEFAULT 0 CHECK (records_extracted >= 0),
                    records_loaded INTEGER NOT NULL DEFAULT 0 CHECK (records_loaded >= 0),
                    records_rejected INTEGER NOT NULL DEFAULT 0 CHECK (records_rejected >= 0),
                    error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS etl_rejections (
                    rejection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    dataset TEXT NOT NULL,
                    row_number INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    record_data TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES etl_runs(run_id) ON DELETE CASCADE
                );
                """
            )
            if seed_data and self._count(connection, "products") == 0:
                self._import_products(connection, seed_directory / "inventory.csv")
            if seed_data and self._count(connection, "employees") == 0:
                self._import_employees(connection, seed_directory / "empdet.csv")
            if seed_data and self._count(connection, "monthly_sales") == 0:
                self._import_monthly_sales(connection, seed_directory / "sales.csv")

    @staticmethod
    def _count(connection: sqlite3.Connection, table: str) -> int:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    @staticmethod
    def _data_rows(csv_path: Path) -> Iterable[dict[str, str]]:
        with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
            rows = list(csv.reader(csv_file))
        header_index = next(i for i, row in enumerate(rows) if row and ",".join(row).startswith(("Itemno", "EID", "Month_Name")))
        headers = [header.strip() for header in rows[header_index]]
        for row in rows[header_index + 1 :]:
            if row:
                yield dict(zip(headers, (value.strip() for value in row)))

    def _import_products(self, connection, csv_path):
        connection.executemany(
            "INSERT INTO products (product_id, department, name, unit_cost, initial_quantity, quantity_sold, quantity_available) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(int(r["Itemno"]), r["Department"], r["item_name"], float(r["Cost(in rupees)"]), int(r["Quantity initially ordered"]), int(r["Quantity sold (in a year)"]), int(r["Quantity Available"])) for r in self._data_rows(csv_path)],
        )

    def _import_employees(self, connection, csv_path):
        connection.executemany(
            "INSERT INTO employees (employee_id, name, job_title, address, phone, monthly_salary, gender) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(r["EID"], r["ENAME"], r["JOB"], r["ADDRESS"], r["Phone Number"], float(r["Salary (monthly)"]), r["Gender"]) for r in self._data_rows(csv_path)],
        )

    def _import_monthly_sales(self, connection, csv_path):
        for position, row in enumerate(self._data_rows(csv_path), start=1):
            month_name = row["Month_Name"]
            connection.execute("INSERT INTO monthly_sales (month_name, display_order, total) VALUES (?, ?, ?)", (month_name, position, float(row["Total"])))
            connection.executemany(
                "INSERT INTO monthly_employee_sales (month_name, employee_name, amount) VALUES (?, ?, ?)",
                [(month_name, person, float(amount)) for person, amount in row.items() if person not in {"Month_Name", "Total"}],
            )

    def products(self):
        with self.connection() as c:
            return c.execute("SELECT product_id, department, name, unit_cost, initial_quantity, quantity_sold, quantity_available FROM products ORDER BY product_id").fetchall()

    def add_product(self, product_id, department, name, unit_cost, quantity_available):
        if product_id <= 0 or not department.strip() or not name.strip() or unit_cost < 0 or quantity_available < 0:
            raise ValueError("Product ID, department, name, cost, and quantity must be valid non-negative values.")
        with self.connection() as c:
            c.execute("INSERT INTO products (product_id, department, name, unit_cost, initial_quantity, quantity_sold, quantity_available) VALUES (?, ?, ?, ?, ?, 0, ?)", (product_id, department.strip(), name.strip(), unit_cost, quantity_available, quantity_available))

    def delete_product(self, product_id):
        with self.connection() as c:
            if c.execute("DELETE FROM products WHERE product_id = ?", (product_id,)).rowcount == 0:
                raise ValueError(f"Product {product_id} does not exist.")

    def update_inventory(self, product_id, quantity_available):
        """Set the available stock for a product after validating the input."""
        if product_id <= 0 or quantity_available < 0:
            raise ValueError("Product ID must be positive and quantity cannot be negative.")
        with self.connection() as c:
            if c.execute(
                "UPDATE products SET quantity_available = ? WHERE product_id = ?",
                (quantity_available, product_id),
            ).rowcount == 0:
                raise ValueError(f"Product {product_id} does not exist.")

    def employees(self, public_only=False):
        columns = "employee_id, name, job_title" if public_only else "employee_id, name, job_title, address, phone, monthly_salary, gender"
        with self.connection() as c:
            return c.execute(f"SELECT {columns} FROM employees ORDER BY employee_id").fetchall()

    def record_sale(self, items, customer_email=None):
        quantities = {}
        for product_id, quantity in items:
            if product_id <= 0 or quantity <= 0:
                raise ValueError("Product IDs and quantities must be positive integers.")
            quantities[product_id] = quantities.get(product_id, 0) + quantity
        if not quantities:
            raise ValueError("A sale needs at least one item.")
        with self.connection() as c:
            products = []
            for product_id, quantity in quantities.items():
                product = c.execute("SELECT product_id, name, unit_cost, quantity_available FROM products WHERE product_id = ?", (product_id,)).fetchone()
                if product is None:
                    raise ValueError(f"Product {product_id} does not exist.")
                if quantity > product["quantity_available"]:
                    raise ValueError(f"Only {product['quantity_available']} units of {product['name']} are available.")
                products.append(product)
            subtotal = sum(p["unit_cost"] * quantities[p["product_id"]] for p in products)
            vat, total = round(subtotal * 0.05), subtotal + round(subtotal * 0.05)
            sale_id = c.execute("INSERT INTO sales (sold_at, customer_email, subtotal, vat, total) VALUES (?, ?, ?, ?, ?)", (datetime.now().isoformat(timespec="seconds"), customer_email or None, subtotal, vat, total)).lastrowid
            for product in products:
                quantity = quantities[product["product_id"]]
                c.execute("INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, line_total) VALUES (?, ?, ?, ?, ?)", (sale_id, product["product_id"], quantity, product["unit_cost"], product["unit_cost"] * quantity))
                c.execute("UPDATE products SET quantity_available = quantity_available - ?, quantity_sold = quantity_sold + ? WHERE product_id = ?", (quantity, quantity, product["product_id"]))
            return sale_id, products, subtotal, vat, total

    def monthly_totals(self):
        with self.connection() as c:
            # Preserve the historic CSV's supplied Total column for the existing chart.
            # The employee columns are still joined and aggregated for audit/reporting.
            return c.execute("SELECT ms.month_name, ms.display_order, MAX(ms.total) AS total, SUM(mes.amount) AS employee_contribution_total FROM monthly_sales AS ms JOIN monthly_employee_sales AS mes ON mes.month_name = ms.month_name GROUP BY ms.month_name, ms.display_order ORDER BY ms.display_order").fetchall()

    def inventory_chart_data(self):
        with self.connection() as c:
            return c.execute("SELECT name, initial_quantity, quantity_sold FROM products ORDER BY product_id").fetchall()

    def product_sales_report(self, limit=None):
        with self.connection() as c:
            query = "SELECT p.product_id, p.name, COUNT(si.sale_item_id) AS sale_lines, COALESCE(SUM(si.quantity), 0) AS units_sold, COALESCE(SUM(si.line_total), 0) AS revenue FROM products AS p LEFT JOIN sale_items AS si ON si.product_id = p.product_id GROUP BY p.product_id, p.name ORDER BY revenue DESC, p.product_id"
            return c.execute(f"{query} LIMIT ?" if limit else query, (limit,) if limit else ()).fetchall()

    def top_products_by_quantity(self, limit=5):
        with self.connection() as c:
            return c.execute(
                """
                SELECT p.product_id, p.name, p.department, SUM(si.quantity) AS units_sold,
                       SUM(si.line_total) AS revenue
                FROM sale_items AS si JOIN products AS p ON p.product_id = si.product_id
                GROUP BY p.product_id, p.name, p.department
                HAVING SUM(si.quantity) > 0
                ORDER BY units_sold DESC, revenue DESC, p.product_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def dashboard_metrics(self, low_stock_threshold=20):
        """Return current operational metrics calculated in SQLite."""
        with self.connection() as c:
            return c.execute(
                """
                SELECT
                    COUNT(*) AS total_products,
                    COALESCE(SUM(quantity_available), 0) AS total_inventory_quantity,
                    COALESCE(SUM(unit_cost * quantity_available), 0) AS total_inventory_value,
                    COALESCE(SUM(CASE WHEN quantity_available <= ? THEN 1 ELSE 0 END), 0) AS low_stock_products,
                    (SELECT COALESCE(SUM(total), 0) FROM sales) AS total_revenue,
                    (SELECT COUNT(*) FROM sales) AS transaction_count
                FROM products
                """,
                (low_stock_threshold,),
            ).fetchone()

    def inventory_by_department(self):
        with self.connection() as c:
            return c.execute(
                """
                SELECT department, SUM(quantity_available) AS quantity_available,
                       SUM(unit_cost * quantity_available) AS inventory_value
                FROM products
                GROUP BY department
                ORDER BY inventory_value DESC, department
                """
            ).fetchall()

    def sales_history(self):
        with self.connection() as c:
            return c.execute(
                """
                SELECT sale_id, sold_at, customer_email, subtotal, vat, total
                FROM sales
                ORDER BY sold_at DESC, sale_id DESC
                """
            ).fetchall()

    def start_etl_run(self):
        with self.connection() as c:
            return c.execute(
                "INSERT INTO etl_runs (started_at, status) VALUES (?, 'RUNNING')",
                (datetime.now().isoformat(timespec="seconds"),),
            ).lastrowid

    def finish_etl_run(self, run_id, status, records_extracted, records_loaded, records_rejected, error_message=None):
        with self.connection() as c:
            c.execute(
                """
                UPDATE etl_runs
                SET completed_at = ?, status = ?, records_extracted = ?, records_loaded = ?,
                    records_rejected = ?, error_message = ?
                WHERE run_id = ?
                """,
                (
                    datetime.now().isoformat(timespec="seconds"), status, records_extracted,
                    records_loaded, records_rejected, error_message, run_id,
                ),
            )

    def record_etl_rejections(self, run_id, rejections):
        if not rejections:
            return
        with self.connection() as c:
            c.executemany(
                "INSERT INTO etl_rejections (run_id, dataset, row_number, reason, record_data) VALUES (?, ?, ?, ?, ?)",
                [(run_id, item["dataset"], item["row_number"], item["reason"], item["record_data"]) for item in rejections],
            )

    def load_etl_records(self, records, replace=False):
        """Load validated, transformed source records in one database transaction."""
        with self.connection() as c:
            if replace:
                c.execute("DELETE FROM sale_items")
                c.execute("DELETE FROM sales")
                c.execute("DELETE FROM monthly_employee_sales")
                c.execute("DELETE FROM monthly_sales")
                c.execute("DELETE FROM employees")
                c.execute("DELETE FROM products")
            product_query = """
                INSERT INTO products (product_id, department, name, unit_cost, initial_quantity, quantity_sold, quantity_available)
                VALUES (:product_id, :department, :name, :unit_cost, :initial_quantity, :quantity_sold, :quantity_available)
            """
            if replace:
                product_query += """
                    ON CONFLICT(product_id) DO UPDATE SET
                        department = excluded.department, name = excluded.name, unit_cost = excluded.unit_cost,
                        initial_quantity = excluded.initial_quantity, quantity_sold = excluded.quantity_sold,
                        quantity_available = excluded.quantity_available
                """
            else:
                product_query += " ON CONFLICT(product_id) DO NOTHING"
            c.executemany(product_query, records["products"])
            c.executemany(
                """
                INSERT INTO employees (employee_id, name, job_title, address, phone, monthly_salary, gender)
                VALUES (:employee_id, :name, :job_title, :address, :phone, :monthly_salary, :gender)
                ON CONFLICT(employee_id) DO UPDATE SET
                    name = excluded.name, job_title = excluded.job_title, address = excluded.address,
                    phone = excluded.phone, monthly_salary = excluded.monthly_salary, gender = excluded.gender
                """,
                records["employees"],
            )
            for monthly_sale in records["monthly_sales"]:
                c.execute(
                    """
                    INSERT INTO monthly_sales (month_name, display_order, total) VALUES (?, ?, ?)
                    ON CONFLICT(month_name) DO UPDATE SET display_order = excluded.display_order, total = excluded.total
                    """,
                    (monthly_sale["month_name"], monthly_sale["display_order"], monthly_sale["total"]),
                )
                c.execute("DELETE FROM monthly_employee_sales WHERE month_name = ?", (monthly_sale["month_name"],))
                c.executemany(
                    "INSERT INTO monthly_employee_sales (month_name, employee_name, amount) VALUES (?, ?, ?)",
                    [(monthly_sale["month_name"], item["employee_name"], item["amount"]) for item in monthly_sale["employee_sales"]],
                )

    def latest_etl_run(self):
        with self.connection() as c:
            return c.execute("SELECT * FROM etl_runs ORDER BY run_id DESC LIMIT 1").fetchone()

    def etl_run_history(self, limit=10):
        with self.connection() as c:
            return c.execute("SELECT * FROM etl_runs ORDER BY run_id DESC LIMIT ?", (limit,)).fetchall()

    def etl_rejection_summary(self, limit=20):
        with self.connection() as c:
            return c.execute(
                """
                SELECT r.run_id, r.dataset, r.row_number, r.reason, r.record_data
                FROM etl_rejections AS r JOIN etl_runs AS e ON e.run_id = r.run_id
                ORDER BY r.rejection_id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def revenue_by_department(self):
        with self.connection() as c:
            return c.execute(
                """
                SELECT p.department, SUM(si.line_total) AS revenue, SUM(si.quantity) AS units_sold
                FROM sale_items AS si JOIN products AS p ON p.product_id = si.product_id
                GROUP BY p.department ORDER BY revenue DESC, p.department
                """
            ).fetchall()

    def monthly_revenue(self):
        with self.connection() as c:
            return c.execute(
                """
                SELECT substr(sold_at, 1, 7) AS month, SUM(total) AS revenue, COUNT(*) AS transactions
                FROM sales GROUP BY substr(sold_at, 1, 7) ORDER BY month
                """
            ).fetchall()

    def transaction_analytics(self):
        with self.connection() as c:
            return c.execute(
                "SELECT COUNT(*) AS transaction_count, COALESCE(AVG(total), 0) AS average_transaction_value FROM sales"
            ).fetchone()

    def low_stock_products(self, threshold=20):
        with self.connection() as c:
            return c.execute(
                "SELECT product_id, department, name, quantity_available FROM products WHERE quantity_available <= ? ORDER BY quantity_available, product_id",
                (threshold,),
            ).fetchall()

    def inventory_turnover_report(self):
        with self.connection() as c:
            return c.execute(
                """
                SELECT product_id, name, department, initial_quantity, quantity_sold,
                    ROUND(CAST(quantity_sold AS REAL) / NULLIF(initial_quantity, 0), 3) AS turnover_rate
                FROM products ORDER BY turnover_rate DESC, product_id
                """
            ).fetchall()


def reset_database(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    if path.exists():
        path.unlink()
    InventoryDatabase(path).initialize()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Create and seed the Sunshine Mart SQLite database.")
    parser.add_argument("--reset", action="store_true", help="Replace the existing database with a fresh seeded database.")
    if parser.parse_args().reset:
        reset_database()
    else:
        InventoryDatabase().initialize()
    print(f"Database ready: {DEFAULT_DB_PATH}")
