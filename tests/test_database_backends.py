import sqlite3

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

import tests.conftest  # noqa: F401
from api import database as db
from scripts.migrate_sqlite_to_postgres import _open_source


@pytest.fixture
def sqlite_database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", None)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "isolated.sqlite")
    db.init_db()
    yield
    db.get_engine().dispose()


def test_sqlite_database_round_trips_records_and_relationships(sqlite_database):
    engine = db.get_engine()
    assert engine.dialect.name == "sqlite"

    profile = db.create_profile(
        {"company": "Test Foods", "state": "Telangana"}
    )
    updated = db.update_profile(
        profile["id"],
        {"company": "Updated Foods", "state": "Telangana"},
    )
    assert updated["company"] == "Updated Foods"

    document = db.save_document(
        profile["id"],
        "records.pdf",
        2,
        "Extracted evidence",
        None,
        {"facts": {"waste": "present"}},
    )
    assert document["chars"] == len("Extracted evidence")
    assert document["analysis"] == {"facts": {"waste": "present"}}
    assert db.get_document(document["id"], with_text=True)["text"] == "Extracted evidence"
    assert db.list_documents(profile["id"])[0]["id"] == document["id"]

    assessment = db.save_assessment(
        profile["id"],
        {
            "profile": {"company": "Updated Foods"},
            "overall": {"status": "REVIEW", "risk_level": "LOW"},
            "findings": [],
        },
    )
    assert assessment["result"]["assessment_id"] == assessment["id"]
    assert db.list_assessments()[0]["id"] == assessment["id"]
    assert db.dashboard_stats()["assessments_total"] == 1

    assert db.delete_profile(profile["id"])
    assert db.get_document(document["id"])["profile_id"] is None
    assert db.get_assessment(assessment["id"])["profile_id"] is None
    assert db.delete_document(document["id"])
    assert db.delete_assessment(assessment["id"])


def test_tenant_queries_isolate_records_and_legacy_rows(sqlite_database):
    profile_a = db.create_profile_for_user(
        {"company": "Tenant A", "state": "Telangana"},
        "https://issuer.example/",
        "user-a",
    )
    profile_b = db.create_profile_for_user(
        {"company": "Tenant B", "state": "Karnataka"},
        "https://issuer.example/",
        "user-b",
    )
    tenant_a = db.get_tenant_ids("https://issuer.example/", "user-a")
    tenant_b = db.get_tenant_ids("https://issuer.example/", "user-b")
    doc_a = db.save_document(
        profile_a["id"],
        "a.pdf",
        1,
        "tenant A evidence",
        None,
        {},
        tenant_ids=tenant_a,
    )
    assessment_a = db.save_assessment(
        profile_a["id"],
        {
            "profile": {"company": "Tenant A"},
            "overall": {"status": "REVIEW", "risk_level": "LOW"},
            "findings": [],
        },
        tenant_ids=tenant_a,
    )
    legacy = db.create_profile({"company": "Unassigned legacy record"})

    assert [profile["id"] for profile in db.list_profiles(tenant_ids=tenant_a)] == [
        profile_a["id"]
    ]
    assert db.get_profile(profile_a["id"], tenant_ids=tenant_b) is None
    assert db.get_document(doc_a["id"], tenant_ids=tenant_b) is None
    assert db.get_assessment(assessment_a["id"], tenant_ids=tenant_b) is None
    assert db.get_profile(legacy["id"], tenant_ids=tenant_a) is None
    assert db.delete_profile(profile_a["id"], tenant_ids=tenant_b) is False
    assert db.delete_document(doc_a["id"], tenant_ids=tenant_b) is False
    assert db.delete_assessment(assessment_a["id"], tenant_ids=tenant_b) is False
    assert db.dashboard_stats(tenant_ids=tenant_a)["assessments_total"] == 1
    assert db.dashboard_stats(tenant_ids=tenant_b)["assessments_total"] == 0


def test_sqlite_init_adds_nullable_tenant_column_without_rewriting_legacy_data(
    tmp_path, monkeypatch
):
    db.get_engine().dispose()
    legacy_path = tmp_path / "legacy.sqlite"
    monkeypatch.setattr(db, "DATABASE_URL", None)
    monkeypatch.setattr(db, "DB_PATH", legacy_path)
    with sqlite3.connect(legacy_path) as connection:
        connection.execute(
            "CREATE TABLE business_profiles ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO business_profiles(data, created_at, updated_at) "
            "VALUES (?, ?, ?)",
            ('{"company":"Legacy"}', "created", "updated"),
        )

    db.init_db()

    profile = db.get_profile(1)
    assert profile["company"] == "Legacy"
    with db.connect() as connection:
        tenant_id = connection.execute(
            select(db.business_profiles.c.tenant_id).where(
                db.business_profiles.c.id == 1
            )
        ).scalar_one()
    assert tenant_id is None


def test_assessment_rejects_documents_from_another_profile(sqlite_database):
    from api.services import ServiceError, run_and_store_assessment

    profile_a = db.create_profile_for_user(
        {"company": "Tenant A", "state": "Telangana"},
        "https://issuer.example/",
        "user-a",
    )
    profile_b = db.create_profile_for_user(
        {"company": "Tenant B", "state": "Karnataka"},
        "https://issuer.example/",
        "user-b",
    )
    doc_a = db.save_document(
        profile_a["id"], "a.pdf", 1, "evidence", None, {}
    )
    tenant_b = db.get_tenant_ids("https://issuer.example/", "user-b")

    with pytest.raises(ServiceError, match="Document not found for this business"):
        run_and_store_assessment(
            profile_b["id"],
            [doc_a["id"]],
            tenant_ids=tenant_b,
        )


def test_postgres_url_uses_psycopg_without_connecting():
    engine = db.create_engine_for_url(
        "postgresql://user:password@127.0.0.1:1/ecoguard_test"
    )
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_postgres_schema_requires_explicit_alembic_migration(monkeypatch):
    monkeypatch.setattr(
        db,
        "DATABASE_URL",
        "postgresql://user:password@127.0.0.1/ecoguard_test",
    )
    with pytest.raises(RuntimeError, match="Alembic"):
        db.init_db()


def test_postgres_connection_failure_does_not_fall_back_to_sqlite(
    tmp_path, monkeypatch
):
    sqlite_fallback = tmp_path / "must_not_be_created.sqlite"
    monkeypatch.setattr(
        db,
        "DATABASE_URL",
        "postgresql://test:test@127.0.0.1:1/ecoguard_test",
    )
    monkeypatch.setattr(db, "DB_PATH", sqlite_fallback)
    assert db.get_engine().dialect.name == "postgresql"

    with pytest.raises(SQLAlchemyError):
        with db.connect() as connection:
            connection.execute(text("SELECT 1"))

    assert not sqlite_fallback.exists()


def test_sqlite_migration_source_is_opened_read_only(tmp_path):
    source_path = tmp_path / "source.sqlite"
    with sqlite3.connect(source_path) as connection:
        connection.executescript(
            """
            CREATE TABLE business_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                filename TEXT NOT NULL,
                pages INTEGER DEFAULT 0,
                text TEXT,
                error TEXT,
                analysis TEXT,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES business_profiles(id)
                    ON DELETE SET NULL
            );
            CREATE TABLE assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                company TEXT,
                overall_status TEXT,
                risk_level TEXT,
                created_at TEXT NOT NULL,
                result TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES business_profiles(id)
                    ON DELETE SET NULL
            );
            """
        )

    source = _open_source(source_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            source.execute(
                "INSERT INTO business_profiles(data, created_at, updated_at) "
                "VALUES ('{}', 'now', 'now')"
            )
    finally:
        source.close()
