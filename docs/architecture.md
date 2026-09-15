# Requirements and architecture

## Goal and boundaries

AI Commerce discovers products by verified features, compares evidence-backed facts, and assesses exact reviewed configurations. Local Phase 1 runs Python 3.10+ with standard-library data structures. All catalog content is synthetic. No Kubernetes, microservices, vector database, embedding API, LLM framework or external commerce service is needed.

The three decisions are independent: relevance (retrieval), eligibility (facts/configuration/prerequisites), and purchasability (valid offer, full costs, stock, delivery). Similarity proves neither eligibility nor purchasability.

## Ingestion

Catalog JSON -> validation -> exact product/source resolution -> original-word chunks -> BM25/TF-IDF/PPMI indexes and evidence graph -> in-memory catalog.

Each fact has a typed definition, ontology version, value, evidence IDs and optional prerequisites. Ingestion rejects duplicate IDs, wrong-product evidence, unknown feature definitions, type mismatches, incompatible ontology releases and invalid monetary values. Source records include product ID, publisher, locator, version, active status and reviewed status. Only active reviewed source text enters retrieval. Production ingestion needs authenticated reviews, effective/retrieval timestamps, access scope, immutable releases and supersession handling.

Evidence paths:

- Product -> HAS_FEATURE -> Feature fact -> SUPPORTED_BY -> Evidence source.
- Product -> HAS_ASSESSMENT -> Configuration assessment -> SUPPORTED_BY -> Evidence source.
- Product -> DESCRIBED_BY -> Evidence source.

These are node dictionaries and adjacency lists. An assessment fixes host revision, OS, display mode/resolution and cable set, with supported display count and driver prerequisite. No unconditional transitive compatibility edge is used.

## Runtime

JSON/CLI -> typed request and conservative interpretation -> targeted clarification if necessary -> evidence retrieval/reranking -> verified constraints and configuration checks -> valid full-cost offers -> rank eligible cards -> deterministic rendering -> facts/amounts/citation validation.

Simple structured queries enumerate the category and use direct graph facts; they do not require text matching. For the tiny catalog, enumeration also prevents a retrieval cutoff from silently eliminating otherwise eligible structured matches. Search returns evidence matches only; discovery enforces eligibility. Natural-language unparsed fragments are returned in clarification with the original request, never discarded.

## Status semantics

| Layer | Status | Meaning |
| --- | --- | --- |
| Feature | VERIFIED | Active reviewed evidence agrees on typed value and prerequisites |
| Feature | UNKNOWN | No reliable evidence, or conflicting evidence |
| Configuration | SUPPORTED | Exact assessment and confirmed prerequisites satisfy request |
| Configuration | UNSUPPORTED | Verified display count or driver permission fails |
| Configuration | CONDITIONAL | Required driver installation is unconfirmed |
| Configuration | UNKNOWN | Missing, conflicting or nonmatching assessment |
| Commerce | ELIGIBLE | Current matching INR quote, stock, full budget and delivery pass |
| Commerce | INELIGIBLE | Stock, budget or delivery fails |
| Commerce | UNKNOWN | Missing/expired/mismatched quote or reviewed cable bundle mismatch |

A verified false differs from unknown. App control is distinct from built-in Wi-Fi; bridge-dependent appliances cannot pass built-in Wi-Fi requirements. Voice ecosystem/region prerequisites remain explicit. Driver permission alone does not prove installation.

## Expected scenarios

Built-in Wi-Fi washing machine: wash-connect passes; wash-basic and wash-addon fail a verified value; wash-pending remains unknown. Smart AC asks which capability is intended. App control returns ac-connect; ac-bridge requires confirmed external_bridge. Comparison retains unknown values and cites actual evidence.

The exact dock fixture yields dock-a unsupported (one display), dock-b unsupported (driver forbidden), dock-c ineligible (full cost), dock-d eligible (INR 9,200), dock-e unknown (no assessment). Relative delivery text requires an explicit timezone-aware timestamp. Live delivery is not implemented.

## Ontology evolution

Definition registry version 1 -> proposal tied to version -> named explicit review -> publish version 2 -> evidence-backed backfill -> reingest/rebuild -> regression checks. Stale proposals, unreviewed additions and silent overwrites are rejected. The demo reviewer is metadata, not authenticated authorization. No persistent migration or automatic production governance is claimed.

## Extension phases

Phase 2: introduce replaceable intent, embedding, neural reranking and explanation adapters. Keep these algorithms as baselines. Validate model outputs; facts, configuration and commerce gates remain deterministic. Evaluate on held-out relevance and adversarial eligibility datasets.

Phase 3: authenticated identity/scope, real reviewed sources, persistent versioned stores, live inventory and offer APIs, release management, admission control, observability, recovery and separately authorized cart/order actions. Dynamic ontology changes happen in a governed background process, not query-time mutation. SHACL could validate structures but cannot prove factual truth.

## Deployment

`compose.yaml` runs a local API and an opt-in test runner. No external dependencies are required. Both run the same Docker image. API uses a non-root user and binds host port 8000 to loopback. The standard-library WSGI server is for local learning. It is not a production web server or authentication boundary.
