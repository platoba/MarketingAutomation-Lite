"""Async SQLAlchemy engine & session — supports SQLite and PostgreSQL."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# SQLite needs connect_args for async; PostgreSQL uses pool_size
if settings.is_sqlite:
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=10,
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


@event.listens_for(Base, "init", propagate=True)
def _apply_defaults(target, args, kwargs):
    """Apply Column defaults at Python level right after __init__."""
    from sqlalchemy import inspect as sa_inspect

    try:
        mapper = sa_inspect(type(target))
    except Exception:
        return
    for col_attr in mapper.column_attrs:
        key = col_attr.key
        if key in kwargs:
            continue
        val = getattr(target, key, None)
        if val is not None:
            continue
        col = col_attr.columns[0]
        if col.default is None:
            continue
        arg = col.default.arg
        if callable(arg):
            try:
                setattr(target, key, arg())
            except TypeError:
                try:
                    setattr(target, key, arg(None))
                except Exception:
                    pass
        else:
            setattr(target, key, arg)


async def get_db():
    async with async_session() as session:
        yield session
