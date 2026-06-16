# Asistente Clarita — Chatbot RAG con Telegram y LangGraph

Proyecto desarrollado para la asignatura **Ingeniería de Soluciones con Inteligencia Artificial** (Duoc UC).

Un chatbot de Telegram que responde preguntas sobre el contenido del curso usando recuperación aumentada por generación (RAG) sobre documentos PDF ingestados en MongoDB Atlas.

---

## Arquitectura general

```
Usuario (Telegram)
       |
   [Guardrails] — bloquea mensajes ofensivos, prompt injection, temas de guerra
       |
   [Agente LangGraph]
       |
   [generate_query] — reformula la pregunta para búsqueda semántica
       |
   [rag_search] — busca en MongoDB Atlas Vector Search
       |
   [Respuesta al usuario]
       |
   [Supabase] — registra sesión, mensajes y trazas de cada nodo
```

**Stack:**
- **LangGraph** — orquesta el flujo del agente como grafo dirigido
- **MongoDB Atlas Vector Search** — base de conocimiento con embeddings de los PDFs del curso
- **OpenAI** — modelo `gpt-4o-mini` y embeddings `text-embedding-3-small`
- **Guardrails** — 3 evaluadores en paralelo (lenguaje ofensivo, prompt injection, guerra)
- **Supabase (PostgreSQL)** — persistencia de sesiones, mensajes, trazas y costos
- **python-telegram-bot** — interfaz con la API de Telegram

---

## Estructura del proyecto

```
AsistenteClarita/
├── src/
│   ├── agents/
│   │   ├── agent.py           # Grafo LangGraph (nodos, edges, routing)
│   │   ├── prompts.py         # Prompts del sistema y reformulación de queries
│   │   ├── tools.py           # Tool: rag_search (busqueda en MongoDB)
│   │   ├── guardrails.py      # Evaluadores de seguridad paralelos
│   │   └── utils/
│   │       └── embeddings.py  # Cliente de embeddings OpenAI
│   ├── ingesta/
│   │   └── ingest.py          # Pipeline de ingesta de PDFs a MongoDB
│   ├── telegram/
│   │   └── bot.py             # Bot de Telegram (punto de entrada)
│   └── observability/
│       └── supabase_logger.py # Logger de sesiones, mensajes, trazas y costos
├── schema.sql                 # SQL para crear las tablas en Supabase
├── notebook.ipynb             # Guia paso a paso para estudiantes
├── requirements.txt
├── requirements-dev.txt
└── .env                       # Variables de entorno (no subir a git)
```

---

## Variables de entorno requeridas

Crear un archivo `.env` en la raiz del proyecto:

```env
OPENAI_API_KEY=...
MONGODB_CONNECTION_STRING=...
TELEGRAM_BOT_TOKEN=...
SUPABASE_URL=...
SUPABASE_KEY=...        # service_role key (no la anon)
```

---

## Instalacion

```bash
pip install -r requirements.txt
```

Para desarrollo y tests:

```bash
pip install -r requirements-dev.txt
```

---

## Paso 1 — Crear las tablas en Supabase

Ejecutar el contenido de `schema.sql` en el editor SQL de Supabase. Crea tres tablas:

- `sessions` — una sesion por usuario de Telegram
- `messages` — cada mensaje enviado y recibido
- `traces` — cada nodo del grafo que se ejecuto, con tiempos y tokens usados

---

## Paso 2 — Ingestar los PDFs (Pipeline de ingesta)

Antes de correr el bot, es necesario poblar la base de conocimiento en MongoDB Atlas con los documentos del curso.

### Que hace la ingesta

El modulo `src/ingesta/ingest.py` implementa la clase `PDFIngester`, que:

1. **Escanea** una carpeta (o un repositorio de GitHub) en busca de archivos `.pdf`
2. **Convierte** cada PDF a texto usando `MarkItDown`
3. **Divide** el texto en chunks de ~2200 caracteres con overlap de 200 caracteres
4. **Genera embeddings** para cada chunk usando `text-embedding-3-small` de OpenAI
5. **Inserta** los documentos en MongoDB Atlas con el embedding, el texto y metadatos del archivo
6. **Evita duplicados**: si un archivo ya fue ingestado (por nombre), lo omite

### Como ejecutar la ingesta

**Opcion A — Desde una carpeta local con PDFs:**

```python
from src.ingesta.ingest import PDFIngester

ingester = PDFIngester(db_name="agent-rag-duoc-uc", collection_name="embeddings")
ingester.ingest_directory("ruta/a/tu/carpeta/de/pdfs")
```

**Opcion B — Desde el repositorio publico del curso (ya ejecutado):**

El material del curso esta disponible en el repositorio publico:

> https://github.com/Foco22/INGENIERIA-DE-SOLUCIONES-CON-INTELIGENCIA-ARTIFICIAL_002D_OLS

Este repositorio contiene los PDFs de las clases y es la fuente de datos que ya fue ingestada en MongoDB Atlas. **No es necesario volver a ejecutar la ingesta** salvo que se agregue nuevo material.

Para reingestar o actualizar:

```python
from src.ingesta.ingest import PDFIngester

ingester = PDFIngester(db_name="agent-rag-duoc-uc", collection_name="embeddings")
ingester.ingest_from_github("https://github.com/Foco22/INGENIERIA-DE-SOLUCIONES-CON-INTELIGENCIA-ARTIFICIAL_002D_OLS")
```

> La ingesta clona el repositorio en un directorio temporal, procesa todos los PDFs encontrados y luego elimina el directorio. Los archivos ya ingestados (por nombre) se omiten automaticamente.

### Indice de vector search en MongoDB Atlas

Despues de ingestar, crear un indice de tipo **Vector Search** en la coleccion con la siguiente configuracion:

- **Index name:** `vector_index`
- **Field:** `embedding`
- **Dimensions:** `1536` (correspondiente a `text-embedding-3-small`)
- **Similarity:** `cosine`

---

## Paso 3 — Correr el bot

```bash
python -m src.telegram.bot
```

El bot queda en escucha. Cada mensaje de Telegram pasa por el grafo LangGraph y la respuesta se envia de vuelta al usuario.

---

## Tests

```bash
pytest tests/ -v
```

Los tests usan mocks para aislar dependencias externas (OpenAI, MongoDB, Supabase, Telegram).

---

## Observabilidad

Cada interaccion queda registrada en Supabase:

| Tabla | Que guarda |
|-------|-----------|
| `sessions` | Una sesion por usuario (`chat_id` + `thread_id` de LangGraph) |
| `messages` | Cada mensaje del usuario y respuesta del asistente, con flag `blocked` |
| `traces` | Cada nodo del grafo ejecutado: tiempo de inicio, fin, duracion, tokens y costo |
