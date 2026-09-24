import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import InventoryDatabase, PROJECT_DIR


class DatabaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = InventoryDatabase(Path(self.temp_dir.name) / "test.db")
        self.db.initialize(PROJECT_DIR)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_seed_data_and_analytics_are_loaded(self):
        self.assertEqual(len(self.db.products()), 10)
        self.assertEqual(len(self.db.employees()), 10)
        totals = self.db.monthly_totals()
        self.assertEqual(len(totals), 12)
        self.assertEqual(totals[0]["month_name"], "Jan")
        self.assertEqual(totals[0]["total"], 684)

    def test_product_crud_and_constraints(self):
        self.db.add_product(99, "Test", "Test Product", 12.5, 8)
        self.assertEqual(next(row for row in self.db.products() if row["product_id"] == 99)["quantity_available"], 8)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_product(99, "Test", "Duplicate", 12.5, 8)
        self.db.delete_product(99)
        self.assertFalse(any(row["product_id"] == 99 for row in self.db.products()))

    def test_sale_creates_related_rows_and_updates_inventory(self):
        sale_id, _, subtotal, vat, total = self.db.record_sale([(1, 2), (2, 3)])
        self.assertEqual((subtotal, vat, total), (960.0, 48, 1008.0))
        with self.db.connection() as connection:
            sale_items = connection.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)).fetchall()
            self.assertEqual(len(sale_items), 2)
            self.assertEqual(connection.execute("SELECT quantity_available FROM products WHERE product_id = 1").fetchone()[0], 63)
            self.assertEqual(connection.execute("SELECT quantity_available FROM products WHERE product_id = 2").fetchone()[0], 187)
        self.assertEqual(self.db.product_sales_report()[0]["units_sold"], 3)

    def test_invalid_sale_does_not_reduce_stock(self):
        with self.assertRaises(ValueError):
            self.db.record_sale([(1, 66)])
        self.assertEqual(self.db.products()[0]["quantity_available"], 65)


if __name__ == "__main__":
    unittest.main()
