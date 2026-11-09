"""Site falso para testar coletores sem rede."""
import json

from imoveis_pg.coleta.http import PoliteClient, Response


def page_html(props, page=1, pages=1, total=None):
    data = {"props": {"pageProps": {"properties": props,
                                    "totalProperties": total if total is not None else len(props),
                                    "pageInfo": {"page": page, "take": 20, "total": pages}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


class FakeSite:
    def __init__(self, pages, robots="User-agent: *\nAllow: /\n"):
        self.pages, self.robots, self.calls = pages, robots, []

    def __call__(self, url, headers, timeout):
        self.calls.append(url)
        assert "imoveis-pg" in headers["User-Agent"]
        if url.endswith("/robots.txt"):
            return Response(200, self.robots.encode()) if self.robots is not None else Response(404, b"")
        if url in self.pages:
            value = self.pages[url]
            if isinstance(value, Response):
                return value
            return Response(200, value if isinstance(value, bytes) else value.encode())
        return Response(404, b"")


def client(site, **kwargs):
    kwargs.setdefault("sleep", lambda s: None)
    return PoliteClient(opener=site, **kwargs)
