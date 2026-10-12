"""Cen?rios de R04 organizados por comportamento."""

from .support import *


@pytest.mark.parametrize(
    ("target_status", "expected_client_events"),
    [
        ("PENDING", 1),
        ("REJECTED", 2),
        ("INACTIVE", 3),
    ],
)
def test_create_account_rejects_non_active_client_without_persisting_account(
    api_database_engine: Engine,
    target_status: str,
    expected_client_events: int,
) -> None:
    client_key, email = _create_pending_individual()

    if target_status == "REJECTED":
        _transition_client_status(
            api_database_engine,
            client_key,
            email,
            "INDIVIDUAL",
            expected_status="PENDING",
            next_status="REJECTED",
            reason="Rejeição controlada do cenário R04",
        )
    elif target_status == "INACTIVE":
        _prepare_client_as_active(
            api_database_engine,
            client_key,
            email,
            expected_client_type="INDIVIDUAL",
        )
        _transition_client_status(
            api_database_engine,
            client_key,
            email,
            "INDIVIDUAL",
            expected_status="ACTIVE",
            next_status="INACTIVE",
            reason="Inativação controlada do cenário R04",
        )

    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_error_response(
        response,
        409,
        _expected_invalid_client_status_error(target_status),
    )
    assert _get_client_account_summary(api_database_engine, client_key) == {
        "status": target_status,
        "account_count": 0,
        "account_status": None,
        "account_event_count": 0,
        "client_event_count": expected_client_events,
    }


def test_create_account_rejects_second_request_without_duplicate_persistence(
    api_database_engine: Engine,
) -> None:
    client_key, email = _create_pending_individual()
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )
    first_response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_created_account_response(first_response, client_key)
    before_retry = _get_client_account_summary(api_database_engine, client_key)

    second_response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_error_response(second_response, 409, ACCOUNT_ALREADY_EXISTS_ERROR)
    assert _get_client_account_summary(api_database_engine, client_key) == before_retry
    assert before_retry == {
        "status": "ACTIVE",
        "account_count": 1,
        "account_status": "ACTIVE",
        "account_event_count": 1,
        "client_event_count": 2,
    }


def test_closed_account_remains_unique_for_the_client(
    api_database_engine: Engine,
) -> None:
    client_key, email = _create_pending_individual()
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )
    first_response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_created_account_response(first_response, client_key)
    _close_account_and_inactivate_client(api_database_engine, client_key)
    before_retry = _get_client_account_summary(api_database_engine, client_key)

    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    # F01 valida ACTIVE antes da existência de ACCOUNT. O ciclo F02 de
    # fechamento torna o CLIENT INACTIVE, portanto CLI0002 tem precedência.
    _assert_error_response(
        response,
        409,
        _expected_invalid_client_status_error("INACTIVE"),
    )
    assert _get_client_account_summary(api_database_engine, client_key) == before_retry
    assert before_retry == {
        "status": "INACTIVE",
        "account_count": 1,
        "account_status": "CLOSED",
        "account_event_count": 2,
        "client_event_count": 3,
    }


def test_account_unique_violation_is_translated_to_conflict(
    api_database_engine: Engine,
) -> None:
    client_key, email = _create_pending_individual()
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )

    with _raise_account_client_unique_violation_for_client(
        api_database_engine,
        client_key,
    ):
        response = ClientRequisition.send(
            "POST",
            f"/client/{client_key}/account",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

    _assert_error_response(response, 409, ACCOUNT_ALREADY_EXISTS_ERROR)
    assert _get_client_account_summary(api_database_engine, client_key) == {
        "status": "ACTIVE",
        "account_count": 0,
        "account_status": None,
        "account_event_count": 0,
        "client_event_count": 2,
    }
