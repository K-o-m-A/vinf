"""Nastavenia crawlera pre www.metal-archives.com."""
import os
from pathlib import Path

BASE_URL = "https://www.metal-archives.com"

# Identifikujeme sa poctivo ako crawler; kontakt sa da doplnit cez premennu prostredia.
CONTACT = os.environ.get("VINF_CONTACT", "FIIT STU VINF school project")
USER_AGENT = f"vinf-crawler/0.1 (+{CONTACT})"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

# (connect timeout, read timeout) v sekundach
TIMEOUT = (10, 30)

# robots.txt predpisuje Crawl-delay: 3, pouzije sa vacsia z hodnot.
MIN_DELAY = 3.0
JITTER = 1.0  # nahodne 0-1 s navyse, aby poziadavky nechodili v presnom rytme

MAX_RETRIES = 3
BACKOFF_BASE = 10.0  # 10 s, 20 s, 40 s
RETRY_STATUSES = {429, 500, 502, 503, 504}

# Nadpisy stranok, ktore znamenaju, ze nas zastavila anti-bot ochrana.
BLOCK_MARKERS = ("<title>Client Challenge", "<title>Just a moment", "<title>Attention Required")

DATA_DIR = Path(os.environ.get("VINF_DATA", "data"))
RAW_DIR = DATA_DIR / "raw"
VISITED_FILE = DATA_DIR / "visited.txt"  # URL uz stiahnutych kapiel, jedna na riadok
