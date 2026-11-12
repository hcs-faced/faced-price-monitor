"""Funzioni comuni: richieste HTTP gentili, lettura prezzi, riconoscimento bundle."""
import json
import re
import time
import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}

_session = requests.Session()
_session.headers.update(HEADERS)
_last_call: dict[str, float] = {}


def polite_get(url: str, min_interval: float = 3.0, timeout: int = 30) -> requests.Response:
    """GET con pausa minima tra due richieste allo stesso dominio."""
    domain = re.sub(r"^https?://([^/]+).*$", r"\1", url)
    wait = min_interval - (time.time() - _last_call.get(domain, 0))
    if wait > 0:
        time.sleep(wait)
    _last_call[domain] = time.time()
    return _session.get(url, timeout=timeout, allow_redirects=True)


def to_price(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    s = str(value).strip().replace("\xa0", " ").replace("€", "").replace("EUR", "").strip()
    m = re.search(r"\d[\d.,]*", s)
    if not m:
        return None
    s = m.group(0)
    if "," in s and "." in s:  # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


BUNDLE_WORDS = re.compile(
    r"\b(kit|set|cofanetto|bundle|confezione doppia|bipack|bi-pack|tripack|duo|trio|"
    r"\d\s?pezzi|omaggio|in regalo)\b"
    r"|\b\d\s?x\s?\d|\bx\s?\d\b|\s\+\s",
    re.IGNORECASE,
)


def looks_like_bundle(title: str | None) -> bool:
    return bool(title and BUNDLE_WORDS.search(title))


def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                if "@graph" in item:
                    stack.extend(item["@graph"] if isinstance(item["@graph"], list) else [item["@graph"]])
                yield item


def extract_offer(html: str) -> dict:
    """Legge prezzo, prezzo barrato, disponibilità e titolo da una pagina prodotto.

    Ordine: dati strutturati JSON-LD (schema.org Product), poi meta tag
    (product:price:amount, og:price:amount, itemprop=price).
    """
    soup = BeautifulSoup(html, "html.parser")
    out = {"price": None, "list_price": None, "in_stock": None, "title": None, "gtin": None}

    for item in _iter_jsonld(soup):
        types = item.get("@type")
        types = types if isinstance(types, list) else [types]
        if "Product" not in types:
            continue
        out["title"] = out["title"] or item.get("name")
        out["gtin"] = out["gtin"] or item.get("gtin13") or item.get("gtin") or item.get("ean")
        offers = item.get("offers")
        offers = offers if isinstance(offers, list) else [offers] if offers else []
        for off in offers:
            if not isinstance(off, dict):
                continue
            price = off.get("price") or off.get("lowPrice")
            if price is None and isinstance(off.get("priceSpecification"), (dict, list)):
                specs = off["priceSpecification"]
                specs = specs if isinstance(specs, list) else [specs]
                for sp in specs:
                    p = to_price(sp.get("price"))
                    if sp.get("priceType", "").lower().endswith(("listprice", "strikethroughprice")):
                        out["list_price"] = p
                    elif p is not None and price is None:
                        price = p
            if price is not None and out["price"] is None:
                out["price"] = to_price(price)
                avail = str(off.get("availability", "")).lower()
                if avail:
                    out["in_stock"] = "instock" in avail or "limitedavailability" in avail
        if out["price"] is not None:
            break

    if out["price"] is None:
        for sel in [
            ("meta", {"property": "product:price:amount"}),
            ("meta", {"property": "og:price:amount"}),
            ("meta", {"itemprop": "price"}),
            (None, {"itemprop": "price"}),
        ]:
            tag = soup.find(sel[0], attrs=sel[1]) if sel[0] else soup.find(attrs=sel[1])
            if tag:
                out["price"] = to_price(tag.get("content") or tag.get_text())
                if out["price"] is not None:
                    break

    if out["title"] is None:
        og = soup.find("meta", attrs={"property": "og:title"})
        out["title"] = (og.get("content") if og else None) or (soup.title.string.strip() if soup.title and soup.title.string else None)

    return out
