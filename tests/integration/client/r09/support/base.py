"""Integração do lifecycle direto de CLIENT pela R09."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timezone
from os import environ
from threading import Barrier
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from tests.utils import DbUtils, INTERNAL_TOKEN, RandomGenerator
from tests.utils.mockserver import MockServer
from tests.utils.requisition import ClientRequisition
from tests.integration.client.r03.support import (
    analyze_client,
    create_pending_individual,
    expect_client_analysis,
    provider_request,
)

__all__ = [name for name in globals() if not name.startswith("__")]
