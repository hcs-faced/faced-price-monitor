"""Raccolta prezzi Face D — eseguito da GitHub Actions 2 volte a settimana.

Passi:
1. aggiorna i prezzi di riferimento da faced.com
2. legge le pagine prodotto dei siti (tabella product_urls)
3. legge le offerte Amazon.it via SP-API
4. salva tutto in observations e chiude il run con un riepilogo
"""
import sys
import traceback

import db
import faced
import retailers
import amazon


def main() -> int:
    log: list[str] = []
    run = db.insert("runs", {"status": "running"}, returning=True)[0]
    run_id = run["id"]
    summary = {"retailer_rows": 0, "amazon_rows": 0, "prices_found": 0, "errors": 0}
    status = "ok"
    try:
        products = db.select("products", "select=*&active=eq.true&in_prototype=eq.true&order=id")
        sites = {s["code"]: s for s in db.select("sites")}

        summary["rrp_updated"] = faced.refresh_rrp(products, log)

        urls = db.select(
            "product_urls",
            "select=*,products!inner(active,in_prototype)&active=eq.true"
            "&products.active=eq.true&products.in_prototype=eq.true",
        )
        rows = retailers.collect(urls, run_id, log)
        summary["retailer_rows"] = len(rows)

        if amazon.enabled() and "amazon" in sites:
            arows = amazon.collect(products, sites["amazon"]["id"], run_id, log)
            summary["amazon_rows"] = len(arows)
            rows += arows
        else:
            log.append("Amazon saltato: credenziali SP-API non configurate")

        for i in range(0, len(rows), 200):
            db.insert("observations", rows[i:i + 200])

        summary["prices_found"] = sum(1 for r in rows if r.get("price") is not None)
        summary["errors"] = sum(1 for r in rows if r.get("error"))
        if summary["errors"]:
            status = "partial"
    except Exception:  # noqa: BLE001
        status = "error"
        log.append(traceback.format_exc()[-1500:])

    summary["log"] = log[-200:]
    db.update("runs", f"id=eq.{run_id}", {"status": status, "finished_at": db.now_iso(), "summary": summary})
    # Il repository è pubblico: nei log di GitHub solo i totali.
    # Il dettaglio (prezzi, venditori, errori) resta nel database, visibile solo con login.
    print(f"Run {run_id}: {status}")
    print({k: v for k, v in summary.items() if k != "log"})
    return 1 if status == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
