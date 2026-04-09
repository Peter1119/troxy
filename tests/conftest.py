"""Shared test fixtures."""

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a temporary SQLite database path."""
    return str(tmp_path / "test_flows.db")
