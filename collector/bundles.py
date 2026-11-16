"""Bundle creati dai rivenditori: pagine che vendono prodotti Face D in kit o abbinati
ad altri prodotti, senza un EAN Face D (es. i kit composti da BENU).

- scoperta: legge la pagina marca Face D di BENU e registra le pagine senza codice Minsan;
- lettura: a ogni raccolta legge prezzo e disponibilità di ogni bundle e salva lo storico.
I bundle di faced.com (bundle virtuali venduti solo da Face D) non vengono monitorati.
"""
import re

import db
from common import polite_get, extract_offer

BENU_BRAND = "https://www.benufarma.it/marchi/faced"


KIT_WORDS = re.compile(r"(^|[^a-z])(kit|set|cofanetto|duo|trio|bipack|tripack|box)([^a-z]|$)", re.I)


def discover_benu(site_id: int, log: list) -> int:
    """Trova sulla pagina marca di BENU i kit creati da BENU: pagine senza codice Minsan
    con "kit" (o simili) nel nome o nell'indirizzo."""
    from bs4 import BeautifulSoup
    found: dict[str, str] = {}
    seen: set[str] = set()
    for page in range(1, 15):
        url = f"{BENU_BRAND}?page={page}"
        try:
            r = polite_get(url)
        except Exception as e:  # noqa: BLE001
            log.append(f"Bundle BENU, pagina marca {page}: {e}")
            break
        if r.status_code != 200:
            log.append(f"Bundle BENU, pagina marca {page}: HTTP {r.status_code}")
            break
        soup = BeautifulSoup(r.text, "html.parser")
        links: dict[str, str] = {}
        for a in soup.select('a[href*="/prodotti/"]'):
            path = re.sub(r"^https://www\.benufarma\.it", "", a.get("href", "")).split("?")[0].split("#")[0]
            text = " ".join(a.get_text(" ").split())
            if len(text) > len(links.get(path, "")):
                links[path] = text
        new_links = set(links) - seen
        if not new_links:  # pagina vuota o uguale alla precedente: fine elenco
            break
        seen |= new_links
        for path in new_links:
            if re.search(r"-p-\d{9}$", path):
                continue  # ha il Minsan: è un prodotto Face D a catalogo
            slug = path.rsplit("/", 1)[-1].replace("-", " ")
            if KIT_WORDS.search(slug) or KIT_WORDS.search(links[path]):
                found["https://www.benufarma.it" + path] = links[path]
    if found:
        db.insert("bundles", [{"site_id": site_id, "url": u} for u in sorted(found)], upsert_on="url")
    log.append(f"Bundle BENU: {len(seen)} pagine lette, {len(found)} kit")
    return len(found)


def collect(sites_by_code: dict, allowed_codes: set, run_id: int, log: list) -> dict:
    """Legge i bundle attivi dei siti consentiti in questa raccolta."""
    stats = {"bundles_found": 0, "bundles_read": 0}
    if "benu" in sites_by_code and "benu" in allowed_codes:
        try:
            stats["bundles_found"] = discover_benu(sites_by_code["benu"]["id"], log)
        except Exception as e:  # noqa: BLE001
            log.append(f"Bundle BENU, scoperta: {e}")
    ids = [sites_by_code[c]["id"] for c in allowed_codes if c in sites_by_code]
    if not ids:
        return stats
    bundles = db.select("bundles", f"select=*&active=eq.true&site_id=in.({','.join(map(str, ids))})")
    prices = []
    for b in bundles:
        try:
            r = polite_get(b["url"])
            if r.status_code == 404:
                db.update("bundles", f"id=eq.{b['id']}", {"active": False})
                continue
            if r.status_code != 200:
                log.append(f"Bundle {b['url']}: HTTP {r.status_code}")
                continue
            offer = extract_offer(r.text)
            values = {"title": (offer["title"] or "")[:300] or None, "price": offer["price"],
                      "list_price": offer["list_price"], "in_stock": offer["in_stock"],
                      "last_seen": db.now_iso()}
            db.update("bundles", f"id=eq.{b['id']}", values)
            if offer["price"] is not None:
                prices.append({"bundle_id": b["id"], "run_id": run_id, "price": offer["price"],
                               "list_price": offer["list_price"]})
            stats["bundles_read"] += 1
        except Exception as e:  # noqa: BLE001
            log.append(f"Bundle {b['url']}: {type(e).__name__}: {e}"[:300])
    if prices:
        db.insert("bundle_prices", prices)
    return stats
