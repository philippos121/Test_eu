from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


def _sync_add_missing_columns(conn):
    """Add any columns defined in models but missing from the DB."""
    inspector = sa_inspect(conn)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name not in existing:
                col_type = col.type.compile(conn.dialect)
                default_clause = ""
                if col.server_default is not None:
                    default_clause = f" DEFAULT {col.server_default.arg.text}"
                conn.execute(text(
                    f'ALTER TABLE {table_name} ADD COLUMN "{col.name}" {col_type}{default_clause}'
                ))


def _sync_fix_null_defaults(conn):
    """Backfill NULL values for columns that have a server_default."""
    inspector = sa_inspect(conn)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        for col in table.columns:
            if col.server_default is not None:
                default_val = col.server_default.arg.text
                conn.execute(text(
                    f'UPDATE {table_name} SET "{col.name}" = {default_val} '
                    f'WHERE "{col.name}" IS NULL'
                ))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sync_add_missing_columns)
        await conn.run_sync(_sync_fix_null_defaults)
