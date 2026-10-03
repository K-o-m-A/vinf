"""Crawler v dvoch krokoch.

1. Abecedny zoznam kapiel: pre kazde pismeno sa stiahnu vsetky strany zoznamu
   (500 kapiel na stranu) do data/raw/band_list/. Uz stiahnute strany sa preskocia.
2. Kapely: pre kazdu kapelu zo zoznamu, ktora este nie je v data/visited.txt,
   sa stiahne hlavna stranka a diskografia a URL kapely sa pripise do visited.txt.
"""
import html
import json
import logging
import re
import string

import httpx

from . import config
from .fetcher import BlockedError, Fetcher

log = logging.getLogger("crawler")

LETTERS = list(string.ascii_uppercase) + ["NBR", "~"]
LIST_PAGE_SIZE = 500

BAND_LINK = re.compile(r"href='(https://www\.metal-archives\.com/bands/[^']+/\d+)'")
# id v URL nemusi sediet (stranka sa najde aj podla mena), skutocne id je v odkaze na diskografiu
BAND_ID_IN_PAGE = re.compile(r"/band/discography/id/(\d+)/tab/all")


def list_url(letter, start):
    return (f"{config.BASE_URL}/browse/ajax-letter/l/{letter}/json/1"
            f"?sEcho=1&iDisplayStart={start}&iDisplayLength={LIST_PAGE_SIZE}")


def list_path(letter, start):
    name = "other" if letter == "~" else letter
    return config.RAW_DIR / "band_list" / f"{name}_{start:06d}.json"


def save(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def download(fetcher, url):
    """Vrati text stranky, alebo None pri chybe (zaloguje sa a pokracuje sa dalej)."""
    if not fetcher.allowed(url):
        log.warning("robots.txt zakazuje %s", url)
        return None
    try:
        resp = fetcher.get(url)
    except httpx.TransportError as e:
        log.warning("chyba %s: %s", url, e)
        return None
    if resp.status_code != 200:
        log.warning("%s %s", resp.status_code, url)
        return None
    return resp.text


def crawl_band_list(fetcher):
    for letter in LETTERS:
        start, total = 0, 1
        while start < total:
            path = list_path(letter, start)
            if path.exists():
                text = path.read_text(encoding="utf-8")
            else:
                text = download(fetcher, list_url(letter, start))
                if text is None:
                    break
                save(path, text)
                log.info("zoznam %s od %d", letter, start)
            total = int(json.loads(text)["iTotalRecords"])
            start += LIST_PAGE_SIZE


def band_urls():
    """URL vsetkych kapiel zo stiahnutych stran zoznamu."""
    for path in sorted((config.RAW_DIR / "band_list").glob("*.json")):
        for row in json.loads(path.read_text(encoding="utf-8"))["aaData"]:
            link = BAND_LINK.search(row[0])
            if link:
                yield html.unescape(link.group(1))


def crawl_bands(fetcher, max_bands):
    visited = set()
    if config.VISITED_FILE.exists():
        visited = set(config.VISITED_FILE.read_text(encoding="utf-8").split())

    done = 0
    for url in band_urls():
        if done >= max_bands:
            break
        if url in visited:
            continue

        page = download(fetcher, url)
        if page is None:
            continue
        band_id = url.rsplit("/", 1)[1]
        save(config.RAW_DIR / "band" / f"{band_id}.html", page)

        m = BAND_ID_IN_PAGE.search(page)
        if m:
            disc = download(fetcher, f"{config.BASE_URL}/band/discography/id/{m.group(1)}/tab/all")
            if disc is not None:
                save(config.RAW_DIR / "band_disc" / f"{band_id}.html", disc)

        visited.add(url)
        with config.VISITED_FILE.open("a", encoding="utf-8") as f:
            f.write(url + "\n")
        done += 1
        log.info("[%d] %s", done, url)

    log.info("hotovo: %d kapiel v tomto behu, %d spolu", done, len(visited))


def crawl(max_bands):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher()
    fetcher.load_robots()
    log.info("robots.txt nacitany, pauza medzi poziadavkami %.1f s", fetcher.delay)
    try:
        crawl_band_list(fetcher)
        crawl_bands(fetcher, max_bands)
    except BlockedError as e:
        log.error("%s, crawl zastaveny", e)
    except KeyboardInterrupt:
        log.info("prerusene pouzivatelom")
