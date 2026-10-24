"""Pytest configuration and shared test fixtures."""

import os
import tempfile
from pathlib import Path
import pytest

from src.db import init_db
from src.import_data import import_sales_data
from src.config import CSV_PRIMARY_PATH, CSV_FALLBACK_PATH

@pytest.fixture
def temp_db_path(tmp_path):
    """Provide an isolated temporary database path for testing."""
    db_file = tmp_path / "test_rsg_sales.db"
    init_db(db_file)
    return db_file

@pytest.fixture
def populated_db(temp_db_path):
    """Provide a populated test database containing the real CSV dataset."""
    csv_file = CSV_PRIMARY_PATH if CSV_PRIMARY_PATH.exists() else CSV_FALLBACK_PATH
    import_sales_data(csv_path=csv_file, db_path=temp_db_path)
    return temp_db_path
