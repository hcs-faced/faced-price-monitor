"""Nuovi venditori: negozi che vendono prodotti Face D sui comparatori di prezzo.

- Trovaprezzi: pagine "Face D" per categoria (viso, make-up, corpo, solari, ...), filtrate sul marchio.
- Idealo: ricerca per linea di prodotto, poi le offerte di ogni scheda prodotto Face D.

Ogni negozio finisce nella tabella `merchants` (una riga per negozio, da approvare in dashboard)
e ogni offerta in `market_offers`, abbinata quando possibile a un prodotto del catalogo.
"""
import re
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup

import db
from common import polite_get, to_price

BRAND = re.compile(r"face\s*-?\s*d\b|\bfaced\b|hcs\s*s\.?r\.?l", re.I)
NOT_BRAND = re.compile(r"too\s*faced|north\s*face", re.I)

TP_BASE = "https://www.trovaprezzi.it"
TP_CATEGORIES = ["prodotti-viso", "make-up", "integratori-coadiuvanti", "prodotti-corpo",
                 "prodotti-solari", "set-regalo-bellezza", "mani-piedi"]

ID_BASE = "https://www.idealo.it"
ID_QUERIES = ["pure plump", "pure lift", "pure glowy", "pure drink", "pure peel", "pure clear", "pure c",
              "pure energy", "instant rich", "instant bright", "instant lift", "retinolo", "hydrasun",
              "hydraoil", "hydraglow", "cc cream", "contorno occhi", "contorno labbra", "crema corpo",
              "siero corpo", "scrub", "micellare", "detergente", "maschera", "nutrilip", "stick",
              "mascara", "terra", "eau de toilette", "kit", "cofanetto", "collagene", "vitamina c",
              "hydragel", "super siero", "patch", "crema mani", "spf"]

# negozi che corrispondono a siti già monitorati: il nome normalizzato deve INIZIARE così
# (es. "efarma" sì, "semprefarmacia" no). Amazon Marketplace = venditori terzi, da verificare.
KNOWN = [("redcare", "redcare"), ("amazonmarketplace", "amazon-mp"), ("amazon", "amazon"), ("benu", "benu"),
         ("efarma", "atida"), ("atida", "atida"), ("pinalli", "pinalli"), ("sephora", "sephora"),
         ("douglas", "douglas"), ("faced", "faced"), ("hcsitaly", "faced")]

STOP = {"face", "faced", "con", "per", "di", "da", "del", "della", "the", "and", "ml", "pz", "x", "e", "a",
        "in", "al", "il", "la", "le", "spf", "viso"}


def name_key(name: str) -> str:
    s = name.lower()
    s = re.sub(r"\s+-\s+negozio.*$", "", s)
    s = re.sub(r"^(www\.)", "", s)
    s = re.sub(r"\.(it|com|eu|net|shop|store)\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _tokens(text: str) -> set[str]:
    t = (text or "").lower().replace("à", "a").replace("è", "e")
    t = re.sub(r"(\d+)\s*(ml|g|pz)\b", r"\1\2", t)
    t = re.sub(r"spf\s*(\d+)", r"spf\1", t)
    words = re.findall(r"[a-z0-9]+", t)
    return {w for w in words if w not in STOP and (len(w) >= 3 or w.isdigit())}


def match_product(title: str, products: list[dict], price: float | None = None) -> int | None:
    """Abbina il titolo di un'offerta a un prodotto del catalogo (parole del nome tutte presenti).
    Scarta i prodotti con prezzo incoerente (es. stick singolo contro confezione): fuori 35%-250%."""
    tt = _tokens(title)
    best, best_score = None, 0.0
    for p in products:
        pt = _tokens(p["name"])
        if not pt:
            continue
        rrp = p.get("rrp")
        if price and rrp and not (float(rrp) * 0.35 <= price <= float(rrp) * 2.5):
            continue
        score = len(pt & tt) / len(pt)
        if p.get("variant"):
            vt = _tokens(p["variant"])
            if vt and vt <= tt:
                score += 0.1
            elif vt:
                score -= 0.1
        score += len(pt) * 0.001  # a parità, il nome più specifico
        if score > best_score:
            best, best_score = p["id"], score
    return best if best_score >= 0.8 else None


def trovaprezzi(log: list) -> list[dict]:
    offers = []
    for cat in TP_CATEGORIES:
        first_seen_title = None
        for page in range(1, 41):
            url = f"{TP_BASE}/prezzo_{cat}_face_d.aspx" + (f"?page={page}" if page > 1 else "")
            try:
                r = polite_get(url, min_interval=2.0)
                if r.status_code in (403, 429):  # a volte blocca per un momento: riprova una volta
                    time.sleep(20)
                    r = polite_get(url, min_interval=2.0)
            except Exception as e:  # noqa: BLE001
                log.append(f"Trovaprezzi {cat} p{page}: {type(e).__name__}")
                break
            if r.status_code != 200:
                log.append(f"Trovaprezzi {cat} p{page}: HTTP {r.status_code}")
                break
            items = BeautifulSoup(r.text, "html.parser").select("li.listing_item")
            if not items:
                break
            first = items[0].select_one(".item_name")
            first = first.get_text(strip=True) if first else ""
            if page > 1 and first == first_seen_title:
                break
            if page == 1:
                first_seen_title = first
            for it in items:
                name = it.select_one(".item_name")
                desc = it.select_one(".item_desc")
                merch = it.select_one(".merchant_name")
                price = it.select_one(".item_basic_price")
                title = name.get_text(" ", strip=True) if name else ""
                text = title + " " + (desc.get_text(" ", strip=True) if desc else "")
                if not merch or not BRAND.search(text) or NOT_BRAND.search(text):
                    continue
                offers.append({"source": "trovaprezzi", "merchant": merch.get_text(strip=True),
                               "title": title[:300], "price": to_price(price.get_text() if price else None),
                               "category": cat})
            if len(items) < 20:
                break
    return offers


def idealo(log: list) -> list[dict]:
    pages: set[str] = set()
    for q in ID_QUERIES:
        try:
            r = polite_get(f"{ID_BASE}/risultati.html?q=face+d+{q.replace(' ', '+')}", min_interval=2.0)
        except Exception as e:  # noqa: BLE001
            log.append(f"Idealo ricerca '{q}': {type(e).__name__}")
            continue
        if r.status_code != 200:
            log.append(f"Idealo ricerca '{q}': HTTP {r.status_code}")
            if r.status_code in (403, 429):
                break
            continue
        for href in re.findall(r'href="((?:https://www\.idealo\.it)?/confronta-prezzi/\d+/[^"?#]+)', r.text):
            slug = href.rsplit("/", 1)[-1]
            if re.match(r"(face-?d|faced)-", slug) and not NOT_BRAND.search(slug.replace("-", " ")):
                pages.add(href if href.startswith("http") else ID_BASE + href)
    offers = []
    for url in sorted(pages):
        try:
            r = polite_get(url, min_interval=2.0)
        except Exception as e:  # noqa: BLE001
            log.append(f"Idealo {url}: {type(e).__name__}")
            continue
        if r.status_code != 200:
            log.append(f"Idealo {url}: HTTP {r.status_code}")
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        h1 = soup.find("h1")
        product_title = h1.get_text(" ", strip=True) if h1 else ""
        for li in soup.select("li.productOffers-listItem"):
            shop = li.select_one("[data-shop-name]")
            if not shop:
                continue
            ttl = li.select_one("[class*=productOffers-listItemTitle]")
            title = ttl.get_text(" ", strip=True) if ttl else product_title
            m = re.search(r"€\s*([\d.]+,\d{2})", li.get_text(" ", strip=True))
            offers.append({"source": "idealo", "merchant": shop["data-shop-name"],
                           "title": (title or product_title)[:300],
                           "price": to_price(m.group(1)) if m else None, "category": "idealo"})
    log.append(f"Idealo: {len(pages)} schede prodotto Face D")
    return offers


def collect(run_id: int, log: list) -> dict:
    offers = []
    for name, fn in (("Trovaprezzi", trovaprezzi), ("Idealo", idealo)):
        try:
            got = fn(log)
            log.append(f"{name}: {len(got)} offerte Face D")
            offers += got
        except Exception as e:  # noqa: BLE001
            log.append(f"{name}: {type(e).__name__}: {e}"[:300])
    # una sola offerta per negozio + titolo + prezzo (la stessa compare in più categorie)
    seen, unique = set(), []
    for o in offers:
        k = (o["source"], name_key(o["merchant"]), o["title"], o["price"])
        if k not in seen:
            seen.add(k)
            unique.append(o)
    if not unique:
        return {"market_offers": 0, "merchants_new": 0}

    now = datetime.now(timezone.utc).isoformat()
    sites = {s["code"]: s for s in db.select("sites", "select=code,authorized")}
    existing = {m["name_key"]: m for m in db.select("merchants", "select=id,name_key,sources")}
    by_key: dict[str, dict] = {}
    for o in unique:
        k = name_key(o["merchant"])
        if not k:
            continue
        rec = by_key.setdefault(k, {"name": re.sub(r"\s+-\s+Negozio.*$", "", o["merchant"]).strip(),
                                    "sources": set()})
        rec["sources"].add(o["source"])
    new_rows, upd_rows = [], []
    for k, rec in by_key.items():
        site = next((code for pre, code in KNOWN if k.startswith(pre)), None)
        if site == "amazon-mp":
            site, auth_mp = "amazon", True
        else:
            auth_mp = False
        srcs = sorted(rec["sources"] | set((existing.get(k) or {}).get("sources") or []))
        if k in existing:
            upd_rows.append({"name_key": k, "name": rec["name"], "sources": srcs, "last_seen": now})
        else:
            auth = True if site == "faced" else (None if auth_mp or not site else sites.get(site, {}).get("authorized"))
            new_rows.append({"name_key": k, "name": rec["name"], "sources": srcs, "site_code": site,
                             "authorized": auth, "first_seen": now, "last_seen": now})
    if new_rows:
        db.insert("merchants", new_rows)
    if upd_rows:
        db.insert("merchants", upd_rows, upsert_on="name_key")
    ids = {m["name_key"]: m["id"] for m in db.select("merchants", "select=id,name_key")}

    products = db.select("products", "select=id,name,variant,rrp&active=eq.true")
    rows = []
    for o in unique:
        k = name_key(o["merchant"])
        if k not in ids:
            continue
        rows.append({"run_id": run_id, "source": o["source"], "merchant_id": ids[k], "title": o["title"],
                     "price": o["price"], "category": o["category"],
                     "product_id": match_product(o["title"], products, o["price"])})
    for i in range(0, len(rows), 200):
        db.insert("market_offers", rows[i:i + 200])
    return {"market_offers": len(rows), "merchants_new": len(new_rows),
            "market_matched": sum(1 for r in rows if r["product_id"])}
