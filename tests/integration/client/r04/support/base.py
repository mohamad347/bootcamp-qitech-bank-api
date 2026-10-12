"""Integração da abertura de conta para um CLIENT ACTIVE."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from os import environ
from threading import Barrier
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from tests.utils import DbUtils, INTERNAL_TOKEN, RandomGenerator
from tests.utils.requisition import ClientRequisition


ACCOUNT_RESPONSE_FIELDS = {"account_key", "status", "balance_cents"}
INVALID_CLIENT_KEY_ERROR = {
    "title": "Bad Request",
    "description": "client_key must be a valid UUID",
    "translation": "Payload Inválido",
    "code": "QIT000001",
}
FORBIDDEN_ERROR = {
    "title": "Forbidden",
    "description": "Request must be internal",
    "translation": "Requisição precisa ser interna",
    "code": "QIT000002",
}
ACCOUNT_ALREADY_EXISTS_ERROR = {
    "title": "Client already has an account",
    "description": "The client already has an account.",
    "translation": "O cliente já possui uma conta.",
    "code": "ACC0002",
}
INTERNAL_ERROR = {
    "title": "Internal Error",
    "description": "An internal error has occurred and its being investigated.",
    "translation": "Um erro interno aconteceu e está sendo investigado.",
    "code": "QIT000500",
}

__all__ = [name for name in globals() if not name.startswith("__")]
