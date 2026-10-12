from dataclasses import dataclass

from sqlalchemy.exc import OperationalError


LOCK_TIMEOUT_SQLSTATE = "55P03"
STATEMENT_TIMEOUT_SQLSTATE = "57014"


@dataclass(frozen=True)
class DatabaseTimeout:
    timeout_type: str
    exception_type: str
    sqlstate: str | None


def _unwrap_exception(exception: BaseException) -> BaseException:
    while isinstance(exception, BaseExceptionGroup) and len(exception.exceptions) == 1:
        exception = exception.exceptions[0]
    return exception


def classify_database_timeout(exception: BaseException) -> DatabaseTimeout | None:
    """Classify PostgreSQL timeouts without parsing exception messages."""
    exception = _unwrap_exception(exception)
    original = getattr(exception, "orig", exception)
    sqlstate = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)

    if sqlstate == LOCK_TIMEOUT_SQLSTATE:
        timeout_type = "lock"
    elif sqlstate == STATEMENT_TIMEOUT_SQLSTATE:
        timeout_type = "statement"
    elif isinstance(exception, OperationalError) and sqlstate is None:
        timeout_type = "connect"
    else:
        return None

    return DatabaseTimeout(
        timeout_type=timeout_type,
        exception_type=type(original).__name__,
        sqlstate=sqlstate,
    )
