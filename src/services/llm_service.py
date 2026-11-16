"""Servicio de generación Text-to-SQL mediante LLM (Gemini, OpenAI, Mock)."""

import os
import re
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import httpx

from src.config import settings


DATABASE_SCHEMA_PROMPT = """
Eres un asistente experto en ingeniería de datos y SQL para DuckDB.
Tu tarea es convertir una pregunta en lenguaje natural del usuario en una única consulta SQL válida de solo lectura (SELECT).

ESQUEMA DE BASE DE DATOS DISPONIBLE:
1. Tabla 'pedidos':
   - id: BIGINT (identificador único)
   - fecha: DATE (formato 'YYYY-MM-DD', año 2024)
   - cliente: VARCHAR (nombre del cliente o empresa)
   - pais: VARCHAR (país del pedido, ej. 'España', 'México', 'Colombia', 'Argentina', 'Chile', 'Perú', 'Francia', 'Alemania')
   - producto: VARCHAR (nombre del producto)
   - importe: DOUBLE (monto de la venta en euros)
   - estado: VARCHAR ('COMPLETADO', 'PENDIENTE', 'CANCELADO', 'ENVIADO')

2. Vista 'ventas_por_mes_pais':
   - mes: VARCHAR (formato 'YYYY-MM')
   - pais: VARCHAR
   - total_ventas: DOUBLE (suma de importes)
   - total_pedidos: BIGINT (conteo de pedidos)
   - ticket_promedio: DOUBLE (promedio de importe)

3. Vista 'top_10_clientes':
   - cliente: VARCHAR
   - total_gastado: DOUBLE (total acumulado)
   - total_pedidos: BIGINT
   - ticket_promedio: DOUBLE

REGLAS CRÍTICAS DE SEGURIDAD Y FORMATO:
- Emite ÚNICAMENTE la sentencia SQL pura.
- NO agregues bloques de código markdown (como ```sql ... ```).
- NO agregues explicaciones, introducciones ni conclusiones.
- La consulta DEBE ser estrictamente de lectura (SELECT). NUNCA generes INSERT, UPDATE, DELETE, DROP, ALTER ni PRAGMA.
- Solo puedes consultar las tablas o vistas: 'pedidos', 'ventas_por_mes_pais', 'top_10_clientes'.
- Si la pregunta pide ventas en España en marzo, por ejemplo:
  SELECT SUM(importe) AS total_ventas FROM pedidos WHERE pais = 'España' AND strftime(fecha, '%m') = '03';
  o usando la vista:
  SELECT total_ventas FROM ventas_por_mes_pais WHERE pais = 'España' AND mes = '2024-03';
"""


class LLMError(Exception):
    """Excepción base para errores en el servicio LLM."""
    def __init__(self, message: str, code: str = "LLM_PROVIDER_ERROR"):
        super().__init__(message)
        self.code = code
        self.message = message


class BaseLLMProvider(ABC):
    """Interfaz abstracta para proveedores de modelos de lenguaje."""

    @abstractmethod
    def generate_sql(self, question: str) -> str:
        """Genera una sentencia SQL a partir de la pregunta del usuario."""
        pass


class MockLLMProvider(BaseLLMProvider):
    """
    Proveedor simulado determinista para pruebas automáticas y ejecución offline.
    Mapea preguntas comunes a sentencias SQL válidas y permite simular errores.
    """

    def __init__(self, override_sql: Optional[str] = None, fail_with_exception: bool = False):
        self.override_sql = override_sql
        self.fail_with_exception = fail_with_exception

    def generate_sql(self, question: str) -> str:
        if self.fail_with_exception:
            raise LLMError("Error simulado de comunicación con el servicio LLM.")

        if self.override_sql:
            return self.override_sql

        q_lower = question.lower().strip()

        # Preguntas sobre España y marzo (ejemplo de la prueba)
        if "españa" in q_lower and ("marzo" in q_lower or "03" in q_lower):
            return "SELECT SUM(importe) AS total_ventas FROM pedidos WHERE pais = 'España' AND strftime('%m', fecha) = '03';"

        # Preguntas sobre top clientes / más compran
        if "top" in q_lower or "más compran" in q_lower or "mas compran" in q_lower or "mejores clientes" in q_lower:
            return "SELECT * FROM top_10_clientes;"

        # Preguntas sobre ventas por mes y país
        if ("ventas por mes" in q_lower) or ("por mes y país" in q_lower) or ("por mes y pais" in q_lower):
            return "SELECT * FROM ventas_por_mes_pais ORDER BY mes DESC, total_ventas DESC;"

        # Preguntas sobre total general de ventas
        if "total" in q_lower and "ventas" in q_lower:
            return "SELECT ROUND(SUM(importe), 2) AS total_ventas, COUNT(*) AS total_pedidos FROM pedidos;"

        # Preguntas por país específico
        for pais in ["méxico", "mexico", "colombia", "argentina", "chile", "perú", "peru", "francia", "alemania"]:
            if pais in q_lower:
                pais_db = "México" if "mex" in pais else ("Perú" if "per" in pais else pais.capitalize())
                return f"SELECT COUNT(*) AS pedidos, ROUND(SUM(importe), 2) AS total FROM pedidos WHERE pais = '{pais_db}';"

        # Default fallback para preguntas generales
        return f"SELECT * FROM pedidos WHERE cliente ILIKE '%{question[:20].strip()}%' LIMIT 10;"


class GeminiLLMProvider(BaseLLMProvider):
    """Proveedor que interactúa con el API de Gemini (Google GenAI o REST)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or settings.llm_model or "gemini-3.1-flash-lite"
        if not self.api_key:
            raise LLMError(
                "No se encontró GEMINI_API_KEY configurada. "
                "Define la variable en el archivo .env o selecciona LLM_PROVIDER=mock.",
                code="MISSING_API_KEY",
            )

    def generate_sql(self, question: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        prompt = f"{DATABASE_SCHEMA_PROMPT}\n\nPregunta del usuario:\n{question}\n\nConsulta SQL:"
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 256,
            }
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, headers=headers, json=payload)
                if response.status_code != 200:
                    raise LLMError(
                        f"Error devuelto por Gemini API ({response.status_code}): {response.text}",
                        code="API_HTTP_ERROR",
                    )
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return self._clean_llm_sql(text)
        except httpx.RequestError as e:
            raise LLMError(f"Error de red al conectar con Gemini: {str(e)}", code="NETWORK_ERROR") from e
        except (KeyError, IndexError) as e:
            raise LLMError("Respuesta inesperada o vacía del modelo Gemini.", code="EMPTY_RESPONSE") from e

    @staticmethod
    def _clean_llm_sql(text: str) -> str:
        """Remueve posibles bloques ```sql de la respuesta."""
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:sql)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()


class OpenAILLMProvider(BaseLLMProvider):
    """Proveedor compatible con la API de OpenAI y endpoints compatibles (Ollama, vLLM)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or "gpt-4o-mini"
        if not self.api_key:
            raise LLMError(
                "No se encontró OPENAI_API_KEY configurada.",
                code="MISSING_API_KEY",
            )

    def generate_sql(self, question: str) -> str:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": DATABASE_SCHEMA_PROMPT},
                {"role": "user", "content": question},
            ],
            "temperature": 0.0,
            "max_tokens": 256,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, headers=headers, json=payload)
                if response.status_code != 200:
                    raise LLMError(
                        f"Error devuelto por OpenAI API ({response.status_code}): {response.text}",
                        code="API_HTTP_ERROR",
                    )
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                cleaned = re.sub(r"^```(?:sql)?\s*", "", text.strip(), flags=re.IGNORECASE)
                cleaned = re.sub(r"\s*```$", "", cleaned)
                return cleaned.strip()
        except httpx.RequestError as e:
            raise LLMError(f"Error de red al conectar con OpenAI: {str(e)}", code="NETWORK_ERROR") from e


def get_llm_provider(
    provider_name: Optional[str] = None,
    mock_override_sql: Optional[str] = None,
    mock_fail: bool = False,
) -> BaseLLMProvider:
    """Fábrica para instanciar el proveedor de LLM según la configuración."""
    selected = (provider_name or settings.llm_provider).lower()

    if selected == "gemini":
        return GeminiLLMProvider()
    elif selected == "openai":
        return OpenAILLMProvider()
    elif selected == "mock":
        return MockLLMProvider(override_sql=mock_override_sql, fail_with_exception=mock_fail)
    else:
        # Por defecto usar mock si no se especifica o no es reconocido
        return MockLLMProvider(override_sql=mock_override_sql, fail_with_exception=mock_fail)
