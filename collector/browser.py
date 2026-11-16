"""Lettura delle pagine con un vero browser, per i siti che bloccano anche curl_cffi (es. Sephora).

Si attiva solo se la variabile BROWSER_SITES contiene il dominio (es. "sephora.it") e se
Playwright è installato (solo sul PC dell'ufficio). Usa Chrome installato sul PC; se non
lo trova usa il Chromium di Playwright. Il browser resta aperto per tutta la raccolta.
"""
import atexit
import os

_SITES = [s.strip().lower() for s in os.environ.get("BROWSER_SITES", "").split(",") if s.strip()]
_state: dict = {}


class Page:
    """Risposta minima compatibile con quella di requests (status_code, text)."""

    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


def wanted(domain: str) -> bool:
    return any(domain.lower().endswith(s) for s in _SITES)


def _start():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    # finestra "normale" (il runner è un servizio: non si vede comunque) e senza i segnali
    # che indicano un browser comandato da un programma
    headless = os.environ.get("BROWSER_HEADLESS", "0") == "1"
    args = ["--disable-blink-features=AutomationControlled", "--lang=it-IT"]
    try:
        br = pw.chromium.launch(channel="chrome", headless=headless, args=args)
    except Exception:  # noqa: BLE001  Chrome non trovato: Chromium di Playwright
        br = pw.chromium.launch(headless=headless, args=args)
    ctx = br.new_context(locale="it-IT", timezone_id="Europe/Rome",
                         viewport={"width": 1366, "height": 900})
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = ctx.new_page()
    _state.update(pw=pw, br=br, page=page, warm=set())
    atexit.register(close)


def get(url: str, timeout: int = 45) -> Page:
    if "page" not in _state:
        _start()
    page = _state["page"]
    scheme, _, domain = url.split("/")[:3]
    if domain not in _state["warm"]:
        # prima visita alla home: il sito imposta i cookie come per un visitatore normale
        try:
            page.goto(f"{scheme}//{domain}/", timeout=timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
        except Exception:  # noqa: BLE001
            pass
        _state["warm"].add(domain)
    resp = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    status = resp.status if resp else 0
    if status == 403:
        # alcuni siti fanno un controllo con script e poi lasciano passare: riprova una volta
        page.wait_for_timeout(6000)
        resp = page.reload(timeout=timeout * 1000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        status = resp.status if resp else status
    return Page(status, page.content())


def close():
    try:
        if "br" in _state:
            _state["br"].close()
        if "pw" in _state:
            _state["pw"].stop()
    except Exception:  # noqa: BLE001
        pass
    _state.clear()
