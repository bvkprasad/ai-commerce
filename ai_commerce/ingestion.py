"""Validate a synthetic release before building an in-memory catalog and indexes."""
import json
from pathlib import Path
from datetime import timedelta
from .domain import CATEGORIES, nonnegative, timestamp, utcnow
from .ontology import Ontology
from .text import chunk_source, vocabulary
from .vectors import TFIDF, PPMI
from .search import BM25, exact_scan, rrf, rerank_features
from .graph import EvidenceGraph


class Catalog:
    def __init__(self, data, vocabulary_limit=500, ontology=None):
        self.ontology = ontology or Ontology()
        if data['ontology_version'] != self.ontology.version:
            raise ValueError('Catalog and ontology release mismatch')
        self.products, self.sources, self.offers = {}, {}, {}
        for source in data['sources']:
            sid = source['id']
            if sid in self.sources or not isinstance(sid, str) or not sid:
                raise ValueError('Duplicate or invalid source ID')
            for key in ('text', 'locator', 'publisher', 'version', 'product_id'):
                if not isinstance(source[key], str) or not source[key]:
                    raise ValueError('Invalid source metadata')
            for key in ('reviewed', 'active'):
                if type(source[key]) is not bool:
                    raise ValueError('Invalid evidence status')
            self.sources[sid] = source
        for product in data['products']:
            pid = product['id']
            if not isinstance(pid, str) or not pid or pid in self.products:
                raise ValueError('Duplicate or invalid product ID')
            if product['category'] not in CATEGORIES or not isinstance(product['title'], str):
                raise ValueError('Invalid product metadata')
            self.products[pid] = product
            self._references(product['source_ids'], pid)
            for fact in product['facts']:
                self.ontology.validate(fact['name'], fact['value'])
                if fact['ontology_version'] != self.ontology.version:
                    raise ValueError('Fact ontology version mismatch')
                self._references(fact['evidence'], pid)
                prerequisites = fact.get('prerequisites', [])
                if not isinstance(prerequisites, list) or any(not isinstance(x, str) for x in prerequisites):
                    raise ValueError('Invalid prerequisites')
            for assessment in product['assessments']:
                for key in ('host', 'os', 'display_mode', 'resolution', 'cable_set', 'version'):
                    if not isinstance(assessment[key], str) or not assessment[key]:
                        raise ValueError('Invalid assessment metadata')
                nonnegative(assessment['display_count'], 'display_count')
                if type(assessment['driver_required']) is not bool:
                    raise ValueError('Invalid driver prerequisite')
                self._references(assessment['evidence'], pid)
        if any(s['product_id'] not in self.products for s in self.sources.values()):
            raise ValueError('Source refers to unknown product')
        offer_ids = set()
        for offer in data['offers']:
            pid = offer['product_id']
            if pid not in self.products or pid in self.offers or offer['id'] in offer_ids:
                raise ValueError('Invalid or duplicate offer')
            if offer['currency'] != 'INR':
                raise ValueError('Only INR supported')
            for field in ('price_paise', 'accessories_paise', 'shipping_paise', 'stock'):
                nonnegative(offer[field], field)
            if timestamp(offer['valid_from']) >= timestamp(offer['expires_at']):
                raise ValueError('Invalid offer validity interval')
            timestamp(offer['delivery_at'])
            self.offers[pid] = offer
            offer_ids.add(offer['id'])
        self.graph = EvidenceGraph(self.products, self.sources)
        self.chunks = {}
        sources = []
        for source in self.sources.values():
            if not source['active'] or not source['reviewed']:
                continue
            product = self.products[source['product_id']]
            sources.append(source['text'])
            for chunk in chunk_source(source['id'], product['id'], product['title'],
                                      product['category'], source['text']):
                self.chunks[chunk.id] = chunk
        self.words = vocabulary(sources, vocabulary_limit)
        texts = {key: chunk.title + ' ' + chunk.text for key, chunk in self.chunks.items()}
        self.tfidf = TFIDF(list(texts.values()), self.words)
        self.ppmi = PPMI(sources, self.words)
        self.bm25 = BM25(texts)
        self.lexical_vectors = {key: self.tfidf.encode(text) for key, text in texts.items()}
        self.semantic_vectors = {key: self.ppmi.encode(text, self.tfidf) for key, text in texts.items()}

    def _references(self, references, product_id):
        if not isinstance(references, list) or any(sid not in self.sources or
                self.sources[sid]['product_id'] != product_id for sid in references):
            raise ValueError('Missing or wrong-product evidence reference')

    def search(self, query, category=None, method='reranked', limit=20):
        if method not in ('bm25', 'tfidf', 'ppmi', 'hybrid', 'reranked'):
            raise ValueError('Unknown retrieval method')
        allowed = {key for key, chunk in self.chunks.items() if not category or chunk.category == category}
        lexical = [(key, score) for key, score in self.bm25.search(query) if key in allowed]
        semantic = exact_scan(self.ppmi.encode(query, self.tfidf),
                              {key: value for key, value in self.semantic_vectors.items() if key in allowed})
        baseline = exact_scan(self.tfidf.encode(query),
                              {key: value for key, value in self.lexical_vectors.items() if key in allowed})
        fused = rrf(lexical, semantic)
        ranking = {'bm25': lexical, 'tfidf': baseline, 'ppmi': semantic,
                   'hybrid': fused, 'reranked': fused}[method]
        candidates = ranking[:limit]
        result = []
        contributions = self.bm25.contributions(query)
        for key, score in candidates:
            chunk = self.chunks[key]
            features = rerank_features(query, chunk.text, chunk.title, self.tfidf)
            result.append(dict(chunk_id=key, product_id=chunk.product_id, source_id=chunk.source_id,
                               score=features['score'] if method == 'reranked' else score,
                               retrieval_score=score, features=features,
                               bm25_terms=contributions.get(key, {}), start=chunk.start, end=chunk.end))
        return sorted(result, key=lambda x: (-x['score'], x['chunk_id']))


def load_catalog(path=None, now=None, vocabulary_limit=500):
    now = now or utcnow()
    default = path is None
    path = Path(path) if path else Path(__file__).parent / 'data' / 'catalog.json'
    data = json.loads(path.read_text())
    # Only the bundled synthetic fixture mints fresh demo quotes at startup.
    # External catalogs must contain absolute timestamps and are never refreshed.
    if default:
        for offer in data['offers']:
            offer['valid_from'] = now.isoformat()
            offer['expires_at'] = (now + timedelta(minutes=30)).isoformat()
            offer['delivery_at'] = (now + timedelta(hours=20)).isoformat()
    return Catalog(data, vocabulary_limit)
