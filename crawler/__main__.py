"""Spustenie: python -m crawler --max-bands 100

Kapely v data/visited.txt sa preskocia, crawl teda pokracuje tam, kde skoncil.
"""
import argparse
import logging

from .crawler import crawl


def main():
    parser = argparse.ArgumentParser(description="Crawler kapiel z www.metal-archives.com")
    parser.add_argument("--max-bands", type=int, default=100,
                        help="kolko kapiel (stranka + diskografia) stiahnut v tomto behu")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    crawl(args.max_bands)


if __name__ == "__main__":
    main()
