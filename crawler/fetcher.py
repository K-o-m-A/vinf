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
        # HTTP/2: Cloudflare pred strankou vracia challenge kazdemu HTTP/1.1 klientovi
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
        if crawl_delay:
            self.delay = max(self.delay, float(crawl_delay))
        self._last_request = time.monotonic()

    def allowed(self, url):
        return self.robots.can_fetch(config.USER_AGENT, url)

    def _wait(self):
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
                if attempt == config.MAX_RETRIES:
                    raise
                time.sleep(config.BACKOFF_BASE * 2 ** attempt)
                continue

            if resp.status_code in config.RETRY_STATUSES and attempt < config.MAX_RETRIES:
                retry_after = resp.headers.get("Retry-After", "")
                wait = float(retry_after) if retry_after.isdigit() else config.BACKOFF_BASE * 2 ** attempt
                time.sleep(wait)
                continue

            if any(marker in resp.text[:5000] for marker in config.BLOCK_MARKERS):
                raise BlockedError(f"anti-bot challenge na {url}")
            return resp
