"""Spustenie: python -m stats [--no-tokens]

Statistika stiahnutych dokumentov: pocet, velkost na disku, pocet relevantnych kapiel
a pocet tokenov (tiktoken, kodovanie o200k_base) v surovom HTML aj v extrahovanom texte.
Vysledok sa vypise ako markdown tabulka a ulozi do data/stats.json.
"""
import argparse
import functools
import json
from multiprocessing import Pool

from crawler import config
from indexer.index import band_text

ENCODING = "o200k_base"
GROUPS = {
    "band_list": "abecedny zoznam kapiel (JSON)",
    "band": "stranka kapely (HTML)",
    "band_disc": "diskografia kapely (HTML)",
}


@functools.cache
def encoder():
    import tiktoken
    return tiktoken.get_encoding(ENCODING)


def count_tokens(text):
    return len(encoder().encode_ordinary(text))


def file_tokens(path):
    return count_tokens(path.read_text(encoding="utf-8"))


def human(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def raw_stats(pool, tokens):
    rows = {}
    for group in GROUPS:
        paths = sorted((config.RAW_DIR / group).glob("*"))
        stats = [p.stat() for p in paths]
        rows[group] = {
            "files": len(paths),
            "bytes": sum(s.st_size for s in stats),
            "disk_bytes": sum(s.st_blocks * 512 for s in stats),  # skutocne obsadene bloky
            "tokens": sum(pool.imap_unordered(file_tokens, paths, chunksize=256)) if tokens else None,
        }
    return rows


def band_stats(text):
    band = json.loads(text)
    return {
        "has_releases": bool(band["releases"]),
        "has_members": any(band["members"].values()),
        "has_metal_genre": "metal" in band.get("genre", "").lower(),
        "releases": len(band["releases"]),
        "members": sum(len(g) for g in band["members"].values()),
    }, band_text(band)


def extracted_stats(pool, tokens):
    path = config.DATA_DIR / "extracted" / "bands.jsonl"
    out = {"bands": 0, "relevant": 0, "with_releases": 0, "with_members": 0, "metal_genre": 0,
           "releases": 0, "members": 0, "bytes": path.stat().st_size, "text_tokens": 0}
    texts = []
    with path.open(encoding="utf-8") as f:
        for s, text in pool.imap(band_stats, f, chunksize=500):
            out["bands"] += 1
            out["with_releases"] += s["has_releases"]
            out["with_members"] += s["has_members"]
            out["metal_genre"] += s["has_metal_genre"]
            # relevantna = ma diskografiu alebo zostavu, teda je co vyhladavat a zobrazit
            out["relevant"] += s["has_releases"] or s["has_members"]
            out["releases"] += s["releases"]
            out["members"] += s["members"]
            texts.append(text)
    if tokens:
        out["text_tokens"] = sum(pool.imap_unordered(count_tokens, texts, chunksize=500))
    return out


def main():
    parser = argparse.ArgumentParser(description="Statistika vycrawlovanych dokumentov")
    parser.add_argument("--no-tokens", action="store_true", help="nepocitaj tokeny (rychlejsie)")
    args = parser.parse_args()
    tokens = not args.no_tokens

    with Pool() as pool:
        raw = raw_stats(pool, tokens)
        ext = extracted_stats(pool, tokens)

    print("| Typ dokumentu | Pocet | Velkost | Na disku | Tokeny (tiktoken) |")
    print("|---|---:|---:|---:|---:|")
    for group, r in raw.items():
        tok = f"{r['tokens']:,}" if r["tokens"] is not None else "-"
        print(f"| {GROUPS[group]} | {r['files']:,} | {human(r['bytes'])} | {human(r['disk_bytes'])} | {tok} |")
    total = {k: sum(r[k] or 0 for r in raw.values()) for k in ("files", "bytes", "disk_bytes", "tokens")}
    print(f"| **spolu** | {total['files']:,} | {human(total['bytes'])} | {human(total['disk_bytes'])} | "
          f"{total['tokens']:,} |")
    print()
    print(f"- extrahovane kapely: {ext['bands']:,} ({human(ext['bytes'])} JSONL)")
    print(f"- relevantne (diskografia alebo zostava): {ext['relevant']:,} "
          f"({100 * ext['relevant'] / ext['bands']:.1f} %)")
    print(f"- s diskografiou: {ext['with_releases']:,}, so zostavou: {ext['with_members']:,}, "
          f"zaner obsahuje 'Metal': {ext['metal_genre']:,}")
    print(f"- vydania spolu: {ext['releases']:,}, clenovia spolu: {ext['members']:,}")
    print(f"- tokeny extrahovaneho textu (dokumenty indexu): {ext['text_tokens']:,}")

    out = config.DATA_DIR / "stats.json"
    out.write_text(json.dumps({"encoding": ENCODING, "raw": raw, "extracted": ext}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
