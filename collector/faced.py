"""Aggiorna il prezzo di riferimento leggendolo dal sito faced.com (dati pubblici Shopify)."""
import db
from common import polite_get, _session

STORE = "https://faced.com"


def refresh_rrp(products: list[dict], log: list) -> int:
    """Per ogni prodotto legge /products/<handle>.js e aggiorna rrp.

    Regola concordata: riferimento = prezzo su faced.com; se c'è un prezzo
    barrato più alto, vale il prezzo barrato.
    """
    updated = 0
    by_handle: dict[str, list[dict]] = {}
    for p in products:
        if p.get("handle"):
            by_handle.setdefault(p["handle"], []).append(p)

    # faced.com mostra prezzi e valuta in base al paese del visitatore: i server di
    # GitHub sono negli USA, quindi si forza il mercato Italia (EUR) e si controlla.
    _session.cookies.set("localization", "IT", domain=".faced.com")
    _session.cookies.set("cart_currency", "EUR", domain=".faced.com")
    try:
        currency = polite_get(f"{STORE}/cart.js", min_interval=1.0).json().get("currency")
    except Exception as e:  # noqa: BLE001
        currency = None
        log.append(f"faced.com: valuta non verificabile ({e})")
    if currency != "EUR":
        log.append(f"faced.com: valuta {currency} invece di EUR, prezzi di riferimento non aggiornati")
        return 0

    for handle, items in by_handle.items():
        try:
            r = polite_get(f"{STORE}/products/{handle}.js", min_interval=1.0)
            r.raise_for_status()
            variants = r.json().get("variants", [])
        except Exception as e:  # noqa: BLE001
            log.append(f"faced.com {handle}: {e}")
            continue
        for p in items:
            v = next((v for v in variants if (v.get("barcode") or "") == p["ean"]), None) \
                or next((v for v in variants if (v.get("sku") or "") == (p.get("sku") or "")), None)
            if not v:
                log.append(f"faced.com {handle}: variante {p['ean']} non trovata")
                continue
            price = (v.get("price") or 0) / 100
            compare = (v.get("compare_at_price") or 0) / 100
            rrp = round(max(price, compare), 2)
            old = float(p.get("rrp") or 0)
            if old and abs(rrp - old) / old > 0.30:
                log.append(f"faced.com {p['ean']}: variazione sospetta {old} -> {rrp}, non aggiornato")
                continue
            if rrp and abs(rrp - old) >= 0.01:
                db.update("products", f"id=eq.{p['id']}", {"rrp": rrp, "updated_at": db.now_iso()})
                log.append(f"Prezzo di riferimento {p['ean']}: {p.get('rrp')} -> {rrp}")
                p["rrp"] = rrp
                updated += 1
    return updated
