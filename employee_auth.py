"""Shared authentication for the password-protected employee-details view."""

from __future__ import annotations

import os
import secrets

PASSWORD_ENV_VAR = "EMPLOYEE_DETAILS_PASSWORD"


def configured_employee_details_password(secrets_mapping=None) -> str | None:
    """Return the configured password from the environment or Streamlit secrets."""
    configured = os.environ.get(PASSWORD_ENV_VAR)
    if configured:
        return configured
    if secrets_mapping is None:
        return None
    try:
        configured = secrets_mapping.get(PASSWORD_ENV_VAR)
    except Exception:
        return None
    if configured is None or str(configured) == "":
        return None
    return str(configured)


def employee_details_password_is_valid(submitted_password: str, secrets_mapping=None) -> bool:
    """Return True only when a password is configured and the submitted value matches."""
    expected = configured_employee_details_password(secrets_mapping)
    if not expected or submitted_password is None:
        return False
    submitted = str(submitted_password)
    try:
        return secrets.compare_digest(submitted, expected)
    except (TypeError, ValueError):
        return False


def employee_records_for_display(database, authenticated: bool):
    """Load full employee rows from SQLite only after authentication succeeds."""
    if not authenticated:
        return None
    return database.employees()
