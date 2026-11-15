"""Pruebas del proceso de generación, limpieza y persistencia de datos."""

import pytest
from src.data.generator import generate_raw_orders
from src.data.cleaner import clean_orders_records, parse_and_validate_date, parse_and_validate_amount
from src.data.database import DatabaseManager


def test_generator_creates_expected_volume_and_columns():
    """Verifica que el generador cree al menos 1000 pedidos con todas las columnas requeridas."""
    orders = generate_raw_orders(count=1000, seed=123)
    assert len(orders) >= 1000

    sample = orders[0]
    expected_fields = {"fecha", "cliente", "país", "producto", "importe", "estado"}
    assert expected_fields.issubset(set(sample.keys()))


def test_cleaner_removes_duplicates_invalid_dates_and_empty_amounts():
    """
    Verifica que el pipeline de limpieza:
    1. Descarte duplicados exactos.
    2. Descarte fechas corruptas o no parseables.
    3. Descarte importes vacíos, nulos, texto o negativos.
    """
    raw_data = [
        # Registros válidos (uno de ellos duplicado)
        {"fecha": "2024-03-15", "cliente": "Empresa A", "país": "España", "producto": "Laptop", "importe": "1200.50", "estado": "COMPLETADO"},
        {"fecha": "2024-03-15", "cliente": "Empresa A", "país": "España", "producto": "Laptop", "importe": "1200.50", "estado": "COMPLETADO"}, # Duplicado exacto
        {"fecha": "2024-04-10", "cliente": "Empresa B", "país": "México", "producto": "Monitor", "importe": "350.00", "estado": "ENVIADO"},

        # Fechas inválidas
        {"fecha": "2024-02-30", "cliente": "Empresa C", "país": "Chile", "producto": "Mouse", "importe": "50.00", "estado": "COMPLETADO"},
        {"fecha": "fecha_invalida", "cliente": "Empresa D", "país": "España", "producto": "Teclado", "importe": "80.00", "estado": "COMPLETADO"},
        {"fecha": None, "cliente": "Empresa E", "país": "Perú", "producto": "Webcam", "importe": "60.00", "estado": "PENDIENTE"},

        # Importes vacíos / inválidos
        {"fecha": "2024-05-01", "cliente": "Empresa F", "país": "Argentina", "producto": "Hub", "importe": "", "estado": "COMPLETADO"},
        {"fecha": "2024-05-02", "cliente": "Empresa G", "país": "Colombia", "producto": "Cables", "importe": "N/A", "estado": "COMPLETADO"},
        {"fecha": "2024-05-03", "cliente": "Empresa H", "país": "España", "producto": "Licencia", "importe": None, "estado": "COMPLETADO"},
        {"fecha": "2024-05-04", "cliente": "Empresa I", "país": "Francia", "producto": "Soporte", "importe": "-100.00", "estado": "CANCELADO"},
    ]

    clean_records, metrics = clean_orders_records(raw_data)

    # Verificaciones métricas
    assert metrics.total_raw_rows == 10
    assert metrics.duplicates_removed == 1
    assert metrics.invalid_dates_removed == 3
    assert metrics.invalid_amounts_removed == 4
    assert metrics.clean_rows == 2
    assert len(clean_records) == 2

    # Verificar que solo quedaron los registros legítimos
    clientes = {r["cliente"] for r in clean_records}
    assert clientes == {"Empresa A", "Empresa B"}
    assert all(r["importe"] > 0 for r in clean_records)
    assert all(parse_and_validate_date(r["fecha"]) is not None for r in clean_records)


def test_database_persistence_and_views_creation():
    """Verifica que los datos limpios se persistan y las dos vistas SQL funcionen correctamente."""
    clean_data = [
        {"fecha": "2024-03-01", "cliente": "Cliente VIP", "pais": "España", "producto": "Laptop", "importe": 1500.0, "estado": "COMPLETADO"},
        {"fecha": "2024-03-15", "cliente": "Cliente VIP", "pais": "España", "producto": "Monitor", "importe": 500.0, "estado": "COMPLETADO"},
        {"fecha": "2024-04-01", "cliente": "Cliente Normal", "pais": "México", "producto": "Teclado", "importe": 100.0, "estado": "COMPLETADO"},
    ]

    db = DatabaseManager(db_path=":memory:")
    db.initialize_schema()
    loaded_count = db.load_orders(clean_data)

    assert loaded_count == 3

    # Test Vista 1: ventas_por_mes_pais
    v1_results = db.execute_read_query("SELECT * FROM ventas_por_mes_pais WHERE pais = 'España';")
    assert len(v1_results) == 1
    assert v1_results[0]["mes"] == "2024-03"
    assert v1_results[0]["total_ventas"] == 2000.0
    assert v1_results[0]["total_pedidos"] == 2

    # Test Vista 2: top_10_clientes
    v2_results = db.execute_read_query("SELECT * FROM top_10_clientes;")
    assert len(v2_results) == 2
    assert v2_results[0]["cliente"] == "Cliente VIP"
    assert v2_results[0]["total_gastado"] == 2000.0
