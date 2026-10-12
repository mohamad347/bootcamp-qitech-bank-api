from uuid import uuid4

import pytest

from tests.integration.transaction.support import send_deposit
from tests.utils import INTERNAL_TOKEN
from tests.utils.requisition import ClientRequisition


def _send_transaction(
    account_key: str,
    payload: dict,
):
    return ClientRequisition.send(
        "POST",
        f"/account/{account_key}/transaction",
        headers={
            "INTERNAL-TOKEN": INTERNAL_TOKEN,
            "Idempotency-Key": str(uuid4()),
        },
        payload=payload,
    )


def test_deposit_requires_idempotency_key(active_account_key: str) -> None:
    response = send_deposit(active_account_key, None)

    assert response.response_status == 400
    assert response.response_json["code"] == "QIT000001"


def test_deposit_rejects_invalid_idempotency_key(
    active_account_key: str,
) -> None:
    response = send_deposit(active_account_key, "not-a-uuid")

    assert response.response_status == 400
    assert response.response_json["code"] == "QIT000001"


def test_deposit_rejects_invalid_account_key() -> None:
    response = send_deposit("not-a-uuid", uuid4())

    assert response.response_status == 400
    assert response.response_json["code"] == "QIT000001"


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"transaction_type": "WITHDRAWAL", "amount_cents": 50_000},
        {"transaction_type": "deposit", "amount_cents": 50_000},
        {
            "transaction_type": "DEPOSIT",
            "target_account_key": str(uuid4()),
            "amount_cents": 50_000,
        },
        {
            "transaction_type": "DEPOSIT",
            "amount_cents": 50_000,
            "unexpected": True,
        },
        {"transaction_type": "DEPOSIT", "amount_cents": "50000"},
        {"transaction_type": "DEPOSIT"},
    ],
    ids=[
        "invalid-transaction-type",
        "lowercase-transaction-type",
        "target-account-on-deposit",
        "extra-property",
        "invalid-amount-type",
        "missing-amount",
    ],
)
def test_deposit_rejects_structurally_invalid_body(
    active_account_key: str,
    invalid_payload: dict,
) -> None:
    response = _send_transaction(active_account_key, invalid_payload)

    assert response.response_status == 400
    assert response.response_json["code"] == "QIT000001"
