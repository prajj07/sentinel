from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from sentinel_common.settings import get_database_settings

_engine_instrumented = False


@lru_cache
def get_engine() -> Engine:
    global _engine_instrumented
    settings = get_database_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    if not _engine_instrumented:
        try:
            from sentinel_observability.tracing import instrument_sqlalchemy

            instrument_sqlalchemy(engine)
            _engine_instrumented = True
        except ImportError:
            pass
    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
