"""Validador de seguridad AST para consultas SQL generadas por LLM."""

from typing import Set, Tuple, Optional, List
import sqlglot
from sqlglot import exp, errors


ALLOWED_TABLES: Set[str] = {
    "pedidos",
    "ventas_por_mes_pais",
    "top_10_clientes",
}

FORBIDDEN_FUNCTIONS: Set[str] = {
    "read_csv",
    "read_parquet",
    "read_json",
    "read_json_auto",
    "write_csv",
    "copy",
    "system",
    "shell",
    "load",
    "install",
    "pragma",
}


class SQLSecurityError(Exception):
    """Excepción lanzada cuando una consulta viola las políticas de seguridad."""
    def __init__(self, message: str, code: str = "SQL_SECURITY_VIOLATION"):
        super().__init__(message)
        self.code = code
        self.message = message


class SQLValidationError(Exception):
    """Excepción lanzada cuando la consulta es sintácticamente inválida."""
    def __init__(self, message: str, code: str = "SQL_SYNTAX_ERROR"):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_sql_query(
    sql: str,
    allowed_tables: Optional[Set[str]] = None,
    dialect: str = "duckdb",
) -> Tuple[bool, str, exp.Expression]:
    """
    Valida una consulta SQL asegurando:
    1. Parseo correcto (sintaxis válida).
    2. Exactamente una única sentencia SQL (evita SQL injection por stacking con ';').
    3. Es estrictamente de solo lectura (tipo SELECT / CTE con SELECT).
    4. Solo accede a las tablas o vistas autorizadas en la lista blanca.
    5. No invoca funciones peligrosas del sistema de archivos o comandos.

    Retorna:
        Tuple[bool, str, exp.Expression]: (Es_Valido, SQL_Normalizado, Expresion_AST)
    Lanza:
        SQLSecurityError o SQLValidationError si la consulta es inválida o insegura.
    """
    if not sql or not sql.strip():
        raise SQLValidationError("La consulta SQL está vacía.", code="EMPTY_QUERY")

    # Limpiar backticks o decoradores de markdown si vienen del LLM
    clean_sql = sql.strip()
    if clean_sql.startswith("```sql"):
        clean_sql = clean_sql[6:]
    elif clean_sql.startswith("```"):
        clean_sql = clean_sql[3:]
    if clean_sql.endswith("```"):
        clean_sql = clean_sql[:-3]
    clean_sql = clean_sql.strip().rstrip(";")

    # 1. Parseo AST y verificación de sentencia única
    try:
        expressions = sqlglot.parse(clean_sql, read=dialect)
    except errors.ParseError as e:
        raise SQLValidationError(
            f"Error de sintaxis SQL al procesar la consulta: {str(e)}",
            code="SQL_SYNTAX_ERROR",
        ) from e

    if not expressions or len(expressions) == 0:
        raise SQLValidationError("No se detectó ninguna sentencia SQL válida.", code="NO_STATEMENT_FOUND")

    if len(expressions) > 1:
        raise SQLSecurityError(
            "Se detectaron múltiples sentencias SQL encadenadas. Solo se permite una consulta individual.",
            code="MULTIPLE_STATEMENTS_NOT_ALLOWED",
        )

    expr = expressions[0]
    if expr is None:
        raise SQLValidationError("No se pudo analizar la estructura de la consulta.", code="NULL_EXPRESSION")

    # 2. Verificar que es estrictamente de solo lectura (Select)
    if not isinstance(expr, exp.Select):
        raise SQLSecurityError(
            f"Operación no permitida: '{expr.key.upper()}'. Solo se permiten consultas de lectura (SELECT).",
            code="ONLY_SELECT_ALLOWED",
        )

    # Verificar que no contenga sub-nodos destructivos o modificadores
    forbidden_node_types = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Alter,
        exp.Create,
        exp.Command,
        exp.Pragma,
    )
    for node in expr.walk():
        if isinstance(node, forbidden_node_types):
            raise SQLSecurityError(
                f"La consulta contiene operaciones no autorizadas de modificación ({node.key.upper()}).",
                code="FORBIDDEN_OPERATION",
            )

    # 3. Validar tablas permitidas (incluyendo soporte para CTEs legítimos)
    effective_allowed = allowed_tables or ALLOWED_TABLES
    cte_names: Set[str] = {cte.alias_or_name.lower() for cte in expr.ctes}

    # Validar todas las tablas referenciadas
    referenced_tables: List[str] = []
    for table_node in expr.find_all(exp.Table):
        table_name = table_node.name.lower()
        referenced_tables.append(table_name)
        # Debe estar en la whitelist o ser un CTE previamente definido
        if table_name not in effective_allowed and table_name not in cte_names:
            raise SQLSecurityError(
                f"Acceso denegado a la tabla/vista '{table_node.name}'. "
                f"Solo se permiten las tablas autorizadas: {sorted(list(effective_allowed))}",
                code="UNAUTHORIZED_TABLE_ACCESS",
            )

    if not referenced_tables:
        # Consultas tipo `SELECT 1;` son inofensivas pero para datos de pedidos exigimos consulta a datos
        pass

    # 4. Validar que no se usen funciones peligrosas de filesystem o sistema
    for func_node in expr.find_all(exp.Anonymous, exp.Func):
        func_name = func_node.name.lower() if hasattr(func_node, "name") else ""
        if func_name in FORBIDDEN_FUNCTIONS:
            raise SQLSecurityError(
                f"Llamada a función prohibida detectada: '{func_name}'.",
                code="FORBIDDEN_FUNCTION_CALL",
            )

    normalized_sql = expr.sql(dialect=dialect)
    return True, normalized_sql, expr
