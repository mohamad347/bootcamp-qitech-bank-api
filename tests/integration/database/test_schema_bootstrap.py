"""O script principal deve criar somente as tabelas aprovadas no ERD v1.1."""

from sqlalchemy import text


ERD_TABLES = {
    "client_status",
    "client",
    "individual_client",
    "company_client",
    "client_status_event",
    "account_status",
    "account",
    "account_status_event",
    "financial_transaction",
    "transaction_entry",
}


def test_clean_bootstrap_contains_only_erd_tables(schema_engine):
    """O SQL principal instala exatamente as dez tabelas aprovadas."""
    with schema_engine.connect() as connection:
        actual_tables = set(
            connection.execute(
                text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                """)
            ).scalars().all()
        )

    assert actual_tables == ERD_TABLES
