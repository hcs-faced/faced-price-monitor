"""Funzioni comuni: richieste HTTP gentili, lettura prezzi, riconoscimento bundle."""
import json
import os
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


VARIANT_WORDS = {
    "chiara": ["light", "chiara", "clair"],
    "scura": ["dark", "scura", "fonc"],
    "light": ["light", "clair", "chiara"],
    "medium": ["medium"],
    "caramel": ["caramel"],
    "30 ml": ["30ml", "30 ml"],
    "50 ml": ["50ml", "50 ml"],
}


def _offer_of(item: dict) -> dict:
    """Prezzo, prezzo barrato e disponibilità dalla prima offerta valida di un Product."""
    res = {"price": None, "list_price": None, "in_stock": None}
    offers = item.get("offers")
    offers = offers if isinstance(offers, list) else [offers] if offers else []
    for off in offers:
        if not isinstance(off, dict):
            continue
        price = off.get("price") or off.get("lowPrice")
        specs = off.get("priceSpecification")
        if isinstance(specs, (dict, list)):
            for sp in specs if isinstance(specs, list) else [specs]:
                p = to_price(sp.get("price"))
                if str(sp.get("priceType", "")).lower().endswith(("listprice", "strikethroughprice")):
                    res["list_price"] = p
                elif p is not None and price is None:
                    price = p
        if price is not None:
            res["price"] = to_price(price)
            avail = str(off.get("availability", "")).lower()
            if avail:
                res["in_stock"] = "instock" in avail or "limitedavailability" in avail
            break
    return res


def _products_in(soup: BeautifulSoup) -> list[dict]:
    """Tutti i Product del JSON-LD, comprese le varianti dentro un ProductGroup."""
    out = []
    for item in _iter_jsonld(soup):
        types = item.get("@type")
        types = types if isinstance(types, list) else [types]
        if "ProductGroup" in types:
            variants = item.get("hasVariant") or []
            for v in variants if isinstance(variants, list) else [variants]:
                if isinstance(v, dict):
                    v.setdefault("_group_name", item.get("name"))
                    out.append(v)
        elif "Product" in types:
            out.append(item)
    return out


def _pick(products: list[dict], ean: str | None, variant: str | None) -> dict | None:
    with_price = [p for p in products if _offer_of(p)["price"] is not None]
    if not with_price:
        return None
    if ean:
        for p in with_price:
            if str(p.get("gtin13") or p.get("gtin") or p.get("ean") or "") == ean:
                return p
    if variant and len(with_price) > 1:
        words = VARIANT_WORDS.get(variant.strip().lower(), [variant.strip().lower()])
        names = [str(p.get("name") or "").lower().replace(" ml", "ml") for p in with_price]
        prefix = os.path.commonprefix(names)  # es. "fast anti-dark circles eye cream "
        for w in words:
            for p, name in zip(with_price, names):
                if w.replace(" ml", "ml") in name[len(prefix):]:
                    return p
    return with_price[0]


def extract_offer(html: str, ean: str | None = None, variant: str | None = None) -> dict:
    """Legge prezzo, prezzo barrato, disponibilità e titolo da una pagina prodotto.

    Ordine: dati strutturati JSON-LD (schema.org Product / ProductGroup con varianti,
    scegliendo la variante con lo stesso EAN o con il nome della variante), poi meta tag
    (product:price:amount, og:price:amount, itemprop=price).
    """
    soup = BeautifulSoup(html, "html.parser")
    out = {"price": None, "list_price": None, "in_stock": None, "title": None, "gtin": None, "matched_ean": False}

    chosen = _pick(_products_in(soup), ean, variant)
    if chosen:
        out.update(_offer_of(chosen))
        out["title"] = chosen.get("name") or chosen.get("_group_name")
        out["gtin"] = chosen.get("gtin13") or chosen.get("gtin") or chosen.get("ean")
        out["matched_ean"] = bool(ean and str(out["gtin"] or "") == ean)

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
