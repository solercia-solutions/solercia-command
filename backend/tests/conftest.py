"""Pytest configuration and shared fixtures.

Integration tests require a running Postgres DB configured via the environment
variable ``TEST_DATABASE_URL``. When the variable is absent the tests that need
DB access are automatically skipped.

Install test dependencies:
    pip install pytest pytest-asyncio httpx

Run all tests:
    cd backend && pytest tests/ -v
"""

import os

import pytest

# Mark all tests in the suite as async by default.
pytest_plugins = ("pytest_asyncio",)

# Skip DB-dependent tests gracefully when no test database is configured.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
skip_no_db = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL not set — skipping integration tests",
)
