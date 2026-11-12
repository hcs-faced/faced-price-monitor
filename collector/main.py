"""Raccolta prezzi Face D — eseguito da GitHub Actions 2 volte a settimana.

Passi:
1. aggiorna i prezzi di riferimento da faced.com
2. legge le pagine prodotto dei siti (tabella product_urls)
3. legge le offerte Amazon.it via SP-API
4. salva tutto in observations e chiude il run con un riepilogo
"""
import os
import sys
import traceback

import db
import faced
import retailers
import bundles
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

        # Filtri per sito: il repository pubblico salta i siti che bloccano GitHub
        # (EXCLUDE_SITES), il PC dell'ufficio legge solo quelli (ONLY_SITES).
        only = {s.strip() for s in os.environ.get("ONLY_SITES", "").split(",") if s.strip()}
        exclude = {s.strip() for s in os.environ.get("EXCLUDE_SITES", "").split(",") if s.strip()}
        code_of = {s["id"]: s["code"] for s in sites.values()}

        if os.environ.get("SKIP_RRP") != "1":
            summary["rrp_updated"] = faced.refresh_rrp(products, log)

        urls = db.select(
            "product_urls",
            "select=*,products!inner(active,in_prototype,ean,variant)&active=eq.true"
            "&products.active=eq.true&products.in_prototype=eq.true",
        )
        urls = [u for u in urls
                if (not only or code_of.get(u["site_id"]) in only)
                and code_of.get(u["site_id"]) not in exclude]
        rows = retailers.collect(urls, run_id, log)
        summary["retailer_rows"] = len(rows)

        # Bundle creati dai rivenditori (kit senza EAN Face D)
        allowed = {c for c in sites if c != "amazon" and (not only or c in only) and c not in exclude}
        try:
            summary.update(bundles.collect(sites, allowed, run_id, log))
        except Exception as e:  # noqa: BLE001
            log.append(f"Bundle: {e}")

        if os.environ.get("SKIP_AMAZON") == "1":
            pass
        elif amazon.enabled() and "amazon" in sites:
            arows = amazon.collect(products, sites["amazon"]["id"], run_id, log)
            summary["amazon_rows"] = len(arows)
            rows += arows
            # bundle e altre inserzioni Face D create da venditori terzi
            try:
                known = {p["asin"] for p in db.select("products", "select=asin&asin=not.is.null")}
                summary["amazon_listings_found"] = amazon.discover_listings(known, sites["amazon"]["id"], log)
                summary["amazon_listings_read"] = amazon.collect_bundles(sites["amazon"]["id"], run_id, log)
            except Exception as e:  # noqa: BLE001
                log.append(f"Amazon inserzioni: {e}")
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
