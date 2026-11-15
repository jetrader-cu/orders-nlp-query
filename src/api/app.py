"""Aplicación FastAPI principal con endpoint Text-to-SQL protegido."""

import time
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.api.schemas import QueryRequest, QueryResponse, ErrorResponse
from src.data.database import DatabaseManager
from src.services.llm_service import (
    get_llm_provider,
    BaseLLMProvider,
    LLMError,
)
from src.services.query_validator import (
    validate_sql_query,
    SQLSecurityError,
    SQLValidationError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar si no existe."""
    db = DatabaseManager(db_path=settings.database_path)
    db.initialize_schema()
    yield


app = FastAPI(
    title="Orders NLP Analytics API",
    description="API REST para consultar pedidos en lenguaje natural convertidos a SQL con validación estricta de solo lectura.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["Salud"])
def health_check():
    """Comprobación de estado del servicio."""
    return {
        "status": "healthy",
        "llm_provider": settings.llm_provider,
        "database": settings.database_path,
    }


@app.post(
    "/api/query",
    response_model=QueryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Consulta inválida o rechazada por seguridad"},
        502: {"model": ErrorResponse, "description": "Error en el proveedor de LLM"},
    },
    tags=["Consultas"],
)
def execute_natural_language_query(
    request: QueryRequest,
    provider: BaseLLMProvider = Depends(get_llm_provider),
):
    """
    Endpoint principal:
    1. Recibe una pregunta en lenguaje natural (ej. '¿cuánto vendimos en España en marzo?').
    2. Utiliza un LLM para convertirla a consulta SQL.
    3. Valida la consulta con un analizador sintáctico AST (solo lectura y tablas autorizadas).
    4. Ejecuta la consulta en la base de datos de forma segura.
    5. Retorna los resultados o un error explicativo claro si falla.
    """
    # 1. Generación de SQL mediante LLM
    try:
        raw_sql = provider.generate_sql(request.question)
    except LLMError as e:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=ErrorResponse(
                success=False,
                error_code=e.code,
                message="Error al generar la consulta SQL mediante el modelo de lenguaje.",
                detail=e.message,
            ).model_dump(),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                success=False,
                error_code="LLM_INTERNAL_ERROR",
                message="Fallo inesperado en el servicio del modelo de lenguaje.",
                detail=str(e),
            ).model_dump(),
        )

    # 2. Validación de seguridad sintáctica y permisos
    try:
        is_valid, validated_sql, _ = validate_sql_query(raw_sql)
    except (SQLSecurityError, SQLValidationError) as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error_code=e.code,
                message="La consulta generada no superó las validaciones de seguridad o sintaxis.",
                detail=e.message,
                generated_sql=raw_sql,
            ).model_dump(),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error_code="UNKNOWN_VALIDATION_ERROR",
                message="Error al validar la consulta SQL.",
                detail=str(e),
                generated_sql=raw_sql,
            ).model_dump(),
        )

    # 3. Ejecución segura en base de datos
    start_time = time.perf_counter()
    try:
        db = DatabaseManager(db_path=settings.database_path)
        results = db.execute_read_query(validated_sql)
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        columns = list(results[0].keys()) if results else []

        return QueryResponse(
            success=True,
            question=request.question,
            sql_query=validated_sql,
            columns=columns,
            results=results,
            row_count=len(results),
            execution_time_ms=elapsed_ms,
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error_code="DB_EXECUTION_ERROR",
                message="Error durante la ejecución de la consulta en la base de datos.",
                detail=str(e),
                generated_sql=validated_sql,
            ).model_dump(),
        )


@app.post("/query", response_model=QueryResponse, include_in_schema=False)
def execute_query_legacy(
    request: QueryRequest,
    provider: BaseLLMProvider = Depends(get_llm_provider),
):
    """Ruta alias para compatibilidad."""
    return execute_natural_language_query(request, provider)
