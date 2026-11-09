"""Cliente HTTP de coleta: respeita robots.txt, espaça requisições e guarda cache bruto."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "imoveis-pg/0.1 (projeto academico IFPR; coleta de anuncios publicos)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class ColetaError(RuntimeError):
    """Falha de coleta que impede gerar uma base confiável."""


@dataclass
class Response:
    status: int
    body: bytes


Opener = Callable[[str, dict, float], Response]


def urllib_opener(url: str, headers: dict, timeout: float) -> Response:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Response(response.status, response.read())
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.read() or b"")


class PoliteClient:
    """Busca páginas públicas com intervalo mínimo e cache em disco.

    Páginas já presentes no cache não geram nova requisição, o que torna a
    coleta reproduzível e permite reprocessar sem acessar o site novamente.
    """

    def __init__(self, *, cache_dir: Path | None = None, delay: float = 3.0,
                 user_agent: str = USER_AGENT, offline: bool = False, retries: int = 3,
                 timeout: float = 30.0, opener: Opener = urllib_opener,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.delay, self.user_agent, self.offline = delay, user_agent, offline
        self.retries, self.timeout = retries, timeout
        self._opener, self._sleep, self._clock = opener, sleep, clock
        self._last_request: float | None = None
        self._robots: dict[str, RobotFileParser] = {}
        self.requests_made = 0
        self.cache_hits = 0

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html")

    def _request(self, url: str) -> Response:
        if self._last_request is not None:
            wait = self.delay - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._clock()
        self.requests_made += 1
        return self._opener(url, {"User-Agent": self.user_agent}, self.timeout)

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = RobotFileParser()
            response = self._request(origin + "/robots.txt")
            if response.status in (401, 403):
                parser.disallow_all = True
            elif response.status >= 400:
                parser.allow_all = True
            else:
                parser.parse(response.body.decode("utf-8", "replace").splitlines())
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(self.user_agent, url)

    def get(self, url: str) -> str:
        cached = self._cache_path(url)
        if cached and cached.exists():
            self.cache_hits += 1
            return cached.read_text(encoding="utf-8")
        if self.offline:
            raise ColetaError(f"Modo offline e página ausente do cache: {url}")
        if not self._allowed(url):
            raise ColetaError(f"robots.txt não permite coletar {url}")
        for attempt in range(self.retries + 1):
            response = self._request(url)
            if response.status == 200:
                break
            if response.status not in RETRY_STATUS or attempt == self.retries:
                raise ColetaError(f"HTTP {response.status} ao buscar {url}")
            self._sleep(self.delay * 2 ** (attempt + 1))
        text = response.body.decode("utf-8", "replace")
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(text, encoding="utf-8")
            entry = {"url": url, "arquivo": cached.name,
                     "coletado_em": datetime.now(timezone.utc).isoformat()}
            with (cached.parent / "index.jsonl").open("a", encoding="utf-8") as index:
                index.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return text
