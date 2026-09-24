"""Batch ETL pipeline for Sunshine Mart's supplied CSV source files.

The pipeline deliberately uses only Python's standard library and the existing
SQLite data-access layer: extract CSV rows, validate them, transform accepted
rows into typed records, then load them transactionally.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from database import InventoryDatabase, PROJECT_DIR


SOURCE_FILES = {
    "products": ("inventory.csv", "Itemno"),
    "employees": ("empdet.csv", "EID"),
    "monthly_sales": ("sales.csv", "Month_Name"),
}


def extract(source_directory=PROJECT_DIR):
    """Read the three source files and retain source row numbers for auditing."""
    extracted = {}
    for dataset, (filename, first_column) in SOURCE_FILES.items():
        path = Path(source_directory) / filename
        with path.open(newline="", encoding="utf-8-sig") as csv_file:
            rows = list(csv.reader(csv_file))
        header_index = next(
            index for index, row in enumerate(rows)
            if row and row[0].strip() == first_column
        )
        headers = [header.strip() for header in rows[header_index]]
        extracted[dataset] = [
            (row_number, dict(zip(headers, (value.strip() for value in row))))
            for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2)
            if row
        ]
    return extracted


def _as_int(record, field, errors, label=None):
    try:
        return int(record[field])
    except (KeyError, TypeError, ValueError):
        errors.append(f"invalid {label or field}")
        return None


def _as_float(record, field, errors, label=None):
    try:
        return float(record[field])
    except (KeyError, TypeError, ValueError):
        errors.append(f"invalid {label or field}")
        return None


def _rejection(dataset, row_number, record, errors):
    return {
        "dataset": dataset,
        "row_number": row_number,
        "reason": "; ".join(errors),
        "record_data": json.dumps(record, sort_keys=True),
    }


def validate(extracted):
    """Separate valid records from rejected records with explicit reasons."""
    valid = {dataset: [] for dataset in SOURCE_FILES}
    rejected = []

    seen_product_ids = set()
    for row_number, record in extracted["products"]:
        errors = []
        product_id = _as_int(record, "Itemno", errors, "product ID")
        cost = _as_float(record, "Cost(in rupees)", errors, "cost")
        initial = _as_int(record, "Quantity initially ordered", errors, "initial quantity")
        sold = _as_int(record, "Quantity sold (in a year)", errors, "quantity sold")
        available = _as_int(record, "Quantity Available", errors, "available quantity")
        if product_id is None or product_id <= 0:
            errors.append("missing or non-positive product ID")
        elif product_id in seen_product_ids:
            errors.append("duplicate product ID")
        else:
            seen_product_ids.add(product_id)
        if not record.get("item_name", "").strip():
            errors.append("missing product name")
        if not record.get("Department", "").strip():
            errors.append("missing department")
        if cost is not None and cost < 0:
            errors.append("negative cost")
        quantities = [initial, sold, available]
        if any(quantity is not None and quantity < 0 for quantity in quantities):
            errors.append("negative quantity")
        if all(quantity is not None for quantity in quantities) and sold + available > initial:
            errors.append("sold plus available quantity exceeds initial quantity")
        (rejected if errors else valid["products"]).append(
            _rejection("products", row_number, record, errors) if errors else (row_number, record)
        )

    seen_employee_ids = set()
    for row_number, record in extracted["employees"]:
        errors = []
        employee_id = record.get("EID", "").strip()
        salary = _as_float(record, "Salary (monthly)", errors, "monthly salary")
        if not employee_id:
            errors.append("missing employee ID")
        elif employee_id in seen_employee_ids:
            errors.append("duplicate employee ID")
        else:
            seen_employee_ids.add(employee_id)
        if not record.get("ENAME", "").strip():
            errors.append("missing employee name")
        if salary is not None and salary < 0:
            errors.append("negative monthly salary")
        (rejected if errors else valid["employees"]).append(
            _rejection("employees", row_number, record, errors) if errors else (row_number, record)
        )

    seen_months = set()
    for row_number, record in extracted["monthly_sales"]:
        errors = []
        month = record.get("Month_Name", "").strip()
        total = _as_float(record, "Total", errors, "monthly total")
        if not month:
            errors.append("missing month")
        elif month in seen_months:
            errors.append("duplicate month record")
        else:
            seen_months.add(month)
        if total is not None and total < 0:
            errors.append("negative monthly total")
        for column, value in record.items():
            if column not in {"Month_Name", "Total"}:
                amount = _as_float(record, column, errors, f"employee sales amount for {column}")
                if amount is not None and amount < 0:
                    errors.append(f"negative employee sales amount for {column}")
        (rejected if errors else valid["monthly_sales"]).append(
            _rejection("monthly_sales", row_number, record, errors) if errors else (row_number, record)
        )
    return valid, rejected


def transform(valid_records):
    """Convert accepted string records to database-ready, typed dictionaries."""
    products = [
        {
            "product_id": int(record["Itemno"]), "department": record["Department"],
            "name": record["item_name"], "unit_cost": float(record["Cost(in rupees)"]),
            "initial_quantity": int(record["Quantity initially ordered"]),
            "quantity_sold": int(record["Quantity sold (in a year)"]),
            "quantity_available": int(record["Quantity Available"]),
        }
        for _, record in valid_records["products"]
    ]
    employees = [
        {
            "employee_id": record["EID"], "name": record["ENAME"], "job_title": record["JOB"],
            "address": record["ADDRESS"], "phone": record["Phone Number"],
            "monthly_salary": float(record["Salary (monthly)"]), "gender": record["Gender"],
        }
        for _, record in valid_records["employees"]
    ]
    monthly_sales = []
    for display_order, (_, record) in enumerate(valid_records["monthly_sales"], start=1):
        monthly_sales.append(
            {
                "month_name": record["Month_Name"], "display_order": display_order,
                "total": float(record["Total"]),
                "employee_sales": [
                    {"employee_name": name, "amount": float(amount)}
                    for name, amount in record.items() if name not in {"Month_Name", "Total"}
                ],
            }
        )
    return {"products": products, "employees": employees, "monthly_sales": monthly_sales}


def load(database, records, rejections, full=True):
    """Persist ETL output through the existing SQLite data-access layer."""
    database.load_etl_records(records, replace=full)
    return sum(len(dataset_records) for dataset_records in records.values())


def run_pipeline(source_directory=PROJECT_DIR, db_path=None, full=True):
    """Run the complete extract, validate, transform, load workflow and log it."""
    database = InventoryDatabase(db_path) if db_path else InventoryDatabase()
    database.initialize(seed_data=False)
    run_id = database.start_etl_run()
    extracted_count = loaded_count = 0
    rejections = []
    try:
        extracted = extract(source_directory)
        extracted_count = sum(len(records) for records in extracted.values())
        valid, rejections = validate(extracted)
        transformed = transform(valid)
        loaded_count = load(database, transformed, rejections, full=full)
        database.record_etl_rejections(run_id, rejections)
        database.finish_etl_run(run_id, "SUCCESS", extracted_count, loaded_count, len(rejections))
    except Exception as error:
        database.record_etl_rejections(run_id, rejections)
        database.finish_etl_run(run_id, "FAILED", extracted_count, loaded_count, len(rejections), str(error))
        raise
    return database.latest_etl_run()


def main():
    parser = argparse.ArgumentParser(description="Run the Sunshine Mart CSV-to-SQLite ETL pipeline.")
    parser.add_argument("--incremental", action="store_true", help="Upsert source records without first clearing transactional tables.")
    args = parser.parse_args()
    result = run_pipeline(full=not args.incremental)
    print(
        f"ETL run {result['run_id']}: {result['status']} | extracted: {result['records_extracted']} | "
        f"loaded: {result['records_loaded']} | rejected: {result['records_rejected']}"
    )


if __name__ == "__main__":
    main()
