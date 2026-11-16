# Registro de Decisiones de Diseño y Arquitectura (DECISIONS.md)

Este documento detalla las decisiones técnicas, los compromisos asumidos, el modelo de seguridad y el informe honesto sobre el uso de Inteligencia Artificial en el desarrollo de la prueba técnica.

---

## 0. Ambigüedades del Enunciado y Cómo se Resolvieron

| Punto Abierto | Decisión Tomada | Justificación Técnica |
|---|---|---|
| **Motor de Base de Datos** (PostgreSQL vs SQLite vs DuckDB) | **SQLite por defecto con compatibilidad transparente para DuckDB**. | El enunciado autoriza expresamente cualquiera de los tres. SQLite está embebido en la librería estándar de Python (`sqlite3`), no requiere servicios externos, no depende de descargas binarias pesadas y garantiza ejecución instantánea en cualquier entorno local, Docker o CI. |
| **Normalización del campo `país`** | Se normaliza internamente a `pais` (sin tilde) en el esquema SQL, aceptando `país` en el CSV de entrada. | Los LLM suelen alternar entre `pais` y `país` al generar SQL. Mantener nombres de columna sin caracteres especiales previene errores de sintaxis y discrepancias en queries generadas automáticamente. |
| **Validación de SQL generado por el LLM** | **Validador sintáctico estricto AST (Árbol de Sintaxis Abstracta) con `sqlglot`**, descartando validaciones basadas en expresiones regulares. | Las expresiones regulares son frágiles y trivialmente eludibles mediante comentarios SQL (`/* ... */`), saltos de línea u ofuscación. El análisis AST garantiza validación gramatical matemática de nodos. |
| **Manejo de credenciales de LLM** | Patrón Strategy con tres proveedores (`MockLLMProvider`, `GeminiLLMProvider`, `OpenAILLMProvider`) y configuración vía `.env`. | Permite a cualquier evaluador correr la API y la suite completa de tests de inmediato sin configurar API keys ni incurrir en costes, asegurando al mismo tiempo compatibilidad con modelos de producción (Gemini / OpenAI). |
| **Criterio de fechas inválidas en ETL** | Coerción a ISO-8601 (`YYYY-MM-DD`); descarte riguroso de fechas imposibles (ej. 30 de febrero, día 32, mes 13 o texto). | La consistencia temporal es vital para las vistas agregadas mensuales. Cualquier fecha no fidedigna debe descartarse en la capa de ingesta antes de alcanzar la base de datos. |

---

## 1. Pipeline ETL y Limpieza de Datos

### Generación Sintética (`src/data/generator.py`)
- Se generan al menos 1.200 registros (superando el requisito de 1.000) con una distribución realista de pedidos.
- Se inyecta una tasa de error deliberada (~5% duplicados, ~5% fechas corruptas, ~5% importes vacíos o inválidos) para validar el comportamiento del pipeline de limpieza.

### Sanitización e Ingesta (`src/data/cleaner.py` y `src/data/database.py`)
El pipeline ejecuta las siguientes etapas secuenciales:
1. **Detección y eliminación de duplicados exactos**: elimina filas idénticas preservando la primera aparición.
2. **Validación temporal**: valida que el campo `fecha` sea una fecha válida del calendario gregoriano. Valores como `2024-02-30`, `fecha_invalida` o campos vacíos son descartados.
3. **Validación financiera**: verifica que `importe` sea numérico, no nulo y estrictamente mayor que 0 (`importe > 0`). Valores negativos, textos o cadenas vacías son descartados.
4. **Normalización textual**: se eliminan espacios en blanco sobrantes (`strip`) y se normaliza el estado a mayúsculas (`COMPLETADO`, `PENDIENTE`, `ENVIADO`, `CANCELADO`).
5. **Métricas de proceso**: se emite un objeto `CleaningMetrics` con el recuento exacto de filas crudas, duplicados descartados, fechas inválidas descartadas, importes vacíos descartados y total limpio final.

---

## 2. Modelos y Vistas Analíticas SQL

Se definen dos vistas SQL en la base de datos:

### Vista 1: `ventas_por_mes_pais`
```sql
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
```
*Propósito:* Permite responder con máxima eficiencia preguntas temporales y geográficas (ej. *"¿cuánto vendimos en España en marzo?"*).

### Vista 2: `top_10_clientes`
```sql
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
```
*Propósito:* Segmentación inmediata de clientes de mayor valor (LTV) y ticket promedio por comprador.

---

## 3. Modelo de Seguridad y Validador AST (`src/services/query_validator.py`)

Un LLM nunca debe ser considerado una frontera de seguridad confiable; puede sufrir alucinaciones o ser víctima de prompt injection. Por ello, la capa de seguridad es determinista y no depende del modelo:

1. **Sentencia única (Single Statement)**: Se rechaza cualquier payload que contenga más de una expresión SQL parseada, bloqueando ataques de SQL injection por stacking (`SELECT ...; DROP TABLE pedidos;`).
2. **Restricción a Solo Lectura (`exp.Select`)**: Solo se permiten sentencias `SELECT`. Se rechaza taxativamente cualquier comando `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE` o `PRAGMA`.
3. **Lista blanca estricta de tablas**: Las únicas entidades autorizadas son:
   - `pedidos`
   - `ventas_por_mes_pais`
   - `top_10_clientes`
   Cualquier intento de acceder a catálogos del sistema (`sqlite_master`, `sqlite_schema`, `information_schema`, etc.) o tablas no autorizadas es interceptado antes de la ejecución.
4. **Soporte de CTEs (Common Table Expressions)**: Si una consulta analítica define un CTE (`WITH resumen AS (...) SELECT * FROM resumen`), el validador reconoce los alias legítimos sin comprometer la seguridad.
5. **Bloqueo de funciones del sistema**: Se auditan los nodos funcionales para evitar llamadas a funciones peligrosas de introspección o filesystem.

---

## 4. Uso de IA Generativa y Verificación Humana

Siguiendo las pautas de transparencia técnica, se documenta a continuación cómo se utilizó la IA durante el proyecto:

### ¿Qué se le pidió a la IA?
- Generación del esqueleto inicial de configuración del proyecto y dependencias en `pyproject.toml`.
- Borrador de datos sintéticos y nombres de prueba para pedidos.
- Esquema de prompt engineering para traducción de preguntas en lenguaje natural a SQL DuckDB/SQLite.
- Batería inicial de casos de prueba para pytest.

### ¿Qué se aceptó de la salida de la IA?
- La estructura modular de separación de responsabilidades: `src/data/`, `src/services/`, `src/api/`.
- La lista de clientes y productos ficticios para la generación de datos.
- La idea de retornar metadatos de ejecución (tiempo en ms, columnas y conteo de filas) en la respuesta de la API.

### Errores y limitaciones detectadas en la IA que fueron corregidos manualmente:

| Error / Alucinación de la IA | Riesgo Identificado | Corrección Manual Aplicada |
|---|---|---|
| **Validación de SQL mediante Regex** | La IA sugirió inicialmente validar el SQL con expresiones regulares (`re.match(r'^SELECT', sql, re.I)`). | Se descartó por inseguro: un atacante puede eludir regex con comentarios multi-línea (`/* comment */ SELECT ...; DROP TABLE pedidos;`). Se implementó validación formal con AST mediante `sqlglot`. |
| **Columna con tilde en consultas SQL** | La IA propuso mantener `país` en el DDL de la base de datos. | En SQLite/DuckDB las columnas con tildes requieren delimitadores (`"país"`). Se normalizó a `pais` en base de datos para máxima robustez ante el LLM, manteniendo mapeo transparente desde el CSV. |
| **Falta de soporte para CTEs en el validador** | El validador inicial de la IA bloqueaba consultas con `WITH ... AS (...)` porque interpretaba el nombre del CTE como una tabla no autorizada. | Se modificó la inspección del AST para recolectar los alias definidos en la cláusula `WITH` y autorizarlos únicamente en el ámbito de la consulta. |
| **Dependencia obligatoria de API Keys** | La IA pretendía exigir `OPENAI_API_KEY` para iniciar la aplicación o correr tests. | Se rediseñó la capa de servicios con una interfaz abstracta `BaseLLMProvider` y una implementación `MockLLMProvider` determinista, permitiendo levantar y probar todo el proyecto sin coste ni credenciales. |
| **Tratamiento de fechas en SQLite** | La IA intentó usar sintaxis de PostgreSQL (`DATE_TRUNC('month', fecha)`). | Se adaptó a la función estándar y portable `strftime('%Y-%m', fecha)`, que funciona de forma consistente tanto en SQLite como en DuckDB. |
| **Depreciación del modelo Gemini (`gemini-2.5-flash`)** | La IA sugirió `gemini-2.5-flash` por defecto, el cual fue descontinuado por Google para nuevas claves de API. | Se consultó el catálogo activo de la API v1beta y se configuró `gemini-3.1-flash-lite` (el modelo más eficiente, de menor latencia y gratuito en el free tier) y `gemini-3.8-flash`. |
