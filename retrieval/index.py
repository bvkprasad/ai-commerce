"""Build and search indexes independently of request and offer rules."""
from .text import chunk_source, vocabulary
from .vectors import TFIDF, PPMI
from .search import BM25, exact_scan, rrf, rerank_features


class SearchIndex:
    def __init__(self, products, sources, vocabulary_limit=500):
        self.products = products
        self.sources = sources
        self.chunks = {}
        source_texts = []
        for source in self.sources.values():
            if not source['active'] or not source['reviewed']:
                continue
            product = self.products[source['product_id']]
            source_texts.append(source['text'])
            for chunk in chunk_source(source['id'], product['id'], product['title'],
                                      product['category'], source['text']):
                self.chunks[chunk.id] = chunk
        self.words = vocabulary(source_texts, vocabulary_limit)
        texts = {key: chunk.title + ' ' + chunk.text for key, chunk in self.chunks.items()}
        self.tfidf = TFIDF(list(texts.values()), self.words)
        self.ppmi = PPMI(source_texts, self.words)
        self.bm25 = BM25(texts)
        self.lexical_vectors = {key: self.tfidf.encode(text) for key, text in texts.items()}
        self.semantic_vectors = {key: self.ppmi.encode(text, self.tfidf) for key, text in texts.items()}

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
