"""Pricing PF/PJ aplicado ao fluxo real de TRANSFER."""

from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine

from tests.integration.transaction.support import (
    create_account,
    read_transfer_state,
    send_transfer,
)


@pytest.mark.parametrize(
    ("source_type", "target_type", "expected_fee_cents"),
    [
        ("INDIVIDUAL", "INDIVIDUAL", 250),
        ("INDIVIDUAL", "COMPANY", 250),
        ("COMPANY", "INDIVIDUAL", 500),
        ("COMPANY", "COMPANY", 500),
    ],
)
def test_transfer_fee_depends_only_on_source_client_type(
    api_database_engine: Engine,
    source_type: str,
    target_type: str,
    expected_fee_cents: int,
) -> None:
    amount_cents = 50_000
    initial_source_balance = 100_000
    source_key = create_account(
        api_database_engine,
        client_type=source_type,
        balance_cents=initial_source_balance,
    )
    target_key = create_account(
        api_database_engine,
        client_type=target_type,
    )
    idempotency_key = uuid4()

    response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
        amount_cents,
    )
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    assert response.response_status == 201
    assert response.response_json["fee_cents"] == expected_fee_cents
    assert state["entries"][1]["direction"] == "DEBIT"
    assert state["entries"][1]["entry_type"] == "FEE"
    assert state["entries"][1]["amount_cents"] == expected_fee_cents
    assert state["source"]["balance_cents"] == (
        initial_source_balance - amount_cents - expected_fee_cents
    )
    assert state["target"]["balance_cents"] == amount_cents


@pytest.mark.parametrize(
    ("source_type", "amount_cents", "expected_fee_cents"),
    [
        ("INDIVIDUAL", 1_000, 50),
        ("INDIVIDUAL", 50_000, 250),
        ("INDIVIDUAL", 1_000_000, 1_000),
        ("INDIVIDUAL", 20_100, 101),
        ("COMPANY", 1_000, 100),
        ("COMPANY", 50_000, 500),
        ("COMPANY", 1_000_000, 1_500),
        ("COMPANY", 20_050, 201),
    ],
    ids=[
        "individual-floor",
        "individual-percentage",
        "individual-cap",
        "individual-half-up",
        "company-floor",
        "company-percentage",
        "company-cap",
        "company-half-up",
    ],
)
def test_transfer_persists_source_pricing_profile_fee(
    api_database_engine: Engine,
    source_type: str,
    amount_cents: int,
    expected_fee_cents: int,
) -> None:
    initial_source_balance = amount_cents + expected_fee_cents + 10_000
    source_key = create_account(
        api_database_engine,
        client_type=source_type,
        balance_cents=initial_source_balance,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
        amount_cents,
    )
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    assert response.response_status == 201
    assert response.response_json["fee_cents"] == expected_fee_cents
    assert len(state["entries"]) == 3
    assert state["entries"][1]["entry_type"] == "FEE"
    assert state["entries"][1]["amount_cents"] == expected_fee_cents
    assert state["source"]["balance_cents"] == (
        initial_source_balance - amount_cents - expected_fee_cents
    )
    assert state["target"]["balance_cents"] == amount_cents
