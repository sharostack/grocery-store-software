import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from database import InventoryDatabase, PROJECT_DIR
from employee_auth import (
    PASSWORD_ENV_VAR,
    employee_details_password_is_valid,
    employee_records_for_display,
)

sys.modules.setdefault("pandas", MagicMock())
sys.modules.setdefault("streamlit", MagicMock())
from streamlit_app import show_employees  # noqa: E402


class EmployeeDetailsAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = InventoryDatabase(Path(self.temp_dir.name) / "test.db")
        self.db.initialize(PROJECT_DIR)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_employee_rows_exist_in_sqlite(self):
        with self.db.connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
            sample = connection.execute(
                "SELECT employee_id, name, job_title, address, phone, monthly_salary, gender FROM employees WHERE employee_id = ?",
                ("S1001",),
            ).fetchone()
        self.assertEqual(count, 10)
        self.assertEqual(sample["job_title"], "Sales")
        self.assertEqual(sample["address"], "JS road")
        self.assertEqual(sample["phone"], "6541515865")
        self.assertEqual(sample["monthly_salary"], 10000)
        self.assertEqual(sample["gender"], "M")

    def test_unauthenticated_state_does_not_expose_employee_details(self):
        with patch.object(self.db, "employees") as employees:
            self.assertIsNone(employee_records_for_display(self.db, authenticated=False))
            employees.assert_not_called()

    def test_correct_password_allows_access(self):
        with patch.dict(os.environ, {PASSWORD_ENV_VAR: "configured-test-password"}):
            self.assertTrue(employee_details_password_is_valid("configured-test-password"))
        rows = employee_records_for_display(self.db, authenticated=True)
        self.assertEqual(len(rows), 10)
        self.assertEqual(
            set(dict(rows[0])),
            {"employee_id", "name", "job_title", "address", "phone", "monthly_salary", "gender"},
        )

    def test_incorrect_password_does_not_reveal_employee_data(self):
        with patch.dict(os.environ, {PASSWORD_ENV_VAR: "configured-test-password"}):
            self.assertFalse(employee_details_password_is_valid("not-the-password"))
        with patch.object(self.db, "employees") as employees:
            self.assertIsNone(employee_records_for_display(self.db, authenticated=False))
            employees.assert_not_called()

    def test_unconfigured_password_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(employee_details_password_is_valid("anything"))

    def test_streamlit_secrets_are_accepted_when_env_is_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(
                employee_details_password_is_valid(
                    "secret-from-streamlit",
                    secrets_mapping={"EMPLOYEE_DETAILS_PASSWORD": "secret-from-streamlit"},
                )
            )

    def test_employee_details_come_from_inventory_database_not_csv(self):
        with patch.object(self.db, "employees", wraps=self.db.employees) as employees:
            with patch("database.csv.reader") as csv_reader:
                rows = employee_records_for_display(self.db, authenticated=True)
        employees.assert_called_once_with()
        csv_reader.assert_not_called()
        self.assertEqual(rows[0]["employee_id"], "S1001")

    def _fake_streamlit(self, *, password="guess", submitted=False, authenticated=False):
        class FakeStreamlit:
            def __init__(self):
                self.session_state = {}
                if authenticated:
                    self.session_state["employee_details_authenticated"] = True
                self.errors = []
                self.dataframes = []
                self.writes = []
                self.password = password
                self.submitted = submitted

            def title(self, *_args, **_kwargs):
                return None

            def write(self, message, *_args, **_kwargs):
                self.writes.append(message)

            def form(self, *_args, **_kwargs):
                return self

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def text_input(self, *_args, **_kwargs):
                return self.password

            def form_submit_button(self, *_args, **_kwargs):
                return self.submitted

            def error(self, message):
                self.errors.append(message)

            def dataframe(self, data, **_kwargs):
                self.dataframes.append(data)

            def rerun(self):
                return None

        return FakeStreamlit()

    def _patch_streamlit(self, fake):
        return patch.multiple(
            "streamlit_app.st",
            session_state=fake.session_state,
            title=fake.title,
            write=fake.write,
            form=fake.form,
            text_input=fake.text_input,
            form_submit_button=fake.form_submit_button,
            error=fake.error,
            dataframe=fake.dataframe,
            rerun=fake.rerun,
            secrets={},
        )

    def test_streamlit_page_does_not_load_employees_before_authentication(self):
        fake = self._fake_streamlit(submitted=False)
        with self._patch_streamlit(fake):
            with patch.object(self.db, "employees") as employees:
                show_employees(self.db)
                employees.assert_not_called()
        self.assertEqual(fake.dataframes, [])
        self.assertIn("Enter password to view employee information.", fake.writes)
        self.assertTrue(all("Public staff directory" not in str(item) for item in fake.writes))

    def test_streamlit_incorrect_password_does_not_reveal_employee_data(self):
        fake = self._fake_streamlit(password="wrong-password", submitted=True)
        with patch.dict(os.environ, {PASSWORD_ENV_VAR: "configured-test-password"}):
            with self._patch_streamlit(fake):
                with patch.object(self.db, "employees") as employees:
                    show_employees(self.db)
                    employees.assert_not_called()
        self.assertEqual(fake.dataframes, [])
        self.assertFalse(fake.session_state.get("employee_details_authenticated"))
        self.assertEqual(fake.errors, ["Wrong Password! ACCESS DENIED!"])

    def test_streamlit_correct_password_grants_authenticated_session(self):
        fake = self._fake_streamlit(password="configured-test-password", submitted=True)
        with patch.dict(os.environ, {PASSWORD_ENV_VAR: "configured-test-password"}):
            with self._patch_streamlit(fake):
                with patch.object(self.db, "employees") as employees:
                    show_employees(self.db)
                    employees.assert_not_called()
        self.assertTrue(fake.session_state.get("employee_details_authenticated"))
        self.assertEqual(fake.dataframes, [])

    def test_streamlit_authenticated_session_shows_full_employee_fields(self):
        class RenamedTable:
            def __init__(self):
                self.columns = None

            def rename(self, columns=None, **_kwargs):
                self.columns = set(columns.values()) if columns else set()
                return self

        renamed = RenamedTable()
        fake = self._fake_streamlit(authenticated=True)
        with self._patch_streamlit(fake):
            with patch.object(self.db, "employees", wraps=self.db.employees) as employees:
                with patch("streamlit_app.frame", return_value=renamed):
                    show_employees(self.db)
                employees.assert_called_once_with()
        self.assertEqual(len(fake.dataframes), 1)
        self.assertIs(fake.dataframes[0], renamed)
        self.assertEqual(
            renamed.columns,
            {
                "Employee ID",
                "Name",
                "Job",
                "Address",
                "Phone Number",
                "Monthly Salary",
                "Gender",
            },
        )


if __name__ == "__main__":
    unittest.main()
