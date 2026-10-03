"""Uruchamia caly pipeline danych jednym poleceniem (kolejnosc ma znaczenie) i na koncu pokazuje, co sie udalo.

    python -m pipeline.run_all                      # Krakow (config.yaml)
    CITY_CONFIG=cities/wroclaw.yaml python -m pipeline.run_all     # inne miasto (patrz cities/TEMPLATE.yaml)
    python -m pipeline.run_all --with-meta          # dodatkowo daty edycji z Overpass (wolne, czesto 429/504)
    python -m pipeline.run_all --skip dem --skip gtfs

Kroki sa niezalezne od strony awarii: gdy jeden sie nie uda, reszta idzie dalej, a podsumowanie mowi, co powtorzyc.
Kazdy krok mozna uruchomic osobno tym samym poleceniem co dotad (python -m pipeline.<nazwa>).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

# (nazwa, modul, wymaga_wczesniejszego_kroku, opis)
STEPS = [
    ("meta", "pipeline.fetch_overpass_meta", None, "daty ostatniej edycji obiektow OSM (opcjonalny, --with-meta)"),
    ("osm", "pipeline.fetch_osm", None, "siec piesza, miejsca, przejscia, fakty z proweniencja"),
    ("dem", "pipeline.fetch_dem", "osm", "nachylenia z NMT (GUGiK)"),
    ("addresses", "pipeline.fetch_addresses", None, "adresy do wyszukiwania po nazwie ulicy"),
    ("gtfs", "pipeline.fetch_gtfs", None, "przystanki i rozklad jazdy"),
    ("sources", "pipeline.make_sources_doc", None, "rejestr zrodel (SOURCES.md)"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", action="append", default=[], choices=[s[0] for s in STEPS], help="pomin krok (mozna kilka razy)")
    ap.add_argument("--with-meta", action="store_true", help="uruchom tez fetch_overpass_meta (domyslnie pomijany)")
    args = ap.parse_args()
    skip = set(args.skip)
    if not args.with_meta:
        skip.add("meta")

    results: dict[str, str] = {}
    t_all = time.time()
    for name, module, needs, desc in STEPS:
        if name in skip:
            results[name] = "pominięty"
            continue
        if needs and results.get(needs) not in ("ok", "pominięty"):
            results[name] = f"pominięty (wymaga kroku {needs}, który się nie udał)"
            continue
        print(f"\n===== [{name}] {desc} =====", flush=True)
        t0 = time.time()
        code = subprocess.call([sys.executable, "-m", module])
        results[name] = ("ok" if code == 0 else f"BŁĄD (kod {code})") + f" [{time.time() - t0:.0f} s]"
    print("\n===== PODSUMOWANIE =====")
    for name, res in results.items():
        print(f"  {name:10} {res}")
    failed = [n for n, r in results.items() if r.startswith("BŁĄD")]
    print(f"\nCzas całkowity: {time.time() - t_all:.0f} s")
    if failed:
        print("Powtórz nieudane kroki osobno, np.: python -m pipeline." + {
            "meta": "fetch_overpass_meta", "osm": "fetch_osm", "dem": "fetch_dem", "addresses": "fetch_addresses",
            "gtfs": "fetch_gtfs", "sources": "make_sources_doc"}[failed[0]])
        sys.exit(1)
    print("Gotowe. Uruchom API: uvicorn api.main:create_app --factory --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
