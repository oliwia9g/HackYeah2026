"""Pobiera z Overpass daty ostatniej edycji obiektow OSM (out meta) dla obszaru demo.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date

import requests

from pipeline.common import load_config, raw_dir

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
ROUNDS = 3   # tyle razy przechodzimy cala liste serwerow (z coraz dluzsza przerwa)
HEADERS = {"User-Agent": "HackYeah2026-krakow-bez-barier/0.1 (hackathon prototype)"}


def build_query(cfg: dict) -> str:
    b = cfg["bbox"]
    bb = f'{b["south"]},{b["west"]},{b["north"]},{b["east"]}'
    parts = []
    for key, val in cfg["osm"]["poi_tags"].items():
        if val is True:
            parts.append(f'nwr["{key}"]({bb});')
        elif isinstance(val, list):
            parts.append(f'nwr["{key}"~"^({"|".join(val)})$"]({bb});')
    return f'[out:json][timeout:180];({"".join(parts)});out meta;'


def fetch(query: str) -> dict:
    last_err = None
    for rnd in range(ROUNDS):
        for url in ENDPOINTS:
            try:
                print(f"pytam {url} ...")
                r = requests.post(url, data={"data": query}, headers=HEADERS, timeout=240)
                if r.status_code == 200:
                    return r.json()
                last_err = f"{url}: HTTP {r.status_code}"
                print("  blad:", last_err)
            except (requests.RequestException, ValueError) as e:
                last_err = f"{url}: {e}"
                print("  blad:", last_err)
            time.sleep(3)
        if rnd < ROUNDS - 1:
            wait = 20 * (rnd + 1)
            print(f"wszystkie serwery zajete, czekam {wait} s i probuje ponownie...")
            time.sleep(wait)
    print("Nie udalo sie pobrac danych z Overpass:", last_err)
    print("To NIE blokuje reszty: pipeline.fetch_osm dziala tez bez osm_meta.json (daty tylko z check_date).")
    sys.exit(1)


def main() -> None:
    cfg = load_config()
    data = fetch(build_query(cfg))
    elements = {}
    for e in data.get("elements", []):
        if e.get("timestamp"):
            elements[f'{e["type"]}/{e["id"]}'] = {"timestamp": e["timestamp"], "version": e.get("version")}
    out = raw_dir(cfg) / "osm_meta.json"
    out.write_text(json.dumps({"fetched_at": date.today().isoformat(), "elements": elements}), "utf-8")

    years = sorted(int(v["timestamp"][:4]) for v in elements.values())
    print(f"zapisano {out} ({len(elements)} obiektow z data edycji)")
    if years:
        recent = sum(1 for y in years if y >= date.today().year - 1)
        print(f"  najstarsza edycja: {years[0]}, najnowsza: {years[-1]}, "
              f"edytowane w ostatnich 2 latach: {recent} ({100 * recent / len(years):.0f}%)")
    print("Teraz uruchom ponownie: python -m pipeline.fetch_osm")


if __name__ == "__main__":
    main()
