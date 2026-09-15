"""Inverted BM25, exact vector scan, RRF and explainable second-stage scoring."""
import math
from collections import Counter, defaultdict
from .text import tokenize
from .vectors import cosine


def ranked(scores):
    return sorted(((key, value) for key, value in scores.items() if value > 0),
                  key=lambda item: (-item[1], item[0]))


class BM25:
    def __init__(self, documents, k1=1.5, b=0.75):
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError('Invalid BM25 parameters')
        self.k1, self.b = k1, b
        self.lengths, self.postings = {}, defaultdict(dict)
        for key, text in documents.items():
            words = tokenize(text)
            self.lengths[key] = len(words)
            for word, count in Counter(words).items():
                self.postings[word][key] = count
        self.n = len(documents)
        self.average = sum(self.lengths.values()) / self.n if self.n else 0

    def contributions(self, query):
        result = defaultdict(dict)
        for word in sorted(set(tokenize(query))):
            posting = self.postings.get(word, {})
            df = len(posting)
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for key, count in posting.items():
                denominator = count + self.k1 * (1 - self.b + self.b * self.lengths[key] / self.average)
                result[key][word] = idf * count * (self.k1 + 1) / denominator
        return dict(result)

    def search(self, query):
        return ranked({key: sum(terms.values()) for key, terms in self.contributions(query).items()})


def exact_scan(query_vector, vectors):
    return ranked({key: cosine(query_vector, vector) for key, vector in vectors.items()})


def rrf(*rankings, constant=60):
    if constant < 0:
        raise ValueError('RRF constant cannot be negative')
    scores = defaultdict(float)
    for ranking in rankings:
        seen, position = set(), 0
        for key, score in ranking:
            if score <= 0 or key in seen:
                continue
            seen.add(key)
            position += 1
            scores[key] += 1 / (constant + position)
    return ranked(scores)


def rerank_features(query, text, title, tfidf):
    tokens, document = tokenize(query), tokenize(text)
    terms = set(tokens)
    weights = {w: tfidf.idf.get(w, 1.0) for w in terms}
    denominator = sum(weights.values())
    coverage = sum(v for w, v in weights.items() if w in document) / denominator if denominator else 0
    title_coverage = len(terms & set(tokenize(title))) / len(terms) if terms else 0
    pairs = set(zip(tokens, tokens[1:]))
    adjacent = len(pairs & set(zip(document, document[1:]))) / len(pairs) if pairs else 0
    similarity = cosine(tfidf.encode(query), tfidf.encode(text))
    return dict(query_coverage=coverage, title_coverage=title_coverage,
                tfidf_cosine=similarity, adjacent_pairs=adjacent,
                score=0.45 * coverage + 0.25 * title_coverage + 0.20 * similarity + 0.10 * adjacent)
