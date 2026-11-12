"""Legge i prezzi dalle pagine prodotto dei siti (tabella product_urls)."""
from common import polite_get, extract_offer, looks_like_bundle


def collect(product_urls: list[dict], run_id: int, log: list) -> list[dict]:
    rows = []
    for pu in product_urls:
        row = {
            "run_id": run_id,
            "product_id": pu["product_id"],
            "site_id": pu["site_id"],
            "seller_id": "",
            "url": pu["url"],
        }
        try:
            r = polite_get(pu["url"])
            if r.status_code != 200:
                row["error"] = f"HTTP {r.status_code}"
            else:
                offer = extract_offer(r.text)
                row.update(
                    title=(offer["title"] or "")[:300] or None,
                    price=offer["price"],
                    list_price=offer["list_price"],
                    in_stock=offer["in_stock"],
                    possible_bundle=looks_like_bundle(offer["title"]),
                )
                if offer["price"] is None:
                    row["error"] = "prezzo non trovato nella pagina"
        except Exception as e:  # noqa: BLE001
            row["error"] = f"{type(e).__name__}: {e}"[:300]
        if row.get("error"):
            log.append(f"{pu['url']}: {row['error']}")
        rows.append(row)
    return rows
