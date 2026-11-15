"""Pipeline ETL completo: generación, limpieza y carga en DuckDB."""

import argparse
from pathlib import Path
from src.data.generator import generate_raw_orders, save_orders_to_csv
from src.data.cleaner import clean_orders_file
from src.data.database import DatabaseManager


def run_pipeline(
    raw_csv_path: str = "data/raw_orders.csv",
    clean_csv_path: str = "data/clean_orders.csv",
    db_path: str = "data/orders.db",
    generate_count: int = 1200,
    force_regenerate: bool = True,
) -> None:
    """Ejecuta el pipeline completo de principio a fin."""
    raw_path = Path(raw_csv_path)

    # 1. Generación de datos crudos si no existe o se fuerza
    if force_regenerate or not raw_path.exists():
        print(f"📦 Generando {generate_count} pedidos sintéticos con anomalías...")
        orders = generate_raw_orders(count=generate_count)
        save_orders_to_csv(orders, raw_path)
        print(f"✅ Archivo crudo guardado en: {raw_path}")

    # 2. Limpieza de datos
    print(f"🧹 Limpiando datos desde {raw_path}...")
    df_clean, metrics = clean_orders_file(raw_path, clean_csv_path)

    print("📊 Métricas del proceso de limpieza:")
    print(f"  - Filas crudas recibidas: {metrics.total_raw_rows}")
    print(f"  - Duplicados eliminados: {metrics.duplicates_removed}")
    print(f"  - Fechas corruptas descartadas: {metrics.invalid_dates_removed}")
    print(f"  - Importes vacíos/inválidos descartados: {metrics.invalid_amounts_removed}")
    print(f"  - Total registros limpios finales: {metrics.clean_rows}")

    # 3. Carga en DuckDB y creación de vistas
    print(f"💾 Cargando {len(df_clean)} registros en DuckDB ({db_path})...")
    db_manager = DatabaseManager(db_path=db_path)
    total_loaded = db_manager.load_orders(df_clean, replace=True)
    print(f"✅ Total registros activos en base de datos: {total_loaded}")

    # 4. Verificación de vistas creadas
    print("\n🔍 Verificación de Vistas Creadas:")
    print("\n📈 [Vista 1] Primeras 3 filas de 'ventas_por_mes_pais':")
    v1_rows = db_manager.execute_read_query("SELECT * FROM ventas_por_mes_pais LIMIT 3;")
    for row in v1_rows:
        print(f"  {row}")

    print("\n🏆 [Vista 2] Primeras 3 filas de 'top_10_clientes':")
    v2_rows = db_manager.execute_read_query("SELECT * FROM top_10_clientes LIMIT 3;")
    for row in v2_rows:
        print(f"  {row}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline ETL de datos de pedidos")
    parser.add_argument("--count", type=int, default=1200, help="Cantidad de pedidos a generar")
    parser.add_argument("--raw", type=str, default="data/raw_orders.csv", help="Ruta CSV crudo")
    parser.add_argument("--clean", type=str, default="data/clean_orders.csv", help="Ruta CSV limpio")
    parser.add_argument("--db", type=str, default="data/orders.db", help="Ruta de la base de datos (SQLite o DuckDB)")
    args = parser.parse_args()

    run_pipeline(
        raw_csv_path=args.raw,
        clean_csv_path=args.clean,
        db_path=args.db,
        generate_count=args.count,
    )
