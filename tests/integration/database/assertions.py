"""Leituras do catálogo PostgreSQL reutilizadas nos testes de schema."""

from sqlalchemy import inspect, text


def assert_columns_and_primary_key(engine, table_name, expected_columns, primary_key):
    """Compara todas as colunas e a PK com o contrato físico da tabela.

    Cada valor de `expected_columns` é (tipo SQL, tamanho, 'YES'/'NO').
    A comparação integral também detecta colunas extras fora do ERD.
    """
    with engine.connect() as connection:
        rows = connection.execute(
            text("""
                SELECT column_name, data_type, character_maximum_length, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :table_name
            """),
            {"table_name": table_name},
        ).mappings().all()

    actual_columns = {
        row["column_name"]: (
            row["data_type"],
            row["character_maximum_length"],
            row["is_nullable"],
        )
        for row in rows
    }
    assert actual_columns == expected_columns

    actual_pk = inspect(engine).get_pk_constraint(table_name, schema="public")
    assert actual_pk["constrained_columns"] == primary_key


def assert_foreign_keys(engine, table_name, expected_foreign_keys):
    """Compara coluna de origem, tabela/coluna de destino e ON DELETE."""
    foreign_keys = inspect(engine).get_foreign_keys(table_name, schema="public")
    actual = {
        (
            fk["constrained_columns"][0],
            fk["referred_table"],
            fk["referred_columns"][0],
            fk.get("options", {}).get("ondelete"),
        )
        for fk in foreign_keys
    }
    assert actual == expected_foreign_keys


def assert_unique(engine, table_name, column_name):
    """Exige uma constraint UNIQUE de coluna única no catálogo do PostgreSQL."""
    constraints = inspect(engine).get_unique_constraints(table_name, schema="public")
    unique_columns = {tuple(item["column_names"]) for item in constraints}
    assert (column_name,) in unique_columns


def assert_index(engine, table_name, index_name, columns):
    """Exige o índice aprovado com nome e ordem de colunas esperados."""
    indexes = inspect(engine).get_indexes(table_name, schema="public")
    assert any(
        item["name"] == index_name and item["column_names"] == columns
        for item in indexes
    )
