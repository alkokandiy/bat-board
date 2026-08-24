import os
import tempfile

_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def headers(client):
    client.post("/api/auth/register", json={"username": "dayuser", "password": "pass1234"})
    r = client.post(
        "/api/auth/login",
        data={"username": "dayuser", "password": "pass1234"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}