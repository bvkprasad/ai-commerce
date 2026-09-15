"""Tiny, explicitly hand-authored product relevance judgments; no quality claims."""
import math

JUDGMENTS = [
    ('washing machine built-in wifi', {'wash-connect': 3, 'wash-addon': 1, 'wash-basic': 1}),
    ('air conditioner app control', {'ac-connect': 3, 'ac-bridge': 2, 'ac-local': 1}),
    ('dock two extended displays', {'dock-d': 3, 'dock-c': 3, 'dock-b': 2, 'dock-a': 1}),
]


def metrics(ranking, judgments, k=3):
    if k < 1:
        raise ValueError('k must be positive')
    unique = list(dict.fromkeys(ranking))
    relevant = {key for key, grade in judgments.items() if grade > 0}
    recall = len(set(unique[:k]) & relevant) / len(relevant) if relevant else 0
    mrr = next((1 / i for i, key in enumerate(unique, 1) if key in relevant), 0)
    dcg = sum((2 ** judgments.get(key, 0) - 1) / math.log2(i + 1) for i, key in enumerate(unique[:k], 1))
    ideal = sum((2 ** grade - 1) / math.log2(i + 1) for i, grade in
                enumerate(sorted(judgments.values(), reverse=True)[:k], 1))
    return {'recall_at_k': recall, 'mrr': mrr, 'ndcg_at_k': dcg / ideal if ideal else 0}


def evaluate(catalog):
    report = {}
    for method in ('bm25', 'tfidf', 'ppmi', 'hybrid', 'reranked'):
        rows = []
        for query, judgments in JUDGMENTS:
            ranking = [x['product_id'] for x in catalog.search(query, method=method, limit=100)]
            rows.append({'query': query, **metrics(ranking, judgments)})
        report[method] = {'queries': rows, 'mean': {key: sum(r[key] for r in rows) / len(rows)
                            for key in ('recall_at_k', 'mrr', 'ndcg_at_k')}}
    return {'warning': 'Three synthetic judgments only; not held-out evidence of general quality.', 'results': report}
