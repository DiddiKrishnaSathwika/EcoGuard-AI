"""Small dependency-free BM25 index (works offline, no API key)."""
import math
import re
from collections import Counter

_STOP = set("the a an of and or to in for on by with is are be as at from that this it its any no not may must shall".split())


def tokenize(text):
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOP and len(t) > 1]


class BM25Index:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.ids = [d[0] for d in docs]
        self.tokens = [tokenize(d[1]) for d in docs]
        self.k1, self.b = k1, b
        self.avg = (sum(len(t) for t in self.tokens) / len(self.tokens)) if self.tokens else 0
        df = Counter()
        for toks in self.tokens:
            df.update(set(toks))
        n = len(self.tokens)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def search(self, query, top_k=10):
        q = tokenize(query)
        scored = []
        for doc_id, toks in zip(self.ids, self.tokens):
            tf = Counter(toks)
            score = 0.0
            for term in set(q):
                if term in tf:
                    f = tf[term]
                    score += self.idf.get(term, 0) * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * len(toks) / (self.avg or 1)))
            scored.append((doc_id, score))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:top_k]
