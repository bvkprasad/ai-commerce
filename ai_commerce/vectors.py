"""Sparse TF-IDF and PPMI vectors, using explicit dictionary arithmetic."""
import math
from collections import Counter, defaultdict
from .text import tokenize


def dot(a, b):
    return sum(value * b.get(key, 0.0) for key, value in a.items())


def norm(vector):
    return math.sqrt(dot(vector, vector))


def normalize(vector):
    length = norm(vector)
    return {key: value / length for key, value in vector.items()} if length else {}


def cosine(a, b):
    denominator = norm(a) * norm(b)
    return dot(a, b) / denominator if denominator else 0.0


class TFIDF:
    def __init__(self, documents, words):
        frequencies = Counter()
        for document in documents:
            frequencies.update(set(tokenize(document)))
        self.idf = {w: 1 + math.log((len(documents) + 1) / (frequencies[w] + 1))
                    for w in words}

    def weights(self, text):
        return {w: (1 + math.log(count)) * self.idf[w]
                for w, count in Counter(tokenize(text)).items() if w in self.idf}

    def encode(self, text):
        return normalize(self.weights(text))


class PPMI:
    def __init__(self, sources, words, window=2):
        if type(window) is not int or window < 1:
            raise ValueError('Window must be a positive integer')
        allowed, pairs, rows, columns = set(words), Counter(), Counter(), Counter()
        for source in sources:
            tokens = tokenize(source)
            for i, word in enumerate(tokens):
                if word not in allowed:
                    continue
                for j in range(max(0, i - window), min(len(tokens), i + window + 1)):
                    context = tokens[j]
                    if i != j and context in allowed:
                        pairs[word, context] += 1
                        rows[word] += 1
                        columns[context] += 1
        total = sum(pairs.values())
        vectors = defaultdict(dict)
        for (word, context), count in pairs.items():
            value = max(0.0, math.log(count * total / (rows[word] * columns[context])))
            if value:
                vectors[word][context] = value
        self.words = {w: normalize(vector) for w, vector in vectors.items()}

    def encode(self, text, tfidf):
        vector = defaultdict(float)
        for word, weight in tfidf.weights(text).items():
            for context, value in self.words.get(word, {}).items():
                vector[context] += weight * value
        return normalize(dict(vector))
