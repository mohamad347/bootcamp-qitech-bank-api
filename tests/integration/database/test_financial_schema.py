"""Contrato físico das operações e movimentações financeiras."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.database.assertions import (
    assert_columns_and_primary_key,
    assert_foreign_keys,
    assert_unique,
)
from tests.integration.database.builders import create_account, create_transaction, insert_entry


class TestFinancialTransactionSchema:
    """Identidade, tipo e chave de controle das operações financeiras."""

    def test_columns_and_primary_key(self, schema_engine):
        """As chaves são UUID e o hash da requisição ocupa 64 caracteres."""
        assert_columns_and_primary_key(
            schema_engine,
            "financial_transaction",
            {
                "id": ("bigint", None, "NO"),
                "transaction_key": ("uuid", None, "NO"),
                "request_control_key": ("uuid", None, "NO"),
                "request_hash": ("character", 64, "NO"),
                "transaction_type": ("character varying", 20, "NO"),
                "created_at": ("timestamp with time zone", None, "NO"),
            },
            ["id"],
        )

    @pytest.mark.parametrize("column_name", ["transaction_key", "request_control_key"])
    def test_business_key_is_unique(self, schema_engine, column_name):
        """Cada chave pública/de controle tem uma constraint UNIQUE própria."""
        assert_unique(schema_engine, "financial_transaction", column_name)

    @pytest.mark.parametrize("transaction_type", ["DEPOSIT", "TRANSFER"])
    def test_accepts_approved_transaction_type(self, db_connection, transaction_type):
        """DEPOSIT e TRANSFER são os dois tipos aceitos pelo schema v1.1."""
        transaction_id = create_transaction(db_connection, transaction_type=transaction_type)
        assert transaction_id > 0

    def test_rejects_unknown_transaction_type(self, db_connection):
        """WITHDRAW não faz parte do domínio fechado da v1.1."""
        with pytest.raises(IntegrityError) as error:
            create_transaction(db_connection, transaction_type="WITHDRAW")
        assert error.value.orig.pgcode == "23514"

    def test_request_control_key_is_globally_unique(self, db_connection):
        """Uma chave de idempotência não pode ser reutilizada em outro tipo."""
        request_control_key = str(uuid4())
        create_transaction(db_connection, request_control_key=request_control_key)
        with pytest.raises(IntegrityError) as error:
            create_transaction(
                db_connection,
                transaction_type="TRANSFER",
                request_control_key=request_control_key,
            )
        assert error.value.orig.pgcode == "23505"  # UNIQUE violation


class TestTransactionEntrySchema:
    """Lançamentos positivos ligados à operação e à conta afetada."""

    def test_columns_and_primary_key(self, schema_engine):
        """Valor e saldo posterior são BIGINT; data possui fuso horário."""
        assert_columns_and_primary_key(
            schema_engine,
            "transaction_entry",
            {
                "id": ("bigint", None, "NO"),
                "transaction_id": ("bigint", None, "NO"),
                "account_id": ("bigint", None, "NO"),
                "direction": ("character varying", 10, "NO"),
                "entry_type": ("character varying", 20, "NO"),
                "amount_cents": ("bigint", None, "NO"),
                "balance_after_cents": ("bigint", None, "NO"),
                "created_at": ("timestamp with time zone", None, "NO"),
            },
            ["id"],
        )

    def test_foreign_keys_are_restricted(self, schema_engine):
        """Lançamento exige operação e conta, sem exclusão em cascata."""
        assert_foreign_keys(
            schema_engine,
            "transaction_entry",
            {
                ("transaction_id", "financial_transaction", "id", "RESTRICT"),
                ("account_id", "account", "id", "RESTRICT"),
            },
        )

    def test_accepts_positive_credit(self, db_connection):
        """Crédito PRINCIPAL de valor positivo é persistível."""
        account_id = create_account(db_connection)
        _set_balance(db_connection, account_id, 1)
        transaction_id = create_transaction(db_connection)
        entry_id = insert_entry(
            db_connection, account_id=account_id, transaction_id=transaction_id
        )
        assert entry_id > 0

    def test_accepts_debit_fee(self, db_connection):
        """Débito de tarifa pode ser registrado com saldo final válido."""
        account_id = create_account(db_connection)
        _set_balance(db_connection, account_id, 9)
        transaction_id = create_transaction(db_connection, transaction_type="TRANSFER")
        entry_id = insert_entry(
            db_connection,
            account_id=account_id,
            transaction_id=transaction_id,
            direction="DEBIT",
            entry_type="FEE",
            amount_cents=1,
            balance_after_cents=9,
        )
        assert entry_id > 0

    @pytest.mark.parametrize(
        "invalid_entry",
        [
            pytest.param({"direction": "OTHER"}, id="direction"),
            pytest.param({"entry_type": "OTHER"}, id="entry_type"),
            pytest.param({"amount_cents": 0}, id="amount_zero"),
            pytest.param({"balance_after_cents": -1}, id="negative_balance"),
        ],
    )
    def test_rejects_invalid_values(self, db_connection, invalid_entry):
        """CHECKs recusam direção/tipo desconhecidos e valores fora do domínio."""
        account_id = create_account(db_connection)
        _set_balance(db_connection, account_id, 1)
        transaction_id = create_transaction(db_connection)
        with pytest.raises(IntegrityError) as error:
            insert_entry(
                db_connection,
                account_id=account_id,
                transaction_id=transaction_id,
                **invalid_entry,
            )
        assert error.value.orig.pgcode == "23514"


def _set_balance(connection, account_id, balance_cents):
    """Prepara um saldo coerente para o cenário de lançamento."""
    connection.execute(
        text("UPDATE account SET balance_cents = :balance WHERE id = :id"),
        {"balance": balance_cents, "id": account_id},
    )
