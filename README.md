# AI Commerce

Explainable feature discovery, product comparison and configuration-specific compatibility, implemented in Python from first principles. **All products, evidence and prices are fictional. This is an educational local application, not a production shopping service.** Apache-2.0; the original license is preserved.

## Run locally

Python 3.10+ is the only runtime dependency. No API keys, embedding downloads, NumPy, databases or framework installation are needed. From the repository directory:

```bash
python -m unittest discover -v
python -m ai_commerce discover --request examples/wifi_washer.json
python -m ai_commerce discover --request examples/dual_monitor_dock.json
python -m ai_commerce discover --request examples/smart_ac.json
python -m ai_commerce discover --query 'Find a washing machine with built-in Wi-Fi under INR 40,000'
python -m ai_commerce compare wash-connect wash-basic wash-pending
python -m ai_commerce search 'two monitor laptop dock' --method hybrid
python -m ai_commerce evaluate
python -m ai_commerce ontology-demo
python -m ai_commerce serve
```

Optional package installation: `python -m pip install .` adds the `ai-commerce` command. Packaging uses setuptools at build time; there are no third-party runtime dependencies. Use `--vocabulary-limit 1000` before the subcommand to change the default cap of 500. Only actual corpus words are included.

## Docker Compose

Install Docker with its Compose plugin, then run:

```bash
docker compose up --build -d
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/discover \
  -H 'Content-Type: application/json' \
  --data-binary @examples/wifi_washer.json
docker compose exec app python -m ai_commerce discover --request examples/dual_monitor_dock.json
docker compose --profile test run --build --rm tests
docker compose logs app
docker compose down
```

Compose includes the API and an optional test-runner service. There are no external service dependencies for this phase: JSON catalog, dictionary vectors/postings, and adjacency-list evidence graph all live in the process. The image contains Python and the source; image building requires internet access to pull the base image. No database volume is required. The API port binds to localhost on your computer. The container runs as a non-root user. Data is in memory; restarting resets the demo and creates fresh fictional offers.

## API

| Method and path | JSON body | Behavior |
| --- | --- | --- |
| GET /health | None | Health check |
| POST /discover | Structured request or `{"query":"Find an AC with smart control"}` | Eligible product cards or clarification |
| POST /compare | `{"product_ids":["wash-connect","wash-basic"]}` | Facts, prerequisites, offer costs and evidence references |
| POST /search | `{"query":"wifi washer","method":"hybrid"}` | Retrieval evidence only; eligibility is not checked |

POST bodies must be JSON objects with Content-Type application/json and Content-Length, at most 16 KiB. Unsupported fields and wrong types are rejected. Text queries are limited to 2,000 characters. The WSGI server is for local demonstrations, with no authentication or production request concurrency guarantees.

Structured discovery fields: `query`, `category` (washing_machine/ac/dock), `features`, `budget_paise`, `delivery_by` (ISO timestamp with timezone), `configuration`, `confirmed_prerequisites`. Budget includes product, required accessories and shipping. Example: INR 10,000 is `1000000` paise. The CLI helper `domain.paise` uses Decimal to avoid floating-point money conversion.

The dock example fixes host revision L42-r2, ExampleOS-1, two extended 1080p60 displays and reviewed-dual-hdmi cables; drivers are forbidden. Only dock-d passes, with INR 8,200 + 800 + 200 = **9,200**. Add an explicit `delivery_by` timestamp to enforce a deadline. The canned example omits a date so it stays runnable.

## Learning order

1. `text.py`: original-word chunks, overlap, tokenizer and bounded vocabulary.
2. `vectors.py`: dictionary dot product, normalization, TF-IDF and word-context PPMI.
3. `search.py`: inverted BM25 term contributions, exact scan, rank fusion and transparent reranker.
4. `ingestion.py`: typed release validation and index construction.
5. `ontology.py` and `graph.py`: governed concept definitions and evidence-backed facts.
6. `domain.py`: typed requests, timestamps, integer money and commerce constraints.
7. `intent.py` and `service.py`: conservative parsing, eligibility and grounded response validation.
8. `evaluation.py` and tests: hand-checked math, negative cases and algorithm comparison.

See [mathematics](docs/mathematics.md) and [architecture](docs/architecture.md) for internals and extension points.

## Scope and limitations

Relevance is separate from verified eligibility, which is separate from purchasability. Hard requirements never become ranking bonuses. Missing, withdrawn, unreviewed or conflicting evidence is UNKNOWN; verified false is distinct. Driver permission does not prove installation. External bridge/module, voice account and region prerequisites must be explicitly confirmed.

English interpretation supports a small grammar. “Smart”, relative delivery dates, negation, and unparsed requirements ask for clarification. Use structured fields for exact configuration and negative feature requirements. It does not understand arbitrary language. Category-wide discovery enumerates this small catalog to avoid losing eligible items to retrieval cutoffs; retrieval scores only order eligible results.

The bundled fixture generates 30-minute offers when loaded; external `--catalog` files keep their supplied timestamps and never silently refresh. There are no real inventory, shipping or order integrations. Product comparisons do not assert compatibility without a supplied configuration.

PPMI is a small distributional baseline, not a pretrained embedding. It cannot establish negation or compatibility. Evaluation has three hand-authored synthetic queries and is not held-out validation. Hybrid retrieval need not outperform lexical baselines. Ontology governance is in memory and the reviewer name is not authenticated identity. Persistent versioning, authorization, real reviewed ingestion, live commerce and controlled actions are future phases.
