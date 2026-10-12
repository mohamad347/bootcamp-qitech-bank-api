"""Helpers coesos e locais da rota R09."""

from .base import *


def _wait_for_blocked_request(connection, resource: str) -> None:
    blocker_pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
    deadline = monotonic() + 5
    while monotonic() < deadline:
        connection.execute(text("SELECT pg_stat_clear_snapshot()"))
        waiting = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_stat_activity AS activity
                WHERE activity.datname = current_database()
                  AND activity.wait_event_type = 'Lock'
                  AND :blocker_pid = ANY(pg_blocking_pids(activity.pid))
                """
            ),
            {"blocker_pid": blocker_pid},
        ).scalar_one()
        if waiting:
            return
        sleep(0.01)
    raise AssertionError(
        f"Nenhuma request aguardou o lock do backend {blocker_pid} em {resource}"
    )

__all__ = [name for name in globals() if not name.startswith("__")]
