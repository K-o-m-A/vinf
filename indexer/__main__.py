"""Spustenie:
  python -m indexer                               # interaktivne vyhladavanie
  python -m indexer build                         # index z data/extracted/bands.jsonl
  python -m indexer search "swedish death metal"  # --idf classic|smooth, -k 10
  python -m indexer compare "q1" "q2" "q3"        # porovnanie metod IDF
"""
import argparse
import itertools
import logging
import pickle
import time

from crawler import config
from .cli import Shell
from .index import IDF_METHODS, Index, build_members, profile_text, profile_tokenize, tokenize

log = logging.getLogger("indexer")
BANDS_FILE = config.DATA_DIR / "extracted" / "bands.jsonl"
INDEX_FILE = config.DATA_DIR / "index" / "index.pkl"
PROFILE_FILE = config.DATA_DIR / "index" / "profile.pkl"
MEMBERS_FILE = config.DATA_DIR / "index" / "members.pkl"


def build():
    start = time.time()
    index = Index()
    index.build(BANDS_FILE)
    index.save(INDEX_FILE)
    postings = sum(len(p) // 2 for p in index.postings.values())
    log.info("index: %d dokumentov, %d termov, %d postingov, %.0f s -> %s",
             index.n, len(index.postings), postings, time.time() - start, INDEX_FILE)

    start = time.time()
    profile = Index(text_fn=profile_text, analyzer=profile_tokenize)
    profile.build(BANDS_FILE)
    profile.save(PROFILE_FILE)
    log.info("profilovy index (zanre + temy): %d termov, %.0f s -> %s",
             len(profile.postings), time.time() - start, PROFILE_FILE)

    start = time.time()
    members = build_members(BANDS_FILE)
    with open(MEMBERS_FILE, "wb") as f:
        pickle.dump(members, f, protocol=pickle.HIGHEST_PROTOCOL)
    log.info("index clenov: %d mien, %.0f s -> %s", len(members), time.time() - start, MEMBERS_FILE)


def search(index, query, method, k):
    print(f"\n### {query!r}  [idf={method}]")
    for rank, (score, doc) in enumerate(index.search(query, method, k), 1):
        print(f"{rank:3}. {score:.4f}  {doc['name']} ({doc['country']}, {doc['formed']}) - {doc['genre']}")


def compare(index, queries, k):
    """Markdown tabulky do reportu: df a idf termov, potom top k kazdej metody vedla seba."""
    for query in queries:
        print(f"\n## {query}\n")
        print("| term | df | " + " | ".join(f"idf {m}" for m in IDF_METHODS) + " |")
        print("|---|---|" + "---|" * len(IDF_METHODS))
        for term in dict.fromkeys(tokenize(query)):
            print(f"| {term} | {index.df(term)} | "
                  + " | ".join(f"{index.idf(term, m):.3f}" for m in IDF_METHODS) + " |")

        results = {m: index.search(query, m, k) for m in IDF_METHODS}
        print("\n| # | " + " | ".join(IDF_METHODS) + " |")
        print("|---|" + "---|" * len(IDF_METHODS))
        for i in range(k):
            cells = []
            for m in IDF_METHODS:
                if i < len(results[m]):
                    score, doc = results[m][i]
                    cells.append(f"{doc['name']} ({doc['country']}) {score:.3f}")
                else:
                    cells.append("")
            print(f"| {i + 1} | " + " | ".join(cells) + " |")

        print()
        urls = {m: {d["url"] for _, d in r} for m, r in results.items()}
        for a, b in itertools.combinations(IDF_METHODS, 2):
            print(f"- spolocne vo top {k}: {a} vs {b} = {len(urls[a] & urls[b])}")


def main():
    parser = argparse.ArgumentParser(description="Vlastny invertovany index nad kapelami")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("shell", help="interaktivne vyhladavanie (predvolene)")
    sub.add_parser("build")
    s = sub.add_parser("search")
    s.add_argument("query", nargs="+")
    s.add_argument("--idf", choices=list(IDF_METHODS) + ["all"], default="all")
    s.add_argument("-k", type=int, default=10)
    c = sub.add_parser("compare")
    c.add_argument("queries", nargs="+")
    c.add_argument("-k", type=int, default=10)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.cmd == "build":
        build()
        return
    if not INDEX_FILE.exists():
        parser.error(f"index {INDEX_FILE} neexistuje, najprv spusti: python -m indexer build")
    index = Index.load(INDEX_FILE)
    if args.cmd in (None, "shell"):
        Shell(index, BANDS_FILE, PROFILE_FILE, MEMBERS_FILE).run()
    elif args.cmd == "search":
        for m in IDF_METHODS if args.idf == "all" else [args.idf]:
            search(index, " ".join(args.query), m, args.k)
    else:
        compare(index, args.queries, args.k)


if __name__ == "__main__":
    main()
