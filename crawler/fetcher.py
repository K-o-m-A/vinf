"""HTTP klient: hlavicky, robots.txt, rate limiting, timeouty a opakovania."""
import random
import time
import urllib.robotparser

import httpx

from . import config


class BlockedError(Exception):
    """Server vratil anti-bot challenge namiesto obsahu, dalej necrawlujeme."""


class Fetcher:
    def __init__(self):
        self.session = httpx.Client(
            http2=True,
            headers=config.HEADERS,
            timeout=httpx.Timeout(config.TIMEOUT[1], connect=config.TIMEOUT[0]),
        )
        self.robots = urllib.robotparser.RobotFileParser()
        self.delay = config.MIN_DELAY
        self._last_request = 0.0

    def load_robots(self):
        resp = self.session.get(f"{config.BASE_URL}/robots.txt")
        resp.raise_for_status()
        self.robots.parse(resp.text.splitlines())
        crawl_delay = self.robots.crawl_delay(config.USER_AGENT)
        if crawl_delay:  # robots.txt moze predpisat dlhsiu pauzu (Crawl-delay), pouzije sa vacsia z nich
            self.delay = max(self.delay, float(crawl_delay))
        self._last_request = time.monotonic()

    def allowed(self, url):
        return self.robots.can_fetch(config.USER_AGENT, url)

    def _wait(self):
        # Pauza medzi poziadavkami: 3 s (Crawl-delay) + nahodne 0-1 s, aby poziadavky
        # nechodili v presnom rytme. Meria sa od zaciatku poslednej poziadavky, takze cas
        # stahovania sa do pauzy zaratava a crawler nie je zbytocne pomalsi.
        pause = self.delay + random.uniform(0, config.JITTER)
        remaining = self._last_request + pause - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()

    def get(self, url):
        """Stiahne URL. Vrati httpx.Response (aj pre 404) alebo vyhodi vynimku."""
        for attempt in range(config.MAX_RETRIES + 1):
            self._wait()
            try:
                resp = self.session.get(url)
            except httpx.TransportError:
                # Chyba spojenia alebo timeout: pocka 10, 20, 40 s (exponencialny backoff)
                # a skusi znova. Po poslednom pokuse chybu posunie volajucemu (download).
                if attempt == config.MAX_RETRIES:
                    raise
                time.sleep(config.BACKOFF_BASE * 2 ** attempt)
                continue

            # 429 (prilis vela poziadaviek) a 5xx (chyba servera) su docasne: pocka podla
            # hlavicky Retry-After, ak ju server poslal, inak 10, 20, 40 s, a skusi znova.
            if resp.status_code in config.RETRY_STATUSES and attempt < config.MAX_RETRIES:
                retry_after = resp.headers.get("Retry-After", "")
                wait = float(retry_after) if retry_after.isdigit() else config.BACKOFF_BASE * 2 ** attempt
                time.sleep(wait)
                continue

            # Ochrana pred botmi (Cloudflare) vrati namiesto obsahu stranku s vyzvou.
            # Taku stranku neulozime a crawl zastavime, aby sme server dalej nezatazovali.
            if any(marker in resp.text[:5000] for marker in config.BLOCK_MARKERS):
                raise BlockedError(f"anti-bot challenge na {url}")
            return resp
