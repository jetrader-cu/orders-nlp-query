# 📦 Orders NLP Analytics API

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest%20passing-brightgreen.svg)]()

Microservicio analítico y pipeline ETL para procesamiento de pedidos comerciales con interfaz de consulta en lenguaje natural (**Text-to-SQL**) protegida mediante **validación sintáctica AST de solo lectura**.

Permite responder preguntas analíticas en lenguaje natural (ej. *"¿cuánto vendimos en España en marzo?"* o *"¿cuáles son los 10 clientes que más compran?"*), traduciéndolas a consultas SQL optimizadas y garantizando la seguridad absoluta contra SQL Injection o comandos destructivos.

---

## 📑 Tabla de Contenidos

1. [Características Principales](#-características-principales)
2. [Arquitectura del Proyecto](#-arquitectura-del-proyecto)
3. [Instalación y Configuración](#-instalación-y-configuración)
4. [Ejecución del Pipeline ETL](#-ejecución-del-pipeline-etl)
5. [Levantar la API FastAPI](#-levantar-la-api-fastapi)
6. [Ejemplos de Consulta con curl](#-ejemplos-de-consulta-con-curl)
7. [Batería de Pruebas (pytest)](#-batería-de-pruebas-pytest)
8. [Decisiones de Diseño](#-decisiones-de-diseño)
9. [Qué Haría con Más Tiempo](#-qué-haría-con-más-tiempo)
10. [Uso de Inteligencia Artificial (Transparencia)](#-uso-de-inteligencia-artificial-transparencia)

---

## 🚀 Características Principales

- **Pipeline ETL Robusto**:
  - Generación de dataset sintético de pedidos (>=1.200 filas) con anomalías intencionales (duplicados, fechas mal formateadas o inexistentes, importes nulos/negativos).
  - Sanitización estricta: descarte de duplicados, validación de fechas gregorianas, validación financiera (`importe > 0`) y normalización de textos.
  - Registro de métricas de limpieza en consola.
- **Modelos y Vistas Analíticas SQL**:
  - `ventas_por_mes_pais`: Agregación mensual de ventas totales, volumen de pedidos y ticket promedio por país.
  - `top_10_clientes`: Ranking de los diez principales clientes por facturación acumulada.
- **API Text-to-SQL Segura (FastAPI)**:
  - Endpoint `POST /api/query` que traduce lenguaje natural a SQL mediante LLM.
  - **Validador de Seguridad AST (`sqlglot`)**: analiza el Árbol de Sintaxis Abstracta de la consulta antes de ejecutarla.
    - Exclusividad de sentencias `SELECT`.
    - Prohibición de inyecciones por stacking (múltiples sentencias `;`).
    - Lista blanca estricta de tablas (`pedidos`, `ventas_por_mes_pais`, `top_10_clientes`).
    - Prohibición de funciones de sistema o acceso a archivos.
  - Proveedores de LLM intercambiables: Google Gemini, OpenAI o `Mock` determinista (ideal para pruebas sin credenciales ni costes).

---

## 🏛 Arquitectura del Proyecto

```text
.
├── src/
│   ├── api/
│   │   ├── app.py                # Aplicación FastAPI y endpoints REST
│   │   └── schemas.py            # Modelos de request/response Pydantic
│   ├── config.py                 # Configuración tipada con pydantic-settings
│   ├── data/
│   │   ├── cleaner.py            # Pipeline de limpieza y métricas de calidad
│   │   ├── database.py           # Conexión, persistencia y vistas SQL
│   │   ├── generator.py          # Generador de datos con errores intencionales
│   │   └── pipeline.py           # Orquestador del flujo ETL
│   └── services/
│       ├── llm_service.py        # Capa desacoplada de LLMs (Gemini, OpenAI, Mock)
│       └── query_validator.py    # Validador de seguridad AST con sqlglot
├── tests/
│   ├── test_api.py               # Pruebas del endpoint con LLM simulado
│   ├── test_cleaning.py          # Pruebas de limpieza y vistas SQL
│   └── test_validator.py         # Pruebas de seguridad e inyecciones SQL
├── data/                         # Almacenamiento local de CSVs y base de datos
├── DECISIONS.md                  # Registro detallado de decisiones de arquitectura
├── pyproject.toml                # Definición del paquete y dependencias
├── .env.example                  # Plantilla de variables de entorno
└── README.md                     # Documentación principal
```

---

## 🛠 Instalación y Configuración

### 1. Clonar el repositorio
```bash
git clone https://github.com/jetrader-cu/orders-nlp-query.git
cd orders-nlp-query
```

### 2. Crear entorno virtual e instalar dependencias

Con **uv** (recomendado por rapidez):
```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

O con **pip estándar**:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Configurar variables de entorno
Copia la plantilla `.env.example`:
```bash
cp .env.example .env
```
Por defecto `LLM_PROVIDER=mock`, lo que permite probar todo el sistema sin claves de API.
Si deseas usar **Gemini** o **OpenAI**:
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=tu_clave_aqui
LLM_MODEL=gemini-3.1-flash-lite   # Modelo recomendado: gratuito/más económico y de baja latencia
                                  # Alternativa disponible: gemini-3.8-flash
# O para OpenAI:
# LLM_PROVIDER=openai
# OPENAI_API_KEY=tu_clave_aqui
```

---

## ⚙️ Ejecución del Pipeline ETL

Para generar los datos sintéticos con anomalías, limpiarlos y almacenarlos en la base de datos:

```bash
python3 -m src.data.pipeline --count 1200
```

Salida esperada:
```text
📦 Generando 1200 pedidos sintéticos con anomalías...
✅ Archivo crudo guardado en: data/raw_orders.csv
🧹 Limpiando datos desde data/raw_orders.csv...
📊 Métricas del proceso de limpieza:
  - Filas crudas recibidas: 1260
  - Duplicados eliminados: 60
  - Fechas corruptas descartadas: 58
  - Importes vacíos/inválidos descartados: 62
  - Total registros limpios finales: 1080
💾 Cargando 1080 registros en DuckDB/SQLite...
✅ Total registros activos en base de datos: 1080
...
```

---

## 🌐 Levantar la API FastAPI

Inicia el servidor uvicorn:
```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Una vez levantado:
- **API Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

## 📡 Ejemplos de Consulta con curl

### 1. Consulta válida: ventas en España en marzo
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "¿cuánto vendimos en España en marzo?"}'
```

**Respuesta HTTP 200**:
```json
{
  "success": true,
  "question": "¿cuánto vendimos en España en marzo?",
  "sql_query": "SELECT SUM(importe) AS total_ventas FROM pedidos WHERE pais = 'España' AND strftime('%m', fecha) = '03'",
  "columns": ["total_ventas"],
  "results": [
    {
      "total_ventas": 45120.85
    }
  ],
  "row_count": 1,
  "execution_time_ms": 1.45
}
```

### 2. Consulta de agregación: Top 10 clientes
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "¿cuáles son los 10 clientes que más compran?"}'
```

### 3. Intento de inyección o comando no permitido (bloqueado por seguridad)
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Borra la tabla de pedidos"}'
```

**Respuesta HTTP 400 Bad Request**:
```json
{
  "success": false,
  "error_code": "ONLY_SELECT_ALLOWED",
  "message": "La consulta generada no superó las validaciones de seguridad o sintaxis.",
  "detail": "Operación no permitida: 'DROP'. Solo se permiten consultas de lectura (SELECT).",
  "generated_sql": "DROP TABLE pedidos;"
}
```

---

## 🧪 Batería de Pruebas (pytest)

El proyecto incluye una suite de pruebas exhaustiva con pytest que cubre los tres requisitos esenciales más pruebas de integración:

```bash
pytest -v
```

### Cobertura de Pruebas:
1. **`tests/test_cleaning.py`**:
   - `test_generator_creates_expected_volume_and_columns`: Comprueba generación >=1000 pedidos con todos los campos.
   - `test_cleaner_removes_duplicates_invalid_dates_and_empty_amounts`: Verifica descarte exacto de duplicados, fechas erróneas (ej. `2024-02-30`) e importes vacíos/negativos.
   - `test_database_persistence_and_views_creation`: Verifica la creación y funcionamiento de las vistas `ventas_por_mes_pais` y `top_10_clientes`.
2. **`tests/test_validator.py`**:
   - `test_valid_select_queries`: Aprobación de consultas analíticas y CTEs legítimos.
   - `test_reject_destructive_operations`: Bloqueo de `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`.
   - `test_reject_unauthorized_tables`: Bloqueo de accesos a tablas no autorizadas o catálogos (`sqlite_master`, etc.).
   - `test_reject_sql_injection_multiple_statements`: Bloqueo de inyección por sentencias encadenadas con `;`.
   - `test_reject_dangerous_system_functions`: Bloqueo de funciones de filesystem.
   - `test_reject_syntax_errors_and_empty_queries`: Manejo de errores de sintaxis.
3. **`tests/test_api.py`**:
   - `test_natural_language_query_success_with_mock_llm`: Ejecución de flujo completo de lenguaje natural a resultados con LLM simulado.
   - `test_api_rejects_malicious_llm_output`: Verificación de respuesta HTTP 400 ante salida maliciosa o alucinada.
   - `test_api_handles_llm_provider_failure`: Verificación de respuesta HTTP 502 ante fallos de conexión del LLM.

---

## 💡 Decisiones de Diseño

Para un análisis exhaustivo de todas las alternativas y compromisos de ingeniería evaluados, consulta **[DECISIONS.md](DECISIONS.md)**. Resumen de las decisiones clave:

1. **Base de Datos Embebida (SQLite/DuckDB)**: Se priorizó una arquitectura que permita ejecución inmediata sin dependencias de infraestructura externa ni drivers binarios pesados. SQLite proporciona soporte nativo estándar con cero configuración, mientras que la compatibilidad con DuckDB permite analítica OLAP de alta escala.
2. **Seguridad mediante Árbol de Sintaxis Abstracta (AST)**: La validación de consultas SQL generadas por LLMs se realiza a nivel gramatical mediante `sqlglot`. Las expresiones regulares son insuficientes para garantizar seguridad en SQL debido a ofuscaciones y comentarios multi-línea.
3. **Desacoplamiento de Proveedores de LLM**: La interfaz `BaseLLMProvider` permite alternar entre Gemini, OpenAI y un proveedor simulado `MockLLMProvider`, permitiendo evaluar el proyecto sin necesidad de introducir API keys de pago.
4. **Normalización de Nombres de Columnas**: El campo `país` del CSV se mapea internamente a `pais` para evitar problemas de compatibilidad y escaping en consultas generadas por diferentes modelos de lenguaje.

---

## 🔮 Qué Haría con Más Tiempo

1. **Caché Semántica de Consultas (Semantic Cache)**:
   - Implementar un almacenamiento en Redis o SQLite con embeddings vectoriales para preguntas similares (ej. *"¿ventas de España en marzo?"* y *"cuánto se vendió en marzo en España"*), reduciendo costes de inferencia y logrando latencias <5 ms.
2. **Auto-Corrección Asistida por el LLM (Self-Healing SQL)**:
   - Si la consulta SQL generada falla por error de sintaxis en el motor de base de datos, alimentar el mensaje de error de vuelta al LLM para que lo corrija automáticamente (hasta 2 reintentos).
3. **Observabilidad y Trazabilidad (OpenTelemetry)**:
   - Integrar instrumentación OpenTelemetry para trazar la latencia de cada llamada al LLM, tokens consumidos, tiempo de validación AST y tiempo de ejecución de la base de datos.
4. **Few-Shot RAG de Esquema Dinámico**:
   - En bases de datos con cientos de tablas, utilizar búsqueda de similitud sobre los esquemas de tablas para inyectar en el prompt únicamente las tablas relevantes a la pregunta del usuario.
5. **Dashboard Interactivo en Frontend**:
   - Crear una interfaz web ligera y moderna en React/Vite o Streamlit con gráficos automáticos basados en las columnas devueltas por la consulta.

---

## 🤖 Uso de Inteligencia Artificial (Transparencia)

En cumplimiento con la política de transparencia técnica de la prueba:

### ¿Qué se le pidió a la IA?
1. Generación del andamiaje inicial del proyecto y configuración de dependencias en `pyproject.toml`.
2. Sugerencias de datasets sintéticos y listas de productos/clientes realistas con inyección controlada de errores.
3. Estructuración del prompt de Text-to-SQL con el esquema relacional de pedidos y vistas.
4. Generación de casos base para las pruebas de seguridad con pytest.

### ¿Qué se aceptó de la IA?
- La estructura modular del proyecto (`src/api`, `src/data`, `src/services`).
- La taxonomía de errores intencionales en el dataset (duplicados, fechas fuera de rango gregoriano, importes vacíos o textuales).
- La inclusión de métricas de ejecución (tiempo en milisegundos, columnas y recuento de filas) en la respuesta del endpoint.

### ¿Qué se corrigió o descartó manualmente?
- **Validación con Regex descartada**: La IA propuso inicialmente validar el SQL mediante expresiones regulares (`re.match(r'^SELECT', ...)`). Se rechazó por considerarse una vulnerabilidad crítica ante técnicas de elusión de SQL (comentarios multi-línea, tabulaciones, stacking). Se implementó un validador sintáctico formal AST con `sqlglot`.
- **Eliminación de la obligatoriedad de API Keys**: La IA requería `OPENAI_API_KEY` para iniciar el servicio. Se reemplazó por el patrón de fábrica con `MockLLMProvider` para garantizar que la prueba sea reproducible por cualquier evaluador sin credenciales externas.
- **Normalización de caracteres especiales**: La IA conservaba `país` con tilde en el DDL SQL, lo que provocaba errores de parsing según el dialecto. Se normalizó el nombre a `pais` en base de datos.
- **Soporte de CTEs (Common Table Expressions)**: El validador inicial de la IA bloqueaba consultas válidas con `WITH ... AS (...)` al confundir el alias del CTE con una tabla no autorizada. Se corrigió para extraer e incorporar los alias definidos en la cláusula `WITH`.
