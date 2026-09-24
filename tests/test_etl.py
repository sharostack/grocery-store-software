import shutil
import tempfile
import unittest
from pathlib import Path

from database import InventoryDatabase, PROJECT_DIR
from etl import extract, run_pipeline, transform, validate


class EtlPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.db_path = self.workspace / "etl_test.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_extract_validate_and_transform_source_files(self):
        extracted = extract(PROJECT_DIR)
        self.assertEqual(sum(len(rows) for rows in extracted.values()), 32)
        valid, rejected = validate(extracted)
        self.assertEqual(len(rejected), 0)
        transformed = transform(valid)
        self.assertEqual(transformed["products"][0]["product_id"], 1)
        self.assertEqual(transformed["employees"][0]["employee_id"], "S1001")
        self.assertEqual(transformed["monthly_sales"][0]["month_name"], "Jan")

    def test_validation_rejects_invalid_inventory_record(self):
        extracted = extract(PROJECT_DIR)
        extracted["products"][0][1]["Cost(in rupees)"] = "-10"
        valid, rejected = validate(extracted)
        self.assertEqual(len(valid["products"]), 9)
        self.assertEqual(len(rejected), 1)
        self.assertIn("negative cost", rejected[0]["reason"])

    def test_full_pipeline_loads_records_and_logs_run(self):
        result = run_pipeline(PROJECT_DIR, self.db_path, full=True)
        database = InventoryDatabase(self.db_path)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["records_extracted"], 32)
        self.assertEqual(result["records_loaded"], 32)
        self.assertEqual(result["records_rejected"], 0)
        self.assertEqual(len(database.products()), 10)
        self.assertEqual(len(database.employees()), 10)
        self.assertEqual(len(database.monthly_totals()), 12)
        self.assertEqual(database.latest_etl_run()["run_id"], result["run_id"])

    def test_latest_etl_run_returns_none_then_latest_completed_run(self):
        database = InventoryDatabase(self.db_path)
        database.initialize(seed_data=False)
        self.assertIsNone(database.latest_etl_run())

        result = run_pipeline(PROJECT_DIR, self.db_path, full=True)
        latest = database.latest_etl_run()
        self.assertEqual(latest["run_id"], result["run_id"])
        self.assertEqual(latest["status"], "SUCCESS")
        self.assertEqual(latest["records_extracted"], 32)
        self.assertEqual(latest["records_loaded"], 32)
        self.assertEqual(latest["records_rejected"], 0)

    def test_pipeline_logs_rejected_records(self):
        source_dir = self.workspace / "source"
        source_dir.mkdir()
        for filename in ("inventory.csv", "empdet.csv", "sales.csv"):
            shutil.copy(PROJECT_DIR / filename, source_dir / filename)
        inventory_path = source_dir / "inventory.csv"
        inventory_path.write_text(inventory_path.read_text().replace("1,Skincare,Facewash,150", "1,Skincare,Facewash,-150"), encoding="utf-8")

        result = run_pipeline(source_dir, self.db_path, full=True)
        database = InventoryDatabase(self.db_path)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["records_rejected"], 1)
        self.assertEqual(len(database.products()), 9)
        rejection = database.etl_rejection_summary()[0]
        self.assertEqual(rejection["dataset"], "products")
        self.assertIn("negative cost", rejection["reason"])


if __name__ == "__main__":
    unittest.main()
