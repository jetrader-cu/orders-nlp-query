"""Esquemas Pydantic para el API REST."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Solicitud para consultar la base de datos en lenguaje natural."""
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        examples=["¿cuánto vendimos en España en marzo?"],
        description="Pregunta en lenguaje natural sobre los pedidos.",
    )


class QueryResponse(BaseModel):
    """Respuesta exitosa con la consulta SQL ejecutada y sus resultados."""
    success: bool = True
    question: str
    sql_query: str
    columns: List[str]
    results: List[Dict[str, Any]]
    row_count: int
    execution_time_ms: float


class ErrorResponse(BaseModel):
    """Respuesta estándar para errores de validación, seguridad o LLM."""
    success: bool = False
    error_code: str
    message: str
    detail: Optional[str] = None
    generated_sql: Optional[str] = None
