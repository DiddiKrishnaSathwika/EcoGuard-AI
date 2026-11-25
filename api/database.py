"""SQLite and PostgreSQL persistence for EcoGuard AI."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    case,
    create_engine,
    delete,
    event,
    func,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.pool import NullPool

from config import DATABASE_URL, DB_PATH


metadata = MetaData()

tenants = Table(
    "tenants",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    sqlite_autoincrement=True,
)

tenant_memberships = Table(
    "tenant_memberships",
    metadata,
    Column("tenant_id", Integer, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
    Column("issuer", Text, primary_key=True),
    Column("subject", Text, primary_key=True),
    Column("role", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)

business_profiles = Table(
    "business_profiles",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", Integer, ForeignKey("tenants.id", ondelete="CASCADE")),
    Column("data", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    sqlite_autoincrement=True,
)
business_profiles_tenant_index = Index(
    "ix_business_profiles_tenant_id",
    business_profiles.c.tenant_id,
)

documents = Table(
    "documents",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("profile_id", Integer, ForeignKey("business_profiles.id", ondelete="SET NULL")),
    Column("filename", Text, nullable=False),
    Column("pages", Integer, server_default=text("0")),
    Column("text", Text),
    Column("error", Text),
    Column("analysis", Text),
    Column("uploaded_at", Text, nullable=False),
    sqlite_autoincrement=True,
)

assessments = Table(
    "assessments",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("profile_id", Integer, ForeignKey("business_profiles.id", ondelete="SET NULL")),
    Column("company", Text),
    Column("overall_status", Text),
    Column("risk_level", Text),
    Column("created_at", Text, nullable=False),
    Column("result", Text, nullable=False),
    sqlite_autoincrement=True,
)

_engine: Engine | None = None
_engine_key: tuple[str, str] | None = None


def create_engine_for_url(database_url: str | URL) -> Engine:
    """Create a short-lived-connection engine for a PostgreSQL URL."""
    url = make_url(database_url)
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError(
            "DATABASE_URL must use PostgreSQL (postgresql:// or "
            "postgresql+psycopg://)."
        )
    return create_engine(
        url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 10},
    )


def get_engine() -> Engine:
    """Return the process-local engine, recreating it if configuration changes."""
    global _engine, _engine_key

    if DATABASE_URL:
        key = ("postgres", DATABASE_URL)
        if _engine is None or _engine_key != key:
            if _engine is not None:
                _engine.dispose()
            _engine = create_engine_for_url(DATABASE_URL)
            _engine_key = key
        return _engine

    key = ("sqlite", str(DB_PATH))
    if _engine is None or _engine_key != key:
        if _engine is not None:
            _engine.dispose()
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            URL.create("sqlite", database=str(DB_PATH)),
            connect_args={"check_same_thread": False},
        )
        event.listen(_engine, "connect", _enable_sqlite_foreign_keys)
        _engine_key = key
    return _engine


def _enable_sqlite_foreign_keys(connection, _record):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    with get_engine().begin() as connection:
        yield connection


def init_db():
    """Initialize the local SQLite schema; PostgreSQL is managed by Alembic."""
    if DATABASE_URL:
        raise RuntimeError(
            "PostgreSQL schema is managed by Alembic; run "
            "`python -m alembic upgrade head` explicitly."
        )
    engine = get_engine()
    metadata.create_all(engine, checkfirst=True)
    columns = {column["name"] for column in inspect(engine).get_columns("business_profiles")}
    tenant_column_added = "tenant_id" not in columns
    if tenant_column_added:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE business_profiles ADD COLUMN "
                    "tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE"
                )
            )
        business_profiles_tenant_index.create(engine, checkfirst=True)


def _profile(row):
    if row is None:
        return None
    d = json.loads(row["data"])
    d.update(id=row["id"], created_at=row["created_at"], updated_at=row["updated_at"])
    return d


def create_profile(data, tenant_id=None):
    with connect() as c:
        result = c.execute(
            insert(business_profiles).values(
                tenant_id=tenant_id,
                data=json.dumps(data),
                created_at=now(),
                updated_at=now(),
            )
        )
        pid = result.inserted_primary_key[0]
    return get_profile(pid)


def create_profile_for_user(data, issuer, subject):
    with connect() as c:
        created_at = now()
        tenant_result = c.execute(
            insert(tenants).values(name=data["company"], created_at=created_at)
        )
        tenant_id = tenant_result.inserted_primary_key[0]
        c.execute(
            insert(tenant_memberships).values(
                tenant_id=tenant_id,
                issuer=issuer,
                subject=subject,
                role="owner",
                created_at=created_at,
            )
        )
        profile_result = c.execute(
            insert(business_profiles).values(
                tenant_id=tenant_id,
                data=json.dumps(data),
                created_at=created_at,
                updated_at=created_at,
            )
        )
        profile_id = profile_result.inserted_primary_key[0]
    return get_profile(profile_id, tenant_ids=[tenant_id])


def get_tenant_ids(issuer, subject):
    with connect() as c:
        rows = c.execute(
            select(tenant_memberships.c.tenant_id).where(
                tenant_memberships.c.issuer == issuer,
                tenant_memberships.c.subject == subject,
            )
        )
        return list(rows.scalars())


def update_profile(pid, data, tenant_ids=None):
    statement = update(business_profiles).where(business_profiles.c.id == pid)
    if tenant_ids is not None:
        statement = statement.where(business_profiles.c.tenant_id.in_(tenant_ids))
    with connect() as c:
        c.execute(
            statement.values(data=json.dumps(data), updated_at=now())
        )
    return get_profile(pid, tenant_ids=tenant_ids)


def get_profile(pid, tenant_ids=None):
    statement = select(business_profiles).where(business_profiles.c.id == pid)
    if tenant_ids is not None:
        statement = statement.where(business_profiles.c.tenant_id.in_(tenant_ids))
    with connect() as c:
        row = c.execute(statement).mappings().first()
        return _profile(row)


def list_profiles(tenant_ids=None):
    statement = select(business_profiles).order_by(business_profiles.c.id.desc())
    if tenant_ids is not None:
        statement = statement.where(business_profiles.c.tenant_id.in_(tenant_ids))
    with connect() as c:
        rows = c.execute(statement).mappings()
        return [_profile(row) for row in rows]


def delete_profile(pid, tenant_ids=None):
    statement = delete(business_profiles).where(business_profiles.c.id == pid)
    if tenant_ids is not None:
        statement = statement.where(business_profiles.c.tenant_id.in_(tenant_ids))
    with connect() as c:
        result = c.execute(statement)
        return result.rowcount > 0


def _doc(row, with_text=False):
    if row is None:
        return None
    d = {"id": row["id"], "profile_id": row["profile_id"], "filename": row["filename"], "pages": row["pages"],
         "error": row["error"], "uploaded_at": row["uploaded_at"],
         "analysis": json.loads(row["analysis"]) if row["analysis"] else None,
         "chars": len(row["text"] or "")}
    if with_text:
        d["text"] = row["text"]
    return d


def save_document(profile_id, filename, pages, text, error, analysis, tenant_ids=None):
    with connect() as c:
        if profile_id is not None and tenant_ids is not None:
            visible_profile = c.execute(
                select(business_profiles.c.id).where(
                    business_profiles.c.id == profile_id,
                    business_profiles.c.tenant_id.in_(tenant_ids),
                )
            ).first()
            if visible_profile is None:
                return None
        result = c.execute(
            insert(documents).values(
                profile_id=profile_id,
                filename=filename,
                pages=pages,
                text=text,
                error=error,
                analysis=json.dumps(analysis) if analysis else None,
                uploaded_at=now(),
            )
        )
        did = result.inserted_primary_key[0]
    return get_document(did)


def get_document(did, with_text=False, tenant_ids=None):
    statement = select(documents).where(documents.c.id == did)
    if tenant_ids is not None:
        statement = statement.join(
            business_profiles,
            documents.c.profile_id == business_profiles.c.id,
        ).where(business_profiles.c.tenant_id.in_(tenant_ids))
    with connect() as c:
        row = c.execute(statement).mappings().first()
        return _doc(row, with_text)


def list_documents(profile_id=None, tenant_ids=None):
    statement = select(documents).order_by(documents.c.id.desc())
    if tenant_ids is not None:
        statement = statement.join(
            business_profiles,
            documents.c.profile_id == business_profiles.c.id,
        ).where(business_profiles.c.tenant_id.in_(tenant_ids))
    if profile_id is not None:
        statement = statement.where(documents.c.profile_id == profile_id)
    with connect() as c:
        rows = c.execute(statement).mappings().all()
        return [_doc(r) for r in rows]


def delete_document(did, tenant_ids=None):
    statement = delete(documents).where(documents.c.id == did)
    if tenant_ids is not None:
        visible_profile_ids = select(business_profiles.c.id).where(
            business_profiles.c.tenant_id.in_(tenant_ids)
        )
        statement = statement.where(documents.c.profile_id.in_(visible_profile_ids))
    with connect() as c:
        result = c.execute(statement)
        return result.rowcount > 0


def save_assessment(profile_id, result, tenant_ids=None):
    with connect() as c:
        if tenant_ids is not None:
            visible_profile = c.execute(
                select(business_profiles.c.id).where(
                    business_profiles.c.id == profile_id,
                    business_profiles.c.tenant_id.in_(tenant_ids),
                )
            ).first()
            if visible_profile is None:
                return None
        inserted = c.execute(
            insert(assessments).values(
                profile_id=profile_id,
                company=result["profile"].get("company"),
                overall_status=result["overall"]["status"],
                risk_level=result["overall"]["risk_level"],
                created_at=now(),
                result=json.dumps(result),
            )
        )
        aid = inserted.inserted_primary_key[0]
    return get_assessment(aid)


def _assessment(row, full=True):
    if row is None:
        return None
    d = {"id": row["id"], "profile_id": row["profile_id"], "company": row["company"],
         "overall_status": row["overall_status"], "risk_level": row["risk_level"], "created_at": row["created_at"]}
    if full:
        d["result"] = json.loads(row["result"])
        d["result"]["assessment_id"] = row["id"]
    return d


def get_assessment(aid, tenant_ids=None):
    statement = select(assessments).where(assessments.c.id == aid)
    if tenant_ids is not None:
        statement = statement.join(
            business_profiles,
            assessments.c.profile_id == business_profiles.c.id,
        ).where(business_profiles.c.tenant_id.in_(tenant_ids))
    with connect() as c:
        row = c.execute(statement).mappings().first()
        return _assessment(row)


def list_assessments(limit=100, tenant_ids=None):
    statement = select(assessments).order_by(assessments.c.id.desc()).limit(limit)
    if tenant_ids is not None:
        statement = statement.join(
            business_profiles,
            assessments.c.profile_id == business_profiles.c.id,
        ).where(business_profiles.c.tenant_id.in_(tenant_ids))
    with connect() as c:
        rows = c.execute(statement).mappings()
        return [_assessment(row, full=False) for row in rows]


def delete_assessment(aid, tenant_ids=None):
    statement = delete(assessments).where(assessments.c.id == aid)
    if tenant_ids is not None:
        visible_profile_ids = select(business_profiles.c.id).where(
            business_profiles.c.tenant_id.in_(tenant_ids)
        )
        statement = statement.where(assessments.c.profile_id.in_(visible_profile_ids))
    with connect() as c:
        result = c.execute(statement)
        return result.rowcount > 0


def dashboard_stats(tenant_ids=None):
    with connect() as c:
        docs_statement = select(
            func.count().label("n"),
            func.coalesce(func.sum(documents.c.pages), 0).label("p"),
            func.coalesce(
                func.sum(
                    case(
                        (documents.c.error.is_not(None), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("e"),
        ).select_from(documents)
        profiles_statement = select(func.count()).select_from(business_profiles)
        assessments_statement = select(func.count()).select_from(assessments)
        latest_statement = select(assessments).order_by(assessments.c.id.desc()).limit(1)
        if tenant_ids is not None:
            docs_statement = docs_statement.join(
                business_profiles,
                documents.c.profile_id == business_profiles.c.id,
            ).where(business_profiles.c.tenant_id.in_(tenant_ids))
            profiles_statement = profiles_statement.where(
                business_profiles.c.tenant_id.in_(tenant_ids)
            )
            assessments_statement = assessments_statement.join(
                business_profiles,
                assessments.c.profile_id == business_profiles.c.id,
            ).where(business_profiles.c.tenant_id.in_(tenant_ids))
            latest_statement = latest_statement.join(
                business_profiles,
                assessments.c.profile_id == business_profiles.c.id,
            ).where(business_profiles.c.tenant_id.in_(tenant_ids))
        docs = c.execute(docs_statement).mappings().one()
        n_prof = c.execute(profiles_statement).scalar_one()
        n_ass = c.execute(assessments_statement).scalar_one()
        latest = c.execute(latest_statement).mappings().first()
    return {
        "profiles": n_prof,
        "documents": {
            "total": docs["n"],
            "pages": docs["p"],
            "failed": docs["e"] or 0,
        },
        "assessments_total": n_ass,
        "latest": _assessment(latest) if latest else None,
        "recent": list_assessments(8, tenant_ids=tenant_ids),
    }
