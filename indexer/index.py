"""Vlastny invertovany index (TF) nad kapelami.

V postingoch je iba TF, IDF sa pocita pri dopyte z df, takze jeden index sluzi pre
vsetky metody IDF. Predpocitaju sa len normy dokumentov pre kosinusove skore.
"""
import bisect
import json
import math
import pickle
import re
import unicodedata
from array import array
from collections import Counter

TOKEN = re.compile(r"\w+")
STOPWORDS = frozenset("""
a an and are as at be but by for from has have he her his i in is it its of on or
she that the their they this to was were which who with you your our we not no
""".split())
POPULARITY = 0.15  # vaha poctu recenzii pri podobnych kapelach


def fold(text):
    """"Sarcófago" -> "sarcofago"."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def stem(t):
    """Jednoduche mnozne cislo: "vikings" -> "viking", ale "bass", "virus", "genesis" ostanu."""
    return t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")) else t


def tokenize(text):
    return [stem(t) for t in TOKEN.findall(fold(text)) if t not in STOPWORDS and not (len(t) == 1 and t.isalpha())]


def tf_weight(tf):
    return 1.0 + math.log10(tf)


def idf_classic(df, n):
    return math.log10(n / df)


def idf_smooth(df, n):
    # nikdy nie je 0, ani pri df = N
    return math.log10((1 + n) / (1 + df)) + 1.0


def idf_squared(df, n):
    # ako Lucene ClassicSimilarity, kde sa IDF uplatni na strane dopytu aj dokumentu
    return math.log10(n / df) ** 2


IDF_METHODS = {"classic": idf_classic, "smooth": idf_smooth, "squared": idf_squared}


def band_text(band):
    members = [m["name"] for group in band["members"].values() for m in group]
    parts = [
        band["name"], band.get("country") or "", band.get("location") or "",
        " ".join(band["genres"]), " ".join(band["themes"]), band.get("label") or "",
        band.get("status") or "", " ".join(members),
        " ".join(r["name"] for r in band["releases"]), band["comment"],
    ]
    return " ".join(parts)


def profile_text(band):
    """Zanre a temy pre hladanie podobnych kapiel, frazy oddelene "|". Temy su 2x,
    o com kapela spieva je pre podobnost dolezitejsie ako zaner."""
    themes = "|".join(band["themes"])
    return "|".join(["|".join(band["genres"]), themes, themes])


def profile_tokenize(text):
    """Slova + dvojice slov v ramci frazy: "World War I" -> world, war, world_war, war_i.
    Vdaka dvojiciam nie je "World War I" podobne "New World Order"."""
    terms = []
    for phrase in text.split("|"):
        words = [stem(t) for t in TOKEN.findall(fold(phrase))]
        terms += [t for t in words if t not in STOPWORDS and len(t) > 1]
        terms += [f"{a}_{b}" for a, b in zip(words, words[1:]) if not (a in STOPWORDS and b in STOPWORDS)]
    return terms


class Index:
    def __init__(self, text_fn=band_text, analyzer=tokenize):
        self.docs = []      # doc_id -> metadata kapely na vypis a filtre
        self.postings = {}  # term -> array('I') [doc, tf, doc, tf, ...]
        self.norms = {}     # metoda IDF -> array('d') normy dokumentov
        self.text_fn = text_fn
        self.analyzer = analyzer

    @property
    def n(self):
        return len(self.docs)

    def df(self, term):
        return len(self.postings.get(term, ())) // 2

    def add(self, doc_id, tokens):
        for term, tf in Counter(tokens).items():
            p = self.postings.get(term)
            if p is None:
                p = self.postings[term] = array("I")
            p.extend((doc_id, tf))

    def build(self, bands_file):
        offset = 0
        with open(bands_file, "rb") as f:
            for line in f:
                band = json.loads(line)
                self.docs.append({
                    "name": band["name"], "url": band["url"], "country": band.get("country"),
                    "genre": band.get("genre", ""), "genres": band["genres"],
                    "formed": band.get("formed"), "status": band.get("status"),
                    "reviews": sum(r["reviews"] for r in band["releases"]),
                    "offset": offset,  # pozicia riadku v bands.jsonl
                })
                self.add(len(self.docs) - 1, self.analyzer(self.text_fn(band)))
                offset += len(line)
        self.compute_norms()

    def compute_norms(self):
        for name, idf_fn in IDF_METHODS.items():
            sq = [0.0] * self.n
            for p in self.postings.values():
                idf = idf_fn(len(p) // 2, self.n)
                for i in range(0, len(p), 2):
                    sq[p[i]] += (tf_weight(p[i + 1]) * idf) ** 2
            self.norms[name] = array("d", (math.sqrt(x) for x in sq))

    def idf(self, term, method):
        df = self.df(term)
        return IDF_METHODS[method](df, self.n) if df else 0.0

    def tf(self, term, doc_id):
        p = self.postings.get(term)
        if not p:
            return 0
        docs = p[0::2]  # zoradene podla doc_id
        i = bisect.bisect_left(docs, doc_id)
        return p[2 * i + 1] if i < len(docs) and docs[i] == doc_id else 0

    def query_weights(self, query, method):
        return {t: tf_weight(tf) * self.idf(t, method) for t, tf in Counter(self.analyzer(query)).items()}

    def rank(self, query, method="classic"):
        """Kosinusova podobnost dopytu a dokumentov, [(skore, doc_id)] od najlepsieho."""
        scores = {}
        q_norm = 0.0
        for term, w_q in self.query_weights(query, method).items():
            p = self.postings.get(term)
            if not p:
                continue
            q_norm += w_q ** 2
            idf = self.idf(term, method)
            for i in range(0, len(p), 2):
                scores[p[i]] = scores.get(p[i], 0.0) + w_q * tf_weight(p[i + 1]) * idf
        norms = self.norms[method]
        q_norm = math.sqrt(q_norm) or 1.0
        return sorted(((s / (norms[d] * q_norm), d) for d, s in scores.items() if norms[d] > 0), reverse=True)

    def search(self, query, method="classic", k=10):
        return [(score, self.docs[d]) for score, d in self.rank(query, method)[:k]]

    def explain(self, query, doc_id, method):
        """[(term, tf, df, idf, prispevok ku skore)] a norma dokumentu."""
        weights = self.query_weights(query, method)
        q_norm = math.sqrt(sum(w ** 2 for w in weights.values())) or 1.0
        d_norm = self.norms[method][doc_id] or 1.0
        rows = []
        for term, w_q in weights.items():
            tf = self.tf(term, doc_id)
            idf = self.idf(term, method)
            w_d = tf_weight(tf) * idf if tf else 0.0
            rows.append((term, tf, self.df(term), idf, w_q * w_d / (q_norm * d_norm)))
        return rows, d_norm

    def docs_with_all(self, terms):
        """Prienik postingov, od najkratsieho zoznamu."""
        lists = sorted((self.postings.get(t) for t in set(terms)), key=lambda p: len(p) if p else 0)
        if not lists or not lists[0]:
            return set()
        docs = set(lists[0][0::2])
        for p in lists[1:]:
            docs &= set(p[0::2])
        return docs

    def similar(self, query, method="classic"):
        """Podobne kapely podla profilu, [(skore, pokrytie, doc_id)].

        Pokrytie je podiel vahy profilu (sucet w^2), ktory ma aj kandidat. Kosinus sme
        skusali najprv, ale trestal kapely za temy navyse: 1914 (World War I, Trench
        warfare, Gas attacks, ...) bola k Kanonenfieber az 6778.
        """
        weights = self.query_weights(query, method)
        total = sum(w * w for w in weights.values()) or 1.0
        cover = {}
        for term, w in weights.items():
            p = self.postings.get(term, ())
            for i in range(0, len(p), 2):
                cover[p[i]] = cover.get(p[i], 0.0) + w * w
        results = []
        for d, c in cover.items():
            c /= total
            results.append((c * (1 + POPULARITY * math.log10(1 + self.docs[d]["reviews"])), c, d))
        return sorted(results, reverse=True)

    def explain_similar(self, query, doc_id, method):
        """[(term, podiel vahy v profile, ma ho kandidat?)]."""
        weights = self.query_weights(query, method)
        total = sum(w * w for w in weights.values()) or 1.0
        rows = [(t, w * w / total, self.tf(t, doc_id) > 0) for t, w in weights.items()]
        return sorted(rows, key=lambda r: -r[1])

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.__dict__, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path):
        index = cls()
        with open(path, "rb") as f:
            index.__dict__.update(pickle.load(f))
        return index


def build_members(bands_file):
    """Meno bez diakritiky -> [(id umelca, meno, doc_id, zostava, nastroje)]."""
    members = {}
    with open(bands_file, "rb") as f:
        for doc_id, line in enumerate(f):
            band = json.loads(line)
            for group, people in band["members"].items():
                for m in people:
                    roles = ", ".join(f"{r} ({y})" if y else r for r, y in m["roles"])
                    key = " ".join(fold(m["name"]).split())
                    members.setdefault(key, []).append((m["id"], m["name"], doc_id, group, roles))
    return members
