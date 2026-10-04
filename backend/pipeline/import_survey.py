"""Import obserwacji z nalotu dronem (albo kontroli terenowej) z pliku CSV.

    python -m pipeline.import_survey obserwacje.csv --survey nalot-2026-12

Kolumny CSV: lon, lat, type, text   (opcjonalnie: survey_id - wtedy --survey nie jest potrzebne)
type: zastawiony_chodnik | chodnik_zablokowany | remont | nawierzchnia_zniszczona | waski_chodnik | przeszkoda
Wspolrzedne w WGS84 (lon/lat). Punkty poza obszarem demo sa odrzucane. Obserwacje danego nalotu zastepuja wczesniejsze
tego samego survey_id (ponowny import jest bezpieczny). Id nalotu musi istniec w surveys.yaml.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date

from engine.surveys import OBS_TYPES
from pipeline.common import inside_aoi, load_config, raw_dir


def clean(s: str, n: int = 200) -> str:
    return re.sub(r"[\x00-\x1f<>]", "", re.sub(r"<[^>]*>", "", s or "")).strip()[:n]


def parse_rows(rows, cfg, default_survey):
    ok, bad = [], []
    for i, r in enumerate(rows, 2):   # wiersz 1 = naglowek
        try:
            lon, lat = float(str(r.get("lon", "")).replace(",", ".")), float(str(r.get("lat", "")).replace(",", "."))
        except ValueError:
            bad.append((i, "zła współrzędna")); continue
        typ = (r.get("type") or "").strip()
        if typ not in OBS_TYPES:
            bad.append((i, f"nieznany typ '{typ}'")); continue
        if not inside_aoi(cfg, lon, lat):
            bad.append((i, "punkt poza obszarem demo")); continue
        sid = (r.get("survey_id") or default_survey or "").strip()
        if not sid:
            bad.append((i, "brak survey_id (kolumna albo --survey)")); continue
        ok.append({"survey_id": sid, "lon": round(lon, 6), "lat": round(lat, 6), "type": typ, "text": clean(r.get("text"))})
    return ok, bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--survey", help="id nalotu z surveys.yaml (gdy CSV nie ma kolumny survey_id)")
    args = ap.parse_args()
    cfg = load_config()
    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    ok, bad = parse_rows(rows, cfg, args.survey)
    for line, why in bad:
        print(f"  odrzucono wiersz {line}: {why}")
    if not ok:
        print("Nic do zaimportowania.")
        sys.exit(1)
    out = raw_dir(cfg) / "survey_observations.json"
    old = json.loads(out.read_text("utf-8")).get("observations", []) if out.exists() else []
    replaced = {o["survey_id"] for o in ok}
    merged = [o for o in old if o["survey_id"] not in replaced] + ok
    out.write_text(json.dumps({"updated_at": date.today().isoformat(), "observations": merged}, ensure_ascii=False), "utf-8")
    print(f"zaimportowano {len(ok)} obserwacji (odrzucono {len(bad)}); razem w pliku: {len(merged)}")
    print("Pamiętaj: nalot musi być wpisany w surveys.yaml (data, obszar), a API zrestartowane.")


if __name__ == "__main__":
    main()
