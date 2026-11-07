import argparse
import json
import logging
import time

from crawler import config
from . import evaluate, jobs

OUT_DIR = config.DATA_DIR / "spark"
DEFAULT_DUMP = config.DATA_DIR / "wiki" / "enwiki-latest-pages-articles.xml.bz2"
DEFAULT_GT = config.DATA_DIR / "wikidata" / "p1952_enwiki.csv"


def main():
    parser = argparse.ArgumentParser(description="Spark: extrakcia kapiel, wiki dump, join a vyhodnotenie")
    parser.add_argument("step", choices=["bands", "wiki", "join", "all", "eval"])
    parser.add_argument("--master", default=None, help="napr. local[4]; bez neho local[*] alebo --master zo spark-submit")
    parser.add_argument("--dump", default=str(DEFAULT_DUMP), help="wiki dump (.xml alebo .xml.bz2)")
    parser.add_argument("--bands", default=None, help="vstupne kapely pre join (JSON riadky)")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--gt", default=str(DEFAULT_GT), help="pary MA id -> clanok z Wikidat (CSV)")
    parser.add_argument("--partitions", type=int, default=64)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    out = jobs.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    spark = jobs.session(f"vinf-{args.step}", args.master)
    start = time.time()
    if args.step in ("bands", "all"):
        jobs.extract_bands(spark, config.RAW_DIR.resolve(), out / "bands", args.partitions)
    if args.step in ("wiki", "all"):
        jobs.parse_wiki(spark, str(jobs.Path(args.dump).resolve()), out)
    if args.step in ("join", "all"):
        bands = jobs.Path(args.bands).resolve() if args.bands else out / "bands"
        stats = jobs.join(spark, bands, out, out)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    if args.step == "eval":
        stats = evaluate.evaluate(spark, jobs.Path(args.gt).resolve(), out, out)
        print(json.dumps({k: v for k, v in stats.items() if not k.endswith("examples")}, indent=2))
    logging.getLogger("sparkjobs").info("hotovo za %.0f s", time.time() - start)
    spark.stop()


if __name__ == "__main__":
    main()
