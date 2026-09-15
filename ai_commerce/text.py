"""Small English tokenizer; offsets always refer to original whitespace words."""
import re
from collections import Counter
from dataclasses import dataclass

STOP = frozenset('a an the is are of to for and in with'.split())


def tokenize(text):
    text = re.sub(r'\bwi[\s\u2010-\u2015-]*fi\b', 'wifi', text.lower())
    return [w for w in re.findall(r'[a-z0-9]+(?:-[a-z0-9]+)*', text) if w not in STOP]


@dataclass(frozen=True)
class Chunk:
    id: str
    source_id: str
    product_id: str
    title: str
    category: str
    start: int
    end: int
    text: str


def chunk_source(source_id, product_id, title, category, text, size=36, overlap=8):
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError('Require 0 <= overlap < size')
    words, result = text.split(), []
    for start in range(0, len(words), size - overlap):
        end = min(len(words), start + size)
        result.append(Chunk(f'{source_id}:{start}:{end}', source_id, product_id,
                            title, category, start, end, ' '.join(words[start:end])))
        if end == len(words):
            break
    return result


def vocabulary(documents, limit=500):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Vocabulary limit must be an integer from 1 to 1000')
    counts = Counter(w for d in documents for w in tokenize(d))
    return tuple(sorted(counts, key=lambda w: (-counts[w], w))[:limit])
