"""Accesso minimo al database Supabase tramite l'API REST (PostgREST)."""
import os
import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

_HEADERS = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
# Le vecchie chiavi "service_role" sono JWT e vanno anche nell'header Authorization.
if not SUPABASE_KEY.startswith("sb_"):
    _HEADERS["Authorization"] = f"Bearer {SUPABASE_KEY}"


def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def select(table: str, query: str = "select=*") -> list:
    r = requests.get(f"{_url(table)}?{query}", headers=_HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def insert(table: str, rows, upsert_on: str | None = None, returning: bool = False):
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        return []
    headers = dict(_HEADERS)
    prefer = ["return=representation" if returning else "return=minimal"]
    url = _url(table)
    if upsert_on:
        prefer.append("resolution=merge-duplicates")
        url += f"?on_conflict={upsert_on}"
    headers["Prefer"] = ",".join(prefer)
    r = requests.post(url, headers=headers, json=rows, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"Supabase insert {table}: {r.status_code} {r.text[:300]}")
    return r.json() if returning else []


def update(table: str, match: str, values: dict):
    headers = dict(_HEADERS)
    headers["Prefer"] = "return=minimal"
    r = requests.patch(f"{_url(table)}?{match}", headers=headers, json=values, timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"Supabase update {table}: {r.status_code} {r.text[:300]}")


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
