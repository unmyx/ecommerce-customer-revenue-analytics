from __future__ import annotations

from novacart.db import split_sql_statements


def test_split_ignores_line_comments_and_blank_statements() -> None:
    script = """
    -- a comment
    CREATE TABLE a (id int);

    -- another comment
    CREATE TABLE b (id int);
    """
    statements = split_sql_statements(script)
    assert len(statements) == 2
    assert statements[0].startswith("CREATE TABLE a")
    assert statements[1].startswith("CREATE TABLE b")


def test_split_keeps_semicolons_inside_string_literals() -> None:
    script = "INSERT INTO t VALUES ('a;b', 'it''s fine'); SELECT 1;"
    statements = split_sql_statements(script)
    assert len(statements) == 2
    assert statements[0] == "INSERT INTO t VALUES ('a;b', 'it''s fine')"


def test_split_handles_block_comments_and_dollar_quotes() -> None:
    script = """
    /* block ; comment */
    CREATE FUNCTION f() RETURNS int AS $$
    BEGIN
        RETURN 1;
    END;
    $$ LANGUAGE plpgsql;
    SELECT 2;
    """
    statements = split_sql_statements(script)
    assert len(statements) == 2
    assert "RETURN 1" in statements[0]
    assert statements[1] == "SELECT 2"


def test_split_returns_trailing_statement_without_semicolon() -> None:
    assert split_sql_statements("SELECT 1") == ["SELECT 1"]

