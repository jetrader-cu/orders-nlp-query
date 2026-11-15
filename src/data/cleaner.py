"""Módulo de limpieza y sanitización de datos de pedidos."""

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Tuple, Dict, Any, List, Optional


@dataclass
class CleaningMetrics:
    """Métricas del proceso de limpieza de datos."""
    total_raw_rows: int
    duplicates_removed: int
    invalid_dates_removed: int
    invalid_amounts_removed: int
    clean_rows: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_raw_rows": self.total_raw_rows,
            "duplicates_removed": self.duplicates_removed,
            "invalid_dates_removed": self.invalid_dates_removed,
            "invalid_amounts_removed": self.invalid_amounts_removed,
            "clean_rows": self.clean_rows,
        }


def parse_and_validate_date(date_str: Any) -> Optional[str]:
    """
    Valida y formatea una fecha a 'YYYY-MM-DD'.
    Rechaza fechas inexistentes (como 2024-02-30) o formatos corruptos.
    """
    if not date_str:
        return None
    s = str(date_str).strip()
    if not s or s.lower() in ("none", "nan", "null", "n/a", "fecha_invalida", "not_a_date"):
        return None

    # Probar formatos comunes
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            # Validar que el año sea razonable (ej. 2020-2030)
            if 2000 <= dt.year <= 2030:
                return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_and_validate_amount(amount_str: Any) -> Optional[float]:
    """
    Valida y formatea un importe como flotante positivo con 2 decimales.
    Rechaza valores vacíos, nulos, texto o importes <= 0.
    """
    if amount_str is None:
        return None
    s = str(amount_str).strip()
    if not s or s.lower() in ("none", "nan", "null", "n/a", "gratis"):
        return None

    # Limpiar posibles símbolos de moneda
    s_clean = re.sub(r"[€$£]", "", s).strip()
    try:
        val = float(s_clean)
        if val > 0:
            return round(val, 2)
    except ValueError:
        return None
    return None


def clean_orders_records(raw_records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], CleaningMetrics]:
    """
    Limpia una lista de diccionarios de pedidos aplicando reglas de validación:
    1. Eliminación de filas duplicadas exactas.
    2. Filtrado y descarte de fechas corruptas o imposibles en el calendario.
    3. Filtrado y descarte de importes nulos, no numéricos o <= 0.
    4. Normalización de cadenas de texto (strip de espacios, mayúsculas en estado).
    """
    total_raw = len(raw_records)
    duplicates_removed = 0
    invalid_dates_removed = 0
    invalid_amounts_removed = 0

    seen_signatures = set()
    cleaned_records: List[Dict[str, Any]] = []

    for row in raw_records:
        # Generar firma de fila para detección de duplicados
        sig = tuple(str(row.get(k, "")).strip() for k in ["fecha", "cliente", "país", "pais", "producto", "importe", "estado"])
        if sig in seen_signatures:
            duplicates_removed += 1
            continue
        seen_signatures.add(sig)

        # 1. Validar fecha
        raw_date = row.get("fecha")
        valid_date = parse_and_validate_date(raw_date)
        if not valid_date:
            invalid_dates_removed += 1
            continue

        # 2. Validar importe
        raw_amount = row.get("importe")
        valid_amount = parse_and_validate_amount(raw_amount)
        if valid_amount is None:
            invalid_amounts_removed += 1
            continue

        # 3. Normalizar textos
        pais_val = str(row.get("pais") or row.get("país") or "").strip()
        cliente_val = str(row.get("cliente") or "").strip()
        producto_val = str(row.get("producto") or "").strip()
        estado_val = str(row.get("estado") or "COMPLETADO").strip().upper()

        cleaned_records.append({
            "fecha": valid_date,
            "cliente": cliente_val,
            "pais": pais_val,
            "producto": producto_val,
            "importe": valid_amount,
            "estado": estado_val,
        })

    metrics = CleaningMetrics(
        total_raw_rows=total_raw,
        duplicates_removed=duplicates_removed,
        invalid_dates_removed=invalid_dates_removed,
        invalid_amounts_removed=invalid_amounts_removed,
        clean_rows=len(cleaned_records),
    )

    return cleaned_records, metrics


def clean_orders_dataframe(df_raw: Any) -> Tuple[Any, CleaningMetrics]:
    """
    Función de compatibilidad para DataFrames (Pandas) o listas.
    """
    try:
        import pandas as pd
        if isinstance(df_raw, pd.DataFrame):
            records = df_raw.to_dict(orient="records")
            clean_records, metrics = clean_orders_records(records)
            df_clean = pd.DataFrame(clean_records)
            return df_clean, metrics
    except ImportError:
        pass

    if isinstance(df_raw, list):
        return clean_orders_records(df_raw)

    records = list(df_raw)
    return clean_orders_records(records)


def clean_orders_file(
    input_csv_path: str | Path,
    output_csv_path: str | Path | None = None,
) -> Tuple[List[Dict[str, Any]], CleaningMetrics]:
    """Carga un archivo CSV crudo, lo limpia y opcionalmente guarda el resultado."""
    input_path = Path(input_csv_path)
    if not input_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de entrada: {input_path}")

    raw_records: List[Dict[str, Any]] = []
    with open(input_path, mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_records.append(dict(row))

    clean_records, metrics = clean_orders_records(raw_records)

    if output_csv_path:
        out_path = Path(output_csv_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, mode="w", newline="", encoding="utf-8") as f:
            if clean_records:
                fieldnames = ["fecha", "cliente", "pais", "producto", "importe", "estado"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(clean_records)

    return clean_records, metrics
