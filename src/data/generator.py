"""Generador de datos sintéticos de pedidos con anomalías intencionales."""

import csv
import random
from pathlib import Path
from typing import List, Dict, Any


CUSTOMERS = [
    "TechCorp S.L.",
    "Iberia Solutions",
    "Global Trade Ltd",
    "Marta Gómez",
    "Carlos Ruiz",
    "Innovatech Hub",
    "Logística del Sur",
    "Ana Martínez",
    "DataStream Analytics",
    "Elena Navarro",
    "Nordic Retail Group",
    "Javier Fernández",
    "BioHealth Labs",
    "Lucía Morales",
    "Quantum Software",
]

COUNTRIES = [
    "España",
    "México",
    "Colombia",
    "Argentina",
    "Chile",
    "Perú",
    "Francia",
    "Alemania",
]

PRODUCTS = [
    ("Laptop Pro 16", 1499.99),
    ("Monitor 4K Ultra", 450.00),
    ("Teclado Mecánico RGB", 120.50),
    ("Ratón Ergonómico", 45.00),
    ("Licencia Cloud Anual", 890.00),
    ("Servidor Rack 1U", 2800.00),
    ("Auriculares Cancelación Ruido", 199.90),
    ("Hub USB-C Multipuerto", 59.99),
    ("Cámara Web 4K", 115.00),
    ("Soporte Monitor Doble", 75.00),
]

STATUSES = ["COMPLETADO", "PENDIENTE", "CANCELADO", "ENVIADO"]

# Fechas mal escritas intencionales
INVALID_DATES = [
    "2024-02-30",        # Día inexistente en febrero
    "2024-13-45",        # Mes y día fuera de rango
    "fecha_invalida",    # Texto no fecha
    "32/01/2024",        # Día superior a 31
    "2024/99/01",        # Formato corrupto
    "",                  # Fecha vacía
    "0000-00-00",        # Fecha nula
    "not_a_date",
]

# Importes anómalos intencionales
INVALID_AMOUNTS = [
    "",                  # Vacío
    "N/A",               # Texto
    "NaN",               # Not a Number en texto
    "None",              # Cadena None
    "-150.00",           # Importe negativo
    "gratis",            # No numérico
    "   ",               # Espacios en blanco
]


def generate_raw_orders(
    count: int = 1200,
    seed: int = 42,
    error_rate: float = 0.05,
) -> List[Dict[str, Any]]:
    """
    Genera una lista de pedidos sintéticos con errores deliberados:
    - Duplicados
    - Fechas mal escritas
    - Importes vacíos / inválidos
    """
    random.seed(seed)
    orders: List[Dict[str, Any]] = []

    for i in range(count):
        # Determinar si introducimos un error en este registro
        has_error = random.random() < error_rate
        error_type = random.choice(["date", "amount"]) if has_error else None

        # Fecha base válida en el año 2024
        month = random.randint(1, 12)
        day = random.randint(1, 28)  # Días seguros para cualquier mes
        valid_date = f"2024-{month:02d}-{day:02d}"

        customer = random.choice(CUSTOMERS)
        country = random.choice(COUNTRIES)
        product_name, base_price = random.choice(PRODUCTS)
        # Añadir pequeña variación de precio (descuento o recargo)
        price_variation = round(random.uniform(0.9, 1.1), 2)
        valid_amount = round(base_price * price_variation, 2)
        status = random.choice(STATUSES)

        # Aplicar anomalías si corresponde
        if error_type == "date":
            fecha = random.choice(INVALID_DATES)
            importe = valid_amount
        elif error_type == "amount":
            fecha = valid_date
            importe = random.choice(INVALID_AMOUNTS)
        else:
            fecha = valid_date
            importe = valid_amount

        orders.append({
            "fecha": fecha,
            "cliente": customer,
            "país": country,
            "producto": product_name,
            "importe": importe,
            "estado": status,
        })

    # Inyectar duplicados deliberados (copias exactas de filas existentes)
    duplicate_count = int(count * error_rate)
    for _ in range(duplicate_count):
        idx = random.randint(0, len(orders) - 1)
        # Insertar una réplica exacta
        orders.append(dict(orders[idx]))

    # Barajar para que los duplicados no estén solo al final
    random.shuffle(orders)
    return orders


def save_orders_to_csv(orders: List[Dict[str, Any]], filepath: str | Path) -> Path:
    """Guarda los pedidos en un archivo CSV."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["fecha", "cliente", "país", "producto", "importe", "estado"]
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(orders)

    return path


if __name__ == "__main__":
    output_path = Path("data/raw_orders.csv")
    generated = generate_raw_orders(count=1200)
    save_orders_to_csv(generated, output_path)
    print(f"Generados {len(generated)} pedidos crudos en {output_path}")
