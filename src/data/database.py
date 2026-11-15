"""Módulo de persistencia y vistas SQL en SQLite y DuckDB."""

import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Union


SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    cliente TEXT NOT NULL,
    pais TEXT NOT NULL,
    producto TEXT NOT NULL,
    importe REAL NOT NULL,
    estado TEXT NOT NULL
);

-- Vista 1: Ventas agregadas por mes y país
CREATE VIEW IF NOT EXISTS ventas_por_mes_pais AS
SELECT
    strftime('%Y-%m', fecha) AS mes,
    pais,
    ROUND(SUM(importe), 2) AS total_ventas,
    COUNT(*) AS total_pedidos,
    ROUND(AVG(importe), 2) AS ticket_promedio
FROM pedidos
GROUP BY strftime('%Y-%m', fecha), pais
ORDER BY mes DESC, total_ventas DESC;

-- Vista 2: Los 10 clientes que más compran por volumen acumulado
CREATE VIEW IF NOT EXISTS top_10_clientes AS
SELECT
    cliente,
    ROUND(SUM(importe), 2) AS total_gastado,
    COUNT(*) AS total_pedidos,
    ROUND(AVG(importe), 2) AS ticket_promedio
FROM pedidos
GROUP BY cliente
ORDER BY total_gastado DESC
LIMIT 10;
"""

DUCKDB_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pedidos (
    id BIGINT PRIMARY KEY,
    fecha DATE NOT NULL,
    cliente VARCHAR NOT NULL,
    pais VARCHAR NOT NULL,
    producto VARCHAR NOT NULL,
    importe DOUBLE NOT NULL,
    estado VARCHAR NOT NULL
);

CREATE OR REPLACE VIEW ventas_por_mes_pais AS
SELECT
    strftime(fecha, '%Y-%m') AS mes,
    pais,
    ROUND(SUM(importe), 2) AS total_ventas,
    COUNT(*) AS total_pedidos,
    ROUND(AVG(importe), 2) AS ticket_promedio
FROM pedidos
GROUP BY strftime(fecha, '%Y-%m'), pais
ORDER BY mes DESC, total_ventas DESC;

CREATE OR REPLACE VIEW top_10_clientes AS
SELECT
    cliente,
    ROUND(SUM(importe), 2) AS total_gastado,
    COUNT(*) AS total_pedidos,
    ROUND(AVG(importe), 2) AS ticket_promedio
FROM pedidos
GROUP BY cliente
ORDER BY total_gastado DESC
LIMIT 10;
"""


class DatabaseManager:
    """Gestiona la conexión, creación de tablas y vistas en SQLite o DuckDB."""

    def __init__(self, db_path: str = "data/orders.db", read_only: bool = False):
        self.db_path = db_path
        self.read_only = read_only
        self.is_duckdb = db_path.endswith(".duckdb")
        self._mem_conn: Optional[sqlite3.Connection] = None

    def _get_sqlite_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._mem_conn is None:
                self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._mem_conn.row_factory = sqlite3.Row
            return self._mem_conn

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        if self.read_only and Path(self.db_path).exists():
            uri = f"file:{Path(self.db_path).resolve()}?mode=ro"
            con = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            con = sqlite3.connect(self.db_path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def initialize_schema(self) -> None:
        """Crea las tablas y vistas si no existen."""
        if self.is_duckdb:
            try:
                import duckdb
                with duckdb.connect(self.db_path, read_only=self.read_only) as con:
                    con.execute(DUCKDB_SCHEMA_SQL)
                return
            except ImportError:
                pass

        con = self._get_sqlite_connection()
        con.executescript(SQLITE_SCHEMA_SQL)
        con.commit()

    def load_orders(self, records: Union[List[Dict[str, Any]], Any], replace: bool = True) -> int:
        """
        Inserta los pedidos limpios en la tabla 'pedidos'.
        Acepta una lista de diccionarios o un DataFrame de pandas.
        """
        if hasattr(records, "to_dict"):
            raw_list = records.to_dict(orient="records")
        else:
            raw_list = list(records)

        normalized: List[Dict[str, Any]] = []
        for r in raw_list:
            item = dict(r)
            if "país" in item and "pais" not in item:
                item["pais"] = item.pop("país")
            normalized.append(item)

        if self.is_duckdb:
            try:
                import duckdb
                import pandas as pd
                df = pd.DataFrame(normalized)
                if "id" not in df.columns:
                    df.insert(0, "id", range(1, len(df) + 1))
                df = df[["id", "fecha", "cliente", "pais", "producto", "importe", "estado"]]
                with duckdb.connect(self.db_path) as con:
                    con.execute(DUCKDB_SCHEMA_SQL)
                    if replace:
                        con.execute("DELETE FROM pedidos;")
                    con.register("df_insert", df)
                    con.execute("INSERT INTO pedidos SELECT * FROM df_insert;")
                    con.unregister("df_insert")
                    return con.execute("SELECT COUNT(*) FROM pedidos;").fetchone()[0]
            except ImportError:
                pass

        con = self._get_sqlite_connection()
        con.executescript(SQLITE_SCHEMA_SQL)
        if replace:
            con.execute("DELETE FROM pedidos;")

        cursor = con.cursor()
        rows_to_insert = [
            (
                r["fecha"],
                r["cliente"],
                r["pais"],
                r["producto"],
                float(r["importe"]),
                r["estado"],
            )
            for r in normalized
        ]
        cursor.executemany(
            "INSERT INTO pedidos (fecha, cliente, pais, producto, importe, estado) VALUES (?, ?, ?, ?, ?, ?);",
            rows_to_insert,
        )
        con.commit()
        count = cursor.execute("SELECT COUNT(*) FROM pedidos;").fetchone()[0]
        return count

    def execute_read_query(self, query: str) -> List[Dict[str, Any]]:
        """Ejecuta una consulta SQL de solo lectura y devuelve los resultados en diccionarios."""
        if self.is_duckdb:
            try:
                import duckdb
                with duckdb.connect(self.db_path, read_only=self.read_only) as con:
                    cursor = con.execute(query)
                    cols = [desc[0] for desc in cursor.description]
                    return [dict(zip(cols, row)) for row in cursor.fetchall()]
            except ImportError:
                pass

        con = self._get_sqlite_connection()
        cursor = con.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
