"""Spustenie: python -m extractor [--limit N]

Prejde vsetky data/raw/band/*.html (+ diskografie) a zapise jednu kapelu na riadok
do data/extracted/bands.jsonl.
"""
import argparse
import json
import logging
from multiprocessing import Pool

from crawler import config
from .extract import extract_band, extract_discography

log = logging.getLogger("extractor")
OUT_FILE = config.DATA_DIR / "extracted" / "bands.jsonl"


def process(path):
    # Spracuje jednu kapelu: z jej stranky vytiahne udaje a z diskografie (ak existuje) vydania.
    # Vysledok je jeden slovnik = jeden riadok v bands.jsonl. Ak subor nie je stranka kapely,
    # vrati None a kapela sa zarata medzi neuspesne.
    band = extract_band(path.read_text(encoding="utf-8"))
    if band is None:
        return None
    disc = config.RAW_DIR / "band_disc" / path.name
    band["file_id"] = path.stem
    band["releases"] = extract_discography(disc.read_text(encoding="utf-8")) if disc.exists() else []
    return band


def main():
    parser = argparse.ArgumentParser(description="Extrakcia entit zo stiahnutych stranok")
    parser.add_argument("--limit", type=int, default=None, help="spracuj len prvych N stranok")
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    paths = sorted((config.RAW_DIR / "band").glob("*.html"))[:args.limit]
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    done = failed = 0
    # Kapely sa spracuju paralelne na vsetkych jadrach (multiprocessing.Pool), kazda nezavisle.
    # imap vracia vysledky v rovnakom poradi ako subory, takze bands.jsonl ma stale rovnake poradie.
    with Pool(args.workers) as pool, OUT_FILE.open("w", encoding="utf-8") as out:
        for band in pool.imap(process, paths, chunksize=200):
            if band is None:
                failed += 1
                continue
            out.write(json.dumps(band, ensure_ascii=False) + "\n")
            done += 1
            if done % 20000 == 0:
                log.info("%d kapiel", done)
    log.info("hotovo: %d kapiel do %s, %d stranok sa nepodarilo spracovat", done, OUT_FILE, failed)


if __name__ == "__main__":
    main()
