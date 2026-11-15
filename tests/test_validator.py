"""Pruebas exhaustivas del validador de seguridad SQL (AST)."""

import pytest
from src.services.query_validator import (
    validate_sql_query,
    SQLSecurityError,
    SQLValidationError,
)


def test_valid_select_queries():
    """Verifica que consultas SELECT válidas sobre tablas permitidas sean aprobadas."""
    valid_queries = [
        "SELECT * FROM pedidos;",
        "SELECT pais, SUM(importe) FROM pedidos WHERE pais = 'España' GROUP BY pais;",
        "SELECT * FROM ventas_por_mes_pais WHERE mes = '2024-03';",
        "SELECT cliente, total_gastado FROM top_10_clientes LIMIT 5;",
        "WITH resumen AS (SELECT pais, SUM(importe) as total FROM pedidos GROUP BY pais) SELECT * FROM resumen WHERE total > 1000;",
    ]
    for q in valid_queries:
        is_valid, normalized, _ = validate_sql_query(q)
        assert is_valid is True
        assert len(normalized) > 0


def test_reject_destructive_operations():
    """Verifica el rechazo estricto de cualquier DDL o DML modificador (DROP, DELETE, UPDATE, INSERT, ALTER)."""
    destructive_queries = [
        "DROP TABLE pedidos;",
        "DELETE FROM pedidos WHERE 1=1;",
        "UPDATE pedidos SET importe = 0;",
        "INSERT INTO pedidos VALUES (1, '2024-01-01', 'Hacker', 'España', 'Free', 0, 'OK');",
        "ALTER TABLE pedidos ADD COLUMN malware VARCHAR;",
        "TRUNCATE TABLE pedidos;",
    ]
    for q in destructive_queries:
        with pytest.raises(SQLSecurityError) as exc_info:
            validate_sql_query(q)
        assert "Solo se permiten consultas de lectura (SELECT)" in exc_info.value.message or "Operación no permitida" in exc_info.value.message


def test_reject_unauthorized_tables():
    """Verifica el bloqueo de acceso a tablas del sistema o no incluidas en la lista blanca."""
    unauthorized_queries = [
        "SELECT * FROM sqlite_master;",
        "SELECT * FROM duckdb_tables;",
        "SELECT * FROM information_schema.tables;",
        "SELECT * FROM users;",
        "SELECT * FROM secrets;",
        "SELECT * FROM pedidos JOIN secret_keys ON pedidos.id = secret_keys.id;",
    ]
    for q in unauthorized_queries:
        with pytest.raises(SQLSecurityError) as exc_info:
            validate_sql_query(q)
        assert "Acceso denegado a la tabla/vista" in exc_info.value.message


def test_reject_sql_injection_multiple_statements():
    """Verifica la detección y bloqueo de inyección por encadenamiento de sentencias (stacking)."""
    stacked_queries = [
        "SELECT * FROM pedidos; DROP TABLE pedidos;",
        "SELECT * FROM top_10_clientes; DELETE FROM pedidos;",
        "SELECT 1; SELECT 2;",
    ]
    for q in stacked_queries:
        with pytest.raises(SQLSecurityError) as exc_info:
            validate_sql_query(q)
        assert exc_info.value.code == "MULTIPLE_STATEMENTS_NOT_ALLOWED"


def test_reject_dangerous_system_functions():
    """Verifica el bloqueo de llamadas a funciones de lectura/escritura del filesystem."""
    dangerous_queries = [
        "SELECT * FROM read_csv('/etc/passwd');",
        "SELECT * FROM read_parquet('data.parquet');",
    ]
    for q in dangerous_queries:
        with pytest.raises(SQLSecurityError) as exc_info:
            validate_sql_query(q)
        assert exc_info.value.code in ("FORBIDDEN_FUNCTION_CALL", "UNAUTHORIZED_TABLE_ACCESS")


def test_reject_syntax_errors_and_empty_queries():
    """Verifica el manejo claro de errores de sintaxis o consultas vacías."""
    with pytest.raises(SQLValidationError) as exc_empty:
        validate_sql_query("")
    assert exc_empty.value.code == "EMPTY_QUERY"

    with pytest.raises(SQLValidationError) as exc_syntax:
        validate_sql_query("SELECT FROM WHERE ;")
    assert exc_syntax.value.code in ("SQL_SYNTAX_ERROR", "NO_STATEMENT_FOUND")
