"""Rozklad jazdy (GTFS), planowanie z komunikacja i dostepnosc pojazdow - na malym, sztucznym rozkladzie."""
import io
import zipfile
from datetime import datetime

from engine.multimodal import plan
from engine.transit import Transit
from pipeline.fetch_gtfs import build
from tests.conftest import P


def _zip(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for k, v in files.items():
            z.writestr(k, "﻿" + v)
    return zipfile.ZipFile(io.BytesIO(b.getvalue()))


GTFS = _zip({
    "stops.txt": "stop_id,stop_name,stop_lat,stop_lon,wheelchair_boarding\ns1,Rynek Główny,50.0617,19.9373,1\ns2,Daleko,51.0,20.5,1\ns3,Plac Nowy,50.0510,19.9450,0\n",
    "routes.txt": "route_id,route_short_name,route_type\nr1,3,0\n",
    "trips.txt": "route_id,service_id,trip_id,trip_headsign,wheelchair_accessible\nr1,wk,t1,Nowa Huta,1\nr1,wk,t2,Nowa Huta,0\nr1,wk,t3,Nowa Huta,2\n",
    "stop_times.txt": "trip_id,stop_id,departure_time\nt1,s1,10:00:00\nt2,s1,10:05:00\nt3,s1,25:10:00\nt1,s3,10:07:00\nt1,s2,10:30:00\n",
    "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nwk,1,1,1,1,1,1,1,20260101,20261231\n",
    "calendar_dates.txt": "service_id,date,exception_type\nwk,20261104,2\n"})
BBOX = (19.924, 50.046, 19.962, 50.073)


def test_gtfs_keeps_only_stops_in_area():
    d = build([("tramwaj", GTFS)], BBOX)
    names = {s["name"] for s in d["stops"].values()}
    assert "Rynek Główny" in names and "Daleko" not in names


def test_departures_after_midnight_and_service_exceptions():
    t = Transit(build([("tramwaj", GTFS)], BBOX))
    assert t.departures("tramwaj:s1", datetime(2026, 10, 4, 1, 0))            # kurs 25:10 liczy sie do poprzedniej doby
    assert all(d["date"] != "2026-11-04" for d in t.departures("tramwaj:s1", datetime(2026, 11, 4, 9, 0)))   # wyjatek w calendar_dates


def test_zero_flags_in_gtfs_are_not_shown_as_accessible():
    """ZTP wpisuje w GTFS same zera = brak danych. 'brak danych' nie moze byc 'dostepny'."""
    t = Transit(build([("tramwaj", GTFS)], BBOX))
    s3 = next(s for s in t.stops.values() if s["name"] == "Plac Nowy")
    assert s3["wheelchair_boarding"] == "unknown"


def _stop(i, name, mode, xy):
    return {"id": i, "gtfs_id": i.split(":")[1], "feed": mode, "name": name, "lon": xy[0], "lat": xy[1], "mode": mode,
            "lines": ["8"], "wheelchair_boarding": "unknown"}


def _transit():
    stops = {"autobus:A": _stop("autobus:A", "Start", "autobus", P[1]), "autobus:B": _stop("autobus:B", "Cel", "autobus", P[7]),
             "tramwaj:A": _stop("tramwaj:A", "Start tram", "tramwaj", P[1]), "tramwaj:B": _stop("tramwaj:B", "Cel tram", "tramwaj", P[7])}
    deps = [["autobus:A", 10 * 3600 + 600, "123", "Cel", "unknown", "autobus:s", 0], ["autobus:B", 10 * 3600 + 960, "123", "Cel", "unknown", "autobus:s", 0],
            ["tramwaj:A", 10 * 3600 + 420, "8", "Cel", "unknown", "tramwaj:s", 1], ["tramwaj:B", 10 * 3600 + 720, "8", "Cel", "unknown", "tramwaj:s", 1]]
    svc = {s: {"days": [1] * 7, "start": "20200101", "end": "20350101"} for s in ("autobus:s", "tramwaj:s")}
    return Transit({"stops": stops, "departures": deps, "services": svc, "trip_keys": ["autobus:t1", "tramwaj:t2"], "trips": {}})


NOW = datetime(2026, 10, 3, 10, 0)


def test_plan_for_wheelchair_only_offers_accessible_vehicles_and_says_stop_access_is_unknown(net):
    r = plan(net, _transit(), None, P[1], P[7], ["wozek_inwalidzki"], NOW)
    assert r["accessible_only"] is True
    for o in r["options"]:
        assert o["ride"]["wheelchair"] in ("yes", "likely")           # tramwaj bez danych o pojezdzie jest wykluczony
    assert any("przystank" in n.lower() for n in r["notes"])           # dostepnosc przystanku != dostepnosc pojazdu


def test_plan_without_accessibility_filter_shows_unknown_vehicles_honestly(net):
    r = plan(net, _transit(), None, P[1], P[7], [], NOW, accessible_only=False)
    rides = {o["ride"]["wheelchair"] for o in r["options"]}
    assert "unknown" in rides or "likely" in rides
    assert all(o["ride"]["wheelchair_basis"] for o in r["options"])


def test_useless_ride_is_filtered_out(net):
    """Przejazd, ktory nie skraca drogi (prawie ten sam dystans pieszo) nie powinien byc proponowany."""
    r = plan(net, _transit(), None, P[1], P[7], [], NOW, accessible_only=False)
    walk = r["walk_only"]["length_m"]
    for o in r["options"]:
        assert o["ride"]["ride_min"] >= 3 and o["walk_m"] < 0.85 * walk
