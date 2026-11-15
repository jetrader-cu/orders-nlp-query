"""Pruebas del API REST con FastAPI y LLM simulado."""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.config import settings
from src.data.database import DatabaseManager
from src.services.llm_service import MockLLMProvider, get_llm_provider


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Inicializa una base de datos de prueba con registros conocidos."""
    test_db_path = "data/test_orders.db"
    settings.database_path = test_db_path

    db = DatabaseManager(db_path=test_db_path)
    db.initialize_schema()

    sample_orders = [
        {"fecha": "2024-03-10", "cliente": "Empresa Alfa", "pais": "España", "producto": "Laptop Pro 16", "importe": 1500.00, "estado": "COMPLETADO"},
        {"fecha": "2024-03-20", "cliente": "Empresa Beta", "pais": "España", "producto": "Monitor 4K", "importe": 500.00, "estado": "COMPLETADO"},
        {"fecha": "2024-04-05", "cliente": "Empresa Gamma", "pais": "México", "producto": "Teclado RGB", "importe": 120.00, "estado": "COMPLETADO"},
        {"fecha": "2024-03-12", "cliente": "Cliente VIP", "pais": "España", "producto": "Servidor 1U", "importe": 3000.00, "estado": "COMPLETADO"},
    ]
    db.load_orders(sample_orders, replace=True)
    yield


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_natural_language_query_success_with_mock_llm(client):
    """
    Verifica que una pregunta en lenguaje natural:
    - Sea procesada por el LLM simulado.
    - Se valide sintáctica y semánticamente.
    - Se ejecute en la base de datos devolviendo resultados esperados.
    """
    response = client.post(
        "/api/query",
        json={"question": "¿cuánto vendimos en España en marzo?"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "total_ventas" in data["columns"] or len(data["results"]) > 0
    assert data["results"][0]["total_ventas"] == 5000.00
    assert "SELECT" in data["sql_query"]
    assert data["execution_time_ms"] >= 0


def test_natural_language_query_top_clients(client):
    """Verifica consulta del ranking de clientes más compradores."""
    response = client.post(
        "/api/query",
        json={"question": "¿cuáles son los clientes que más compran?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["results"]) > 0
    assert data["results"][0]["cliente"] == "Cliente VIP"
    assert data["results"][0]["total_gastado"] == 3000.00


def test_api_rejects_malicious_llm_output(client):
    """
    Verifica que si el LLM intenta generar una sentencia destructiva o fuera de lista blanca,
    la API responda con HTTP 400 y un mensaje de error claro y estructurado.
    """
    malicious_mock = MockLLMProvider(override_sql="DROP TABLE pedidos;")
    app.dependency_overrides[get_llm_provider] = lambda: malicious_mock

    response = client.post(
        "/api/query",
        json={"question": "Elimina todos los pedidos"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "ONLY_SELECT_ALLOWED"
    assert "Solo se permiten consultas de lectura (SELECT)" in data["detail"]


def test_api_handles_llm_provider_failure(client):
    """Verifica que fallos de red o comunicación con el LLM respondan con error claro (HTTP 502)."""
    failing_mock = MockLLMProvider(fail_with_exception=True)
    app.dependency_overrides[get_llm_provider] = lambda: failing_mock

    response = client.post(
        "/api/query",
        json={"question": "¿ventas totales?"},
    )
    assert response.status_code == 502
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "LLM_PROVIDER_ERROR"
    assert "Error al generar la consulta SQL" in data["message"]


def test_api_validation_error_on_empty_payload(client):
    """Verifica que solicitudes con cuerpo vacío o longitud insuficiente sean rechazadas con 422."""
    response = client.post("/api/query", json={"question": "a"})
    assert response.status_code == 422


def test_health_check_endpoint(client):
    """Verifica el endpoint de diagnóstico /api/health."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
