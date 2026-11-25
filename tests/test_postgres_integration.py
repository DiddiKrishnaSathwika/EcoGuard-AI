import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

import tests.conftest  # noqa: F401
from alembic import command
from alembic.config import Config
from api import database as db
import config as app_config


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
POSTGRES_TESTS_ENABLED = (
    os.getenv("ENABLE_DISPOSABLE_POSTGRES_TESTS") == "1"
    and bool(TEST_DATABASE_URL)
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_TESTS_ENABLED,
    reason=(
        "Set TEST_DATABASE_URL and ENABLE_DISPOSABLE_POSTGRES_TESTS=1 "
        "for a disposable PostgreSQL test database."
    ),
)


@pytest.fixture
def isolated_postgres_schema(monkeypatch):
    base_url = make_url(TEST_DATABASE_URL)
    if not base_url.database or "test" not in base_url.database.lower():
        pytest.fail("The disposable PostgreSQL test database name must include 'test'.")

    schema = f"ecoguard_test_{uuid4().hex}"
    admin_engine = db.create_engine_for_url(base_url)
    engine = None
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        scoped_url = base_url.set(
            query={**base_url.query, "options": f"-csearch_path={schema}"}
        )
        scoped_url_string = scoped_url.render_as_string(hide_password=False)
        monkeypatch.setattr(db, "DATABASE_URL", scoped_url_string)
        monkeypatch.setattr(app_config, "DATABASE_URL", scoped_url_string)
        alembic_config = Config("alembic.ini")
        command.upgrade(alembic_config, "head")
        engine = db.get_engine()
        yield
    finally:
        if engine is not None:
            engine.dispose()
        try:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            admin_engine.dispose()


def test_postgres_database_round_trips_records_and_relationships(
    isolated_postgres_schema,
):
    profile = db.create_profile(
        {"company": "Postgres Test Foods", "state": "Telangana"}
    )
    document = db.save_document(
        profile["id"],
        "records.pdf",
        1,
        "PostgreSQL evidence",
        None,
        {"facts": {"waste": "present"}},
    )
    assessment = db.save_assessment(
        profile["id"],
        {
            "profile": {"company": "Postgres Test Foods"},
            "overall": {"status": "REVIEW", "risk_level": "LOW"},
            "findings": [],
        },
    )

    assert db.get_document(document["id"], with_text=True)["text"] == "PostgreSQL evidence"
    assert db.get_assessment(assessment["id"])["result"]["assessment_id"] == assessment["id"]
    assert db.dashboard_stats()["assessments_total"] == 1
    assert db.delete_profile(profile["id"])
    assert db.get_document(document["id"])["profile_id"] is None
    assert db.get_assessment(assessment["id"])["profile_id"] is None
