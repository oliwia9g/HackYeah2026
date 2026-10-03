"""Pobiera rozkłady ZTP Kraków (GTFS) i wycina z nich przystanki z obszaru demo.

Wynik: raw/transit.json (do silnika/API) oraz public/data/transit_stops.geojson (warstwa dla frontu).

Uruchomienie (z katalogu backend/):
    python -m pipeline.fetch_gtfs                       # pobiera tramwaje i autobusy
    python -m pipeline.fetch_gtfs --file tram.zip --file bus.zip   # z plikow pobranych recznie

Zasady:
- wheelchair_boarding / wheelchair_accessible: 1 = tak, 2 = nie, 0 lub puste = BRAK DANYCH (nigdy "dostepne").
- To dane z ROZKLADU JAZDY, nie z pozycji pojazdow na zywo.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from datetime import date

import pandas as pd
import requests

from pipeline.common import bbox_tuple, load_aoi, load_config, out_dir, raw_dir, write_geojson

URLS = {
    "tramwaj": "https://gtfs.ztp.krakow.pl/GTFS_KRK_T.zip",
    "autobus": "https://gtfs.ztp.krakow.pl/GTFS_KRK_A.zip",
}
HEADERS = {"User-Agent": "HackYeah2026-krakow-bez-barier/0.1 (hackathon prototype)"}
def route_mode(code, fallback: str) -> str:
    """GTFS: 0 = tramwaj, 3 = autobus; rozszerzone kody 900-906 = tramwaj, 700-716 = autobus. Nieznany kod -> etykieta feedu."""
    try:
        c = int(code)
    except (TypeError, ValueError):
        return fallback
    if c == 0 or 900 <= c <= 906:
        return "tramwaj"
    if c == 3 or 700 <= c <= 716:
        return "autobus"
    return {1: "metro", 2: "kolej"}.get(c, fallback)
LICENSE = "otwarte dane ZTP Kraków - warunki licencji do potwierdzenia (patrz sources.yaml)"
SOURCE_URL = "https://gtfs.ztp.krakow.pl/"


def _read(z: zipfile.ZipFile, name: str, **kw) -> pd.DataFrame:
    if name not in z.namelist():
        return pd.DataFrame()
    with z.open(name) as f:
        return pd.read_csv(f, dtype=str, encoding="utf-8-sig", keep_default_na=False, **kw)


def _wc(v) -> str:
    """GTFS: 1 tak, 2 nie, reszta = brak danych."""
    return {"1": "yes", "2": "no"}.get(str(v).strip(), "unknown")


def _secs(t: str) -> int | None:
    try:
        h, m, s = (int(x) for x in t.strip().split(":"))
        return h * 3600 + m * 60 + s
    except ValueError:
        return None


def build(zips: list[tuple[str, zipfile.ZipFile]], bbox: tuple, aoi=None) -> dict:
    """zips: [(etykieta, ZipFile)]. bbox: (left, bottom, right, top). aoi: wielokat (shapely) - dokladniejszy filtr."""
    left, bottom, right, top = bbox
    stops_out, deps_out, services, exceptions, trips_out = {}, [], {}, {}, {}
    trip_keys, tidx = [], {}   # numer kursu w odjazdach = indeks w trip_keys (laczy przystanki jednego kursu)
    for label, z in zips:
        stops = _read(z, "stops.txt")
        if stops.empty:
            continue
        stops["lon"] = pd.to_numeric(stops["stop_lon"], errors="coerce")
        stops["lat"] = pd.to_numeric(stops["stop_lat"], errors="coerce")
        inb = stops[(stops.lon >= left) & (stops.lon <= right) & (stops.lat >= bottom) & (stops.lat <= top)]
        if aoi is not None and not inb.empty:
            import shapely
            inb = inb[shapely.contains_xy(aoi, inb["lon"].to_numpy(), inb["lat"].to_numpy())]
        if inb.empty:
            continue
        ids = set(inb["stop_id"])
        wb = inb["wheelchair_boarding"] if "wheelchair_boarding" in inb else pd.Series("", index=inb.index)

        # stop_times: czytamy kawalkami, bo dla autobusow to miliony wierszy
        parts = []
        with z.open("stop_times.txt") as f:
            for ch in pd.read_csv(f, dtype=str, encoding="utf-8-sig", keep_default_na=False, chunksize=500_000,
                                  usecols=["trip_id", "stop_id", "departure_time"]):
                parts.append(ch[ch["stop_id"].isin(ids)])
        st = pd.concat(parts) if parts else pd.DataFrame(columns=["trip_id", "stop_id", "departure_time"])
        trips = _read(z, "trips.txt")
        routes = _read(z, "routes.txt")
        if "wheelchair_accessible" not in trips:
            trips["wheelchair_accessible"] = ""
        if "trip_headsign" not in trips:
            trips["trip_headsign"] = ""
        df = (st.merge(trips[["trip_id", "route_id", "service_id", "trip_headsign", "wheelchair_accessible"]], on="trip_id")
                .merge(routes[["route_id", "route_short_name", "route_type"]], on="route_id"))
        df["sec"] = df["departure_time"].map(_secs)
        df = df.dropna(subset=["sec"])

        # przystanek obslugiwany przez linie + czy jest w rozkladzie niskopodlogowy kurs
        for r, w in zip(inb.itertuples(), wb):
            sid = f"{label}:{r.stop_id}"
            sub = df[df["stop_id"] == r.stop_id]
            stops_out[sid] = {
                "id": sid, "gtfs_id": r.stop_id, "feed": label, "name": r.stop_name, "lon": float(r.lon), "lat": float(r.lat),
                "wheelchair_boarding": _wc(w),
                "mode": route_mode(sub["route_type"].mode().iat[0], label) if len(sub) else label,
                "lines": sorted(set(sub["route_short_name"])),
            }
        # trip_id -> (linia, kierunek): potrzebne do laczenia z danymi na zywo (GTFS-RT)
        for tid, line, head in df[["trip_id", "route_short_name", "trip_headsign"]].drop_duplicates("trip_id").itertuples(index=False):
            trips_out[f"{label}:{tid}"] = [line, head]
            tidx[f"{label}:{tid}"] = len(trip_keys)
            trip_keys.append(f"{label}:{tid}")
        for r in df.itertuples():
            deps_out.append([f"{label}:{r.stop_id}", int(r.sec), r.route_short_name, r.trip_headsign,
                             _wc(r.wheelchair_accessible), f"{label}:{r.service_id}",
                             tidx[f"{label}:{r.trip_id}"]])

        cal = _read(z, "calendar.txt")
        for r in cal.itertuples():
            days = [int(getattr(r, d)) for d in
                    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")]
            services[f"{label}:{r.service_id}"] = {"days": days, "start": r.start_date, "end": r.end_date}
        cd = _read(z, "calendar_dates.txt")
        for r in cd.itertuples():
            exceptions.setdefault(f"{label}:{r.service_id}", {})[r.date] = int(r.exception_type)

    return {"generated_at": date.today().isoformat(), "source": "ZTP Kraków GTFS", "source_url": SOURCE_URL,
            "license": LICENSE, "stops": stops_out, "trips": trips_out, "trip_keys": trip_keys, "departures": deps_out, "services": services, "exceptions": exceptions}


def download(url: str) -> zipfile.ZipFile:
    print(f"pobieram {url} ...")
    r = requests.get(url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    return zipfile.ZipFile(io.BytesIO(r.content))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="append", help="zip GTFS pobrany recznie (mozna podac kilka razy)")
    args = ap.parse_args()
    cfg = load_config()

    zips = []
    if args.file:
        for i, p in enumerate(args.file):
            zips.append((f"plik{i + 1}", zipfile.ZipFile(p)))
    else:
        for label, url in URLS.items():
            try:
                zips.append((label, download(url)))
            except requests.RequestException as e:
                print(f"  nie udalo sie ({label}): {e}")
    if not zips:
        print("Brak danych GTFS. Pobierz recznie GTFS_KRK_T.zip i GTFS_KRK_A.zip ze strony ZTP "
              "i uruchom z --file.")
        sys.exit(1)

    data = build(zips, bbox_tuple(cfg), load_aoi(cfg))
    raw = raw_dir(cfg)
    (raw / "transit.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")

    import geopandas as gpd
    from shapely.geometry import Point
    rows = [{**{k: v for k, v in s.items() if k != "lines"}, "lines": ",".join(s["lines"]),
             "geometry": Point(s["lon"], s["lat"])} for s in data["stops"].values()]
    if rows:
        write_geojson(gpd.GeoDataFrame(rows, crs="EPSG:4326"), out_dir(cfg) / "transit_stops.geojson")
    n_wc = sum(1 for s in data["stops"].values() if s["wheelchair_boarding"] == "yes")
    n_unk = sum(1 for s in data["stops"].values() if s["wheelchair_boarding"] == "unknown")
    print(f"przystanki w obszarze demo: {len(data['stops'])} (dostepne: {n_wc}, brak danych: {n_unk}), "
          f"odjazdy w rozkladzie: {len(data['departures'])}")
    low = sum(1 for d in data["departures"] if d[4] == "yes")
    print(f"  kursy z niską podłogą oznaczone W ROZKŁADZIE ZTP: {low} ({100 * low / max(1, len(data['departures'])):.0f}%)")
    if low == 0:
        print("  To oczekiwane: ZTP nie wypełnia tych pól w GTFS (same zera = brak danych). Dostępność pojazdów liczy API:")
        print("  autobusy = deklaracja MPK (prawdopodobnie), tramwaje = dane na żywo ZTP + typ taboru (engine/fleet.py).")

if __name__ == "__main__":
    main()
