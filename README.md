# AI Commerce

A local application for discovering and comparing products using reviewed facts, configuration requirements, and offer costs. The bundled products, evidence, and prices are fictional.

## Project layout

| Package | Responsibility |
| --- | --- |
| `ai_commerce` | Serve requests, validate the catalog, interpret queries, check requirements, and return product cards |
| `retrieval` | Educational retrieval algorithms used by experiments |
| `experiments` | Optional retrieval evaluation and feature-schema migration demos |

Application files:

| File | Purpose |
| --- | --- |
| `__init__.py` | Marks the directory as a Python package and exposes its version |
| `__main__.py` | Starts the API server when you run `python -m ai_commerce` |
| `api.py` | Handles HTTP routes, reads JSON, and sends responses |
| `request.py` | Defines supported features, validates requests, interprets simple queries, and checks offers |
| `catalog.py` | Reads SQLite records and checks reviewed facts and configurations |
| `storage.py` | Validated database records, SQLite transactions, and full-text search |
| `llm.py` | OpenRouter calls and validated natural-language requirement extraction |
| `service.py` | Applies discovery and comparison rules and builds product responses |

`data/catalog.sqlite3` is a bundled fictional SQLite fixture. The running application stores and queries its data in an in-memory SQLite database. The JSON catalog file has been removed. Changes disappear on restart.

## Run locally

Local development uses Python 3.13, selected in `.python-version`. The package supports Python 3.10+. The API uses FastAPI, Pydantic, Uvicorn, SQLite, and HTTPX. An OpenRouter key is optional; without one, structured discovery and the local query grammar work.

```bash
# macOS, if a suitable Python is not already installed
brew install python@3.13

python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
python -m ai_commerce
```

For later terminal sessions, run `source .venv/bin/activate` from the project directory. Within this environment, `python` and `python3` use Python 3.13. You can also use `.venv/bin/python` directly.

The API listens at `http://127.0.0.1:8000`. Installation also provides `ai-commerce`, which starts the same server with no arguments. Discovery, comparison, and search use the HTTP endpoints below.

For the listen address, set `AI_COMMERCE_HOST` or `AI_COMMERCE_PORT` when needed. Docker sets the host to `0.0.0.0` so its published port works.

Run tests with `python -m unittest discover -v`. HTTP tests use FastAPI’s TestClient.

## API

| Method and path | JSON body | Result |
| --- | --- | --- |
| GET /health | None | Health check |
| POST /discover | Structured request or `{"query":"Find an AC with smart control"}` | Eligible product cards or clarification |
| POST /compare | `{"product_ids":["wash-connect","wash-basic"]}` | Product facts, prerequisites, offer costs, and evidence |
| POST /search | `{"query":"wifi washer","category":"washing_machine"}` | Evidence matches; eligibility is not checked |

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/discover \
  -H 'Content-Type: application/json' \
  --data-binary @examples/wifi_washer.json
```

POST bodies must be JSON objects with Content-Type application/json, at most 16 KiB. Queries are limited to 2,000 characters. Pydantic rejects unknown fields and invalid types with HTTP 422; invalid commerce requirements return HTTP 400. Error responses use a `detail` field. Content-Length is optional; chunked requests are also accepted.

Interactive API documentation is available at `http://127.0.0.1:8000/docs`, with the OpenAPI schema at `/openapi.json`.

Discovery accepts `query`, `category` (`washing_machine`, `ac`, or `dock`), `features`, `budget_paise`, `delivery_by`, `configuration`, and `confirmed_prerequisites`. Money is integer INR paise: INR 10,000 is `1000000`. Budget includes required accessories and shipping. Delivery timestamps must include a timezone.

Discovery checks facts and prerequisites before returning products. Missing or conflicting evidence remains unknown. Dock compatibility requires an exact reviewed host, OS, display configuration, and cable set. The dock example returns dock-d at INR 9,200 including accessories and shipping.

Without OpenRouter, English parsing supports a small local grammar. When configured, OpenRouter extracts natural-language requirements using a validated schema. Ambiguous or unsupported requirements should produce clarification; model understanding is not guaranteed. Use structured fields for precise requirements.

## Enable OpenRouter

```bash
cp .env.example .env
```

Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`, then restart `python -m ai_commerce`. Choose a model that supports [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs). `.env` is ignored by Git and Docker; Compose forwards the configured values at runtime. Environment variables take precedence over `.env` values.

Try a query such as:

```bash
curl -X POST http://127.0.0.1:8000/discover \
  -H 'Content-Type: application/json' \
  -d '{"query":"I need a washer with built-in Wi-Fi for less than forty thousand rupees"}'
```

Only requests containing a query make a model call. It extracts requirements; SQLite and local commerce checks establish facts, compatibility, stock, and prices. Confirmed prerequisites are never supplied by the model. Model failures return HTTP 502; structured requests still work. `/health` reports the configured language-understanding mode.

## Understand the catalog

`Catalog` provides database methods rather than dictionaries. `EvidenceChecks` has been removed; `catalog.verified_feature()` and `catalog.compatibility()` resolve reviewed records directly.

```python
from ai_commerce.catalog import load_catalog

catalog = load_catalog()
try:
    washer = catalog.product("wash-connect")
    print(catalog.verified_feature(washer, "built_in_wifi"))
    catalog.update("offers", "wash-connect", stock=0)
finally:
    catalog.close()
```

A feature is verified only when active reviewed sources agree. Missing or conflicting evidence is unknown. Compatibility requires an exact reviewed setup. See [architecture and evidence examples](docs/architecture.md) for the complete explanation.

Application search uses [SQLite FTS5](https://www.sqlite.org/fts5.html). This version does not require pretrained embeddings or a vector database. OpenRouter integration uses one direct HTTP call, so no agent orchestration framework is needed.

## Optional learning tools

These commands are separate from the application:

```bash
python -m experiments evaluate
python -m experiments ontology-demo
```

Installation also provides `ai-commerce-experiments`. The learning package supports BM25, TF-IDF, PPMI, hybrid rank fusion, and reranking. The application uses SQLite FTS5 with built-in BM25; `/search` accepts only `query` and optional `category`, with no algorithm selection. `--vocabulary-limit` (before the command) accepts 1–1,000, with a default of 500.

See [retrieval mathematics](docs/mathematics.md) and [application architecture](docs/architecture.md). The evaluation uses three synthetic queries; it is a learning exercise. The schema migration demo changes only its own in-memory catalog.

## Docker

```bash
docker compose up --build -d
curl http://127.0.0.1:8000/health
docker compose --profile test run --build --rm tests
docker compose down
```

The container runs as a non-root user and binds the API port to localhost. No external database or persistent volume is required.

## Limits

This application uses Uvicorn to serve a FastAPI application with fictional data. It has no authentication, live inventory, ordering, or shipping integration. Bundled offers last 30 minutes from startup; restarting creates fresh fictional offers. External catalogs retain their supplied timestamps. Search scores rank evidence and do not prove product eligibility.

Apache-2.0; the original license is preserved.
