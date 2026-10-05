# Application architecture

## Request flow

`python -m ai_commerce` starts FastAPI through Uvicorn. There are no application subcommands.

```mermaid
flowchart LR
    Query[User query] --> Interpret[OpenRouter or local rules]
    Interpret --> Validate[Pydantic validates requirements]
    Validate --> Catalog[SQLite catalog and FTS5 search]
    Catalog --> Evidence[Reviewed facts and exact configurations]
    Evidence --> Offers[Budget, stock, and delivery checks]
    Offers --> Cards[Verified product cards]
```

OpenRouter is used only when both its API key and model are configured. Structured requests with an empty query skip the LLM. The model extracts requirements; it does not choose products, establish compatibility, invent prices, or place orders. Returned cards and explanations still come from verified data and deterministic rules.

## What Catalog does

`Catalog` is a small interface over the database. Call `products(category)`, `product(id)`, `source(id)`, `offer(product_id)`, or `search(query)`. These methods read SQLite records. They do not expose a mutable catalog dictionary. Changing a returned dictionary does not update the database.

`storage.py` defines validated Pydantic records and SQLite tables. Products, sources, and offers have primary keys; source and offer ownership use foreign keys. Nested feature facts, prerequisites, and configuration assessments are JSON values inside database records. Their references and types are validated before committing a release. This first version uses a document-oriented relational schema rather than separate tables for every feature and cable setting.

Use `catalog.update('offers', 'wash-connect', stock=0)` for a validated update. Updates commit records and rebuild the FTS index in one transaction. Failed validation leaves the previous release intact. A lock protects the shared SQLite connection used by FastAPI worker threads.

Each process has its own in-memory SQLite database. Startup imports the fictional fixture from `ai_commerce/data/catalog.sqlite3`; the application never edits that fixture. Changes are lost on shutdown. `catalog.db.save(path)` can explicitly export a snapshot for local development; an explicitly loaded snapshot retains its original offer timestamps.

## What happened to EvidenceChecks

There is no separate `EvidenceChecks` class. These methods live on `Catalog`:

| Method | Question it answers |
| --- | --- |
| `evidence_active(source_ids)` | Do all cited sources exist, have a review, and remain active? |
| `verified_feature(product, name)` | Do the reviewed facts agree on the value and prerequisites? |
| `compatibility(product, configuration)` | Does an exact reviewed assessment match this setup, display count, and driver requirements? |

For example, a manual might explicitly say that a washer has built-in Wi-Fi. If that source is reviewed and active, the feature is verified true. A reviewed statement that it lacks Wi-Fi gives verified false. An absent, withdrawn, or contradictory statement gives unknown. App control does not establish built-in Wi-Fi because an external bridge might be required.

For docks, the host revision, OS, display mode, resolution, and cable set must match a reviewed assessment. The method then checks display count and driver requirements. Permission to install a driver does not establish that it is installed.

These checks remain necessary even when an LLM understands the request: understanding the words does not prove the product can satisfy them.

## Search

The application uses SQLite FTS5 and its built-in BM25 ranking over reviewed active source text and product titles. It supports ordinary words, category filters, stemming, and Wi-Fi spelling normalization. It returns source IDs, product IDs, and scores. Search scores do not establish product eligibility.

Discovery enumerates all products in the requested category before applying requirements. A search cutoff cannot exclude an otherwise eligible product.

There is no vector database in this version: there are no pretrained embeddings or similarity requirements that need one. The tiny catalog fits SQLite full-text search. Chroma can be introduced together with a real embedding pipeline when semantic retrieval is needed.

The `retrieval` package contains the educational BM25, TF-IDF, PPMI, and hybrid algorithms. Only `experiments` imports that package; application startup and requests use SQLite search.

## OpenRouter

`llm.py` uses HTTPX for a direct request to OpenRouter's chat completions endpoint with a strict JSON schema. It sends the user's query and supported feature definitions, rather than the catalog or credentials in the prompt. A configured model must support structured outputs.

The extracted category, feature requirements, budget, exact delivery timestamp, and configuration are validated by Pydantic. Ambiguous or unsupported requirements should produce clarification questions. Explicit structured requirements are preserved; disagreements produce clarification. Confirmed external prerequisites come only from the original explicit request.

The client uses a connection timeout, bounded output tokens, and no application-level retries. Refusals, truncation, malformed outputs, invalid requirements, timeouts, and provider errors return a safe HTTP 502. A failing configured model does not silently fall back to a weaker interpretation. Without an API key, the existing small local grammar is used.

This is one model call followed by ordinary Python decisions. LangChain or LangGraph would add orchestration without a workflow that currently needs it. Model interpretation can still be wrong; prompts and schema validation do not establish perfect language understanding.

## Status semantics

| Layer | Status | Meaning |
| --- | --- | --- |
| Feature | VERIFIED | Active reviewed evidence agrees on value and prerequisites |
| Feature | UNKNOWN | Evidence is missing, inactive, unreviewed, or conflicting |
| Configuration | SUPPORTED | Exact reviewed configuration satisfies the request |
| Configuration | UNSUPPORTED | Display count or driver permission fails |
| Configuration | CONDITIONAL | Required driver installation is unconfirmed |
| Configuration | UNKNOWN | Assessment is missing, conflicting, or does not match |
| Offer | ELIGIBLE | Current INR quote, stock, full budget, and delivery pass |
| Offer | INELIGIBLE | Stock, budget, or delivery fails |
| Offer | UNKNOWN | Quote is missing, stale, or mismatched |

## Deployment

FastAPI's lifespan hook opens the database and optional OpenRouter client before serving requests and closes both at shutdown. Synchronous routes run in the framework's thread pool. `/docs` and `/openapi.json` describe the request schemas.

Docker Compose passes OpenRouter environment variables and runs without an external database. Its API port is published on localhost. The catalog remains fictional; there are no inventory, shipping, authentication, or ordering integrations.
