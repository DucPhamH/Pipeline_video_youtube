"""DB test riêng — set DATABASE_URL trước khi import app."""
import os
import tempfile
from pathlib import Path

_TEST_DB = Path(tempfile.gettempdir()) / "write_service_test.sqlite3"
if _TEST_DB.exists():
    _TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from main import app

    with TestClient(app) as c:
        yield c
