"""Amazon.it tramite le API ufficiali Selling Partner (SP-API).

- Catalog Items API: trova l'ASIN a partire dall'EAN.
- Product Pricing API (getItemOffers): offerte dei venditori su quell'ASIN
  (prezzo, spedizione, FBA, Buy Box). Restituisce fino a 20 offerte.
"""
import os
import re
import time
import requests

import db

ENDPOINT = "https://sellingpartnerapi-eu.amazon.com"
MARKETPLACE_IT = "APJ6JRA9NG5V4"
_token = {"value": None, "exp": 0.0}


def enabled() -> bool:
    return all(os.environ.get(k) for k in ("SPAPI_CLIENT_ID", "SPAPI_CLIENT_SECRET", "SPAPI_REFRESH_TOKEN"))


def _access_token() -> str:
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    r = requests.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": os.environ["SPAPI_REFRESH_TOKEN"],
            "client_id": os.environ["SPAPI_CLIENT_ID"],
            "client_secret": os.environ["SPAPI_CLIENT_SECRET"],
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    _token.update(value=data["access_token"], exp=time.time() + int(data.get("expires_in", 3600)))
    return _token["value"]


def _get(path: str, params: dict, min_interval: float) -> dict:
    for attempt in range(4):
        time.sleep(min_interval)
        r = requests.get(
            ENDPOINT + path,
            params=params,
            headers={"x-amz-access-token": _access_token(), "accept": "application/json"},
            timeout=30,
        )
        if r.status_code == 429:  # troppe richieste: aspetta e riprova
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code >= 300:
            raise RuntimeError(f"SP-API {path}: {r.status_code} {r.text[:300]}")
        return r.json()
    raise RuntimeError(f"SP-API {path}: troppi tentativi (429)")


def find_asin(ean: str) -> str | None:
    data = _get(
        "/catalog/2022-04-01/items",
        {"identifiers": ean, "identifiersType": "EAN", "marketplaceIds": MARKETPLACE_IT, "includedData": "summaries"},
        min_interval=0.6,
    )
    items = data.get("items") or []
    return items[0]["asin"] if items else None


def _amount(obj) -> float | None:
    if isinstance(obj, dict) and obj.get("Amount") is not None:
        return round(float(obj["Amount"]), 2)
    return None


def collect(products: list[dict], amazon_site_id: int, run_id: int, log: list) -> list[dict]:
    rows = []
    seen_sellers: set[str] = set()
    for p in products:
        asin = p.get("asin")
        if not asin:
            try:
                asin = find_asin(p["ean"])
            except Exception as e:  # noqa: BLE001
                log.append(f"Amazon ricerca ASIN {p['ean']}: {e}")
                continue
            if not asin:
                log.append(f"Amazon: nessun ASIN per EAN {p['ean']}")
                continue
            db.update("products", f"id=eq.{p['id']}", {"asin": asin})
            p["asin"] = asin

        url = f"https://www.amazon.it/dp/{asin}"
        try:
            data = _get(
                f"/products/pricing/v0/items/{asin}/offers",
                {"MarketplaceId": MARKETPLACE_IT, "ItemCondition": "New"},
                min_interval=2.1,  # limite Amazon: 0,5 richieste al secondo
            )
        except Exception as e:  # noqa: BLE001
            log.append(f"Amazon offerte {asin}: {e}")
            rows.append({"run_id": run_id, "product_id": p["id"], "site_id": amazon_site_id,
                         "seller_id": "", "url": url, "error": str(e)[:300]})
            continue

        offers = (data.get("payload") or {}).get("Offers") or []
        if not offers:
            rows.append({"run_id": run_id, "product_id": p["id"], "site_id": amazon_site_id,
                         "seller_id": "", "url": url, "in_stock": False,
                         "error": "nessuna offerta attiva"})
        for off in offers:
            seller = off.get("SellerId") or ""
            seen_sellers.add(seller)
            rows.append({
                "run_id": run_id,
                "product_id": p["id"],
                "site_id": amazon_site_id,
                "seller_id": seller,
                "url": url,
                "price": _amount(off.get("ListingPrice")),
                "shipping": _amount(off.get("Shipping")),
                "in_stock": True,
                "is_buybox": bool(off.get("IsBuyBoxWinner")),
                "is_fba": bool(off.get("IsFulfilledByAmazon")),
            })

    # registra i venditori nuovi (autorizzato = da verificare) e aggiorna "ultimo visto"
    if seen_sellers:
        db.insert(
            "sellers",
            [{"site_id": amazon_site_id, "seller_id": s, "last_seen": db.now_iso()} for s in seen_sellers if s],
            upsert_on="site_id,seller_id",
        )
    return rows


# ---------- Bundle e altre inserzioni Face D su Amazon ----------
BUNDLE_WORDS = re.compile(r"\b(kit|set|cofanetto|confezione|bundle|pacco|pack|duo|trio|\d\s?x|x\s?\d|\d\s?pz|\d\s?pezzi)\b|\+", re.I)


def discover_listings(known_asins: set, amazon_site_id: int, log: list, max_pages: int = 10) -> int:
    """Cerca nel catalogo Amazon.it le inserzioni Face D con ASIN diverso dai nostri prodotti:
    bundle creati da venditori terzi (kit, confezioni multiple, abbinamenti) o altre inserzioni."""
    found = []
    token = None
    for _ in range(max_pages):
        params = {"keywords": "Face D", "marketplaceIds": MARKETPLACE_IT, "includedData": "summaries", "pageSize": 20}
        if token:
            params["pageToken"] = token
        try:
            data = _get("/catalog/2022-04-01/items", params, min_interval=0.6)
        except Exception as e:  # noqa: BLE001
            log.append(f"Amazon ricerca inserzioni: {e}")
            break
        for it in data.get("items") or []:
            asin = it.get("asin")
            summ = (it.get("summaries") or [{}])[0]
            brand = (summ.get("brand") or summ.get("brandName") or "").lower().replace(" ", "")
            title = summ.get("itemName") or ""
            if not asin or asin in known_asins or brand not in ("faced", "face-d"):
                continue
            found.append({"site_id": amazon_site_id, "url": f"https://www.amazon.it/dp/{asin}",
                          "title": title[:300] or None,
                          "kind": "bundle" if BUNDLE_WORDS.search(title) else "altra inserzione"})
        token = (data.get("pagination") or {}).get("nextToken")
        if not token:
            break
    if found:
        db.insert("bundles", found, upsert_on="url")
    return len(found)


def collect_bundles(amazon_site_id: int, run_id: int, log: list) -> int:
    """Prezzo più basso e numero di offerte per ogni inserzione Amazon registrata come bundle."""
    items = db.select("bundles", f"select=*&active=eq.true&site_id=eq.{amazon_site_id}")
    prices, read = [], 0
    for b in items:
        asin = b["url"].rstrip("/").split("/")[-1]
        try:
            data = _get(f"/products/pricing/v0/items/{asin}/offers",
                        {"MarketplaceId": MARKETPLACE_IT, "ItemCondition": "New"}, min_interval=2.1)
        except Exception as e:  # noqa: BLE001
            log.append(f"Amazon inserzione {asin}: {e}"[:300])
            continue
        offers = (data.get("payload") or {}).get("Offers") or []
        listed = [_amount(o.get("ListingPrice")) for o in offers]
        listed = [p for p in listed if p is not None]
        values = {"last_seen": db.now_iso(), "in_stock": bool(listed),
                  "price": min(listed) if listed else None, "sellers": len(offers)}
        db.update("bundles", f"id=eq.{b['id']}", values)
        if listed:
            prices.append({"bundle_id": b["id"], "run_id": run_id, "price": min(listed)})
        read += 1
    if prices:
        db.insert("bundle_prices", prices)
    return read
