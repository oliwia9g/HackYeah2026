"""Dostepnosc pojazdow (proweniencja) i dane na zywo z ZTP (GTFS-RT) - bez dostepu do sieci."""
import time

from google.transit import gtfs_realtime_pb2 as rt

from engine.fleet import OK, vehicle_access
from engine.realtime import Realtime


def test_bus_is_only_likely_never_confirmed():
    a = vehicle_access("autobus", "unknown", None)
    assert a["wheelchair"] == "likely" and a["wheelchair_basis"] and a["wheelchair"] in OK


def test_bus_explicit_no_wins():
    assert vehicle_access("autobus", "no", "123")["wheelchair"] == "no"


def test_tram_unknown_flag_unknown_type_is_unknown():
    assert vehicle_access("tramwaj", "unknown", None)["wheelchair"] == "unknown"


def test_tram_flag_without_known_type_is_based_on_flag_only():
    a = vehicle_access("tramwaj", "yes", "BRAK")      # etykieta bez numeru -> typ taboru nieznany
    assert a["wheelchair"] == "yes" and "nieznany" in a["wheelchair_basis"]


def test_tram_flag_contradicting_high_floor_type_is_conflict():
    from engine.fleet import TRAM_FLEET
    high = next((n for n, v in TRAM_FLEET.items() if v.get("floor") == "high"), None)
    if high is None:
        return    # brak pliku taboru w srodowisku testowym
    assert vehicle_access("tramwaj", "yes", high)["wheelchair"] == "conflict"


def _feeds():
    now = int(time.time())
    tu = rt.FeedMessage(); tu.header.gtfs_realtime_version = "2.0"
    for i, (tid, dt) in enumerate([("t1", 120), ("t2", 300), ("t3", 600)]):
        e = tu.entity.add(); e.id = str(i); e.trip_update.trip.trip_id = tid
        u = e.trip_update.stop_time_update.add(); u.stop_id = "S1"; u.arrival.time = now + dt; u.arrival.delay = 30
    vp = rt.FeedMessage(); vp.header.gtfs_realtime_version = "2.0"
    for i, (tid, w) in enumerate([("t1", 2), ("t2", 0), ("t3", 3)]):
        e = vp.entity.add(); e.id = str(i); e.vehicle.trip.trip_id = tid
        e.vehicle.vehicle.label = f"32{i}"; e.vehicle.vehicle.wheelchair_accessible = w
    return {"TripUpdates_T.pb": tu.SerializeToString(), "VehiclePositions_T.pb": vp.SerializeToString()}


STOP = {"id": "tramwaj:S1", "gtfs_id": "S1", "feed": "tramwaj"}
TRIPS = {"tramwaj:t1": ["3", "Nowa Huta"], "tramwaj:t2": ["3", "Nowa Huta"]}


def test_live_departures_and_filter():
    files, ok = _feeds(), [True]

    def fetch(name):
        if not ok[0]:
            raise RuntimeError("503")
        return files[name]
    r = Realtime(fetch)
    deps = r.live_for_stop(STOP, TRIPS)["departures"]
    assert [d["line"] for d in deps][:2] == ["3", "3"] and len(deps) == 3
    only = r.live_for_stop(STOP, TRIPS, only_accessible=True)["departures"]
    assert all(d["wheelchair"] in OK for d in only) and len(only) < len(deps)


def test_outage_uses_recent_cache_then_says_so():
    files, ok = _feeds(), [True]

    def fetch(name):
        if not ok[0]:
            raise RuntimeError("503")
        return files[name]
    r = Realtime(fetch)
    r.live_for_stop(STOP, TRIPS)
    ok[0] = False
    r._cache["tramwaj"]["at"] -= 60
    x = r.live_for_stop(STOP, TRIPS)
    assert x["available"] and x["stale"]                 # swiezy-ish cache, ale oznaczony jako nieaktualny
    r._cache["tramwaj"]["at"] -= 1000
    y = r.live_for_stop(STOP, TRIPS)
    assert not y["available"] and y["reason"]            # za stare dane: jawny komunikat zamiast zgadywania


def test_status_reports_outage():
    def boom(name):
        raise RuntimeError("down")
    st = Realtime(boom).status()
    assert st["tramwaj"]["ok"] is False and st["autobus"]["ok"] is False
