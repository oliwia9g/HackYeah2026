"""Plan podrozy: spacer (z przeszkodami wg profilu) + przejazd tramwajem/autobusem jednym kursem + spacer.

- Spacery sa liczone po sieci pieszej tym samym silnikiem co trasy (zagrozenia, krawezniki, nachylenia).
- Przejazd: kurs z rozkladu ZTP, ktory ma w obszarze demo przystanek startowy i docelowy w tej kolejnosci. Bez przesiadek.
- Dostepnosc pojazdu: autobus = deklaracja MPK ("prawdopodobnie"), tramwaj = flaga ZTP na zywo + typ taboru; brak danych =/= dostepny.
  Dla profili wozkowych domyslnie pokazujemy tylko przejazdy, gdzie pojazd jest `yes` albo `likely`.
- Dostepnosc samego PRZYSTANKU (peron, krawezniki) nie jest w danych ZTP - zawsze zaznaczamy to w uwagach.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from engine.fleet import OK, vehicle_access

WALK_SPEED_FALLBACK = 4.0


def _fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _vehicle_access(transit, realtime, ride: dict) -> dict:
    board = transit.stops[ride["board"]]
    mode, feed = board.get("mode"), board.get("feed")
    key = transit.trip_keys[ride["trip"]] if ride["trip"] < len(transit.trip_keys) else None
    veh = None
    if realtime is not None and key and ":" in key:
        veh = realtime.vehicle_for_trip(feed, key.split(":", 1)[1])
    flag = ride["wc"]
    if veh and veh.get("wheelchair") in ("yes", "no"):
        flag = veh["wheelchair"]
    acc = vehicle_access(mode if mode in ("tramwaj", "autobus") else feed, flag, veh["label"] if veh else None)
    acc["vehicle"] = veh["label"] if veh else None
    acc["live_assigned"] = veh is not None
    return acc


def plan(net, transit, realtime, origin: tuple, dest: tuple, keys: list, now: datetime,
         accessible_only: bool | None = None, max_walk_m: int = 700, max_options: int = 3) -> dict:
    """origin/dest = (lon, lat); now = czas lokalny (naive, Europe/Warsaw)."""
    if accessible_only is None:
        accessible_only = any(k.startswith("wozek") for k in keys)
    out = {"walk_only": None, "options": [], "notes": [], "accessible_only": accessible_only, "excluded_inaccessible": 0}
    walk = net.route(origin, dest, keys, "warn")
    if walk is not None:
        out["walk_only"] = walk
    if not transit.available or not transit.can_plan:
        out["notes"].append("Brak danych do planowania przejazdów (uruchom pipeline.fetch_gtfs). Pokazujemy tylko trasę pieszą.")
        return out

    cache: dict = {}

    def leg(a, b, tag):
        k = (a, b)
        if k not in cache:
            cache[k] = net.route(a, b, keys, "warn")
        return cache[k]

    boards, alights = {}, {}
    for s in transit.nearby(*origin, radius_m=max_walk_m, limit=8):
        r = leg(origin, (s["lon"], s["lat"]), "to")
        if r and r["length_m"] <= max_walk_m * 1.3:
            boards[s["id"]] = r
    for s in transit.nearby(*dest, radius_m=max_walk_m, limit=8):
        r = leg((s["lon"], s["lat"]), dest, "from")
        if r and r["length_m"] <= max_walk_m * 1.3:
            alights[s["id"]] = r
    if not boards:
        out["notes"].append("W pobliżu startu nie ma przystanku osiągalnego pieszo tą trasą (w obszarze demo).")
        return out
    if not alights:
        out["notes"].append("W pobliżu celu nie ma przystanku osiągalnego pieszo tą trasą (w obszarze demo).")
        return out

    cands = []
    for b, wb in boards.items():
        earliest = now + timedelta(minutes=wb["time_min"])
        for r in transit.rides({b}, set(alights), earliest):
            if r["board"] == r["alight"]:
                continue
            wa = alights[r["alight"]]
            r["walk_to"], r["walk_from"] = wb, wa
            r["arrive"] = r["arr"] + timedelta(minutes=wa["time_min"])
            cands.append(r)
    seen, picked, excluded = set(), [], 0
    for r in sorted(cands, key=lambda r: r["arrive"]):
        sig = (r["line"], r["board"], r["alight"])
        if sig in seen:
            continue
        seen.add(sig)
        acc = _vehicle_access(transit, realtime, r)
        if accessible_only and acc["wheelchair"] not in OK:
            excluded += 1
            continue
        r["acc"] = acc
        picked.append(r)
        if len(picked) >= max_options:
            break
    out["excluded_inaccessible"] = excluded
    if excluded:
        out["notes"].append(f"Pominięto {excluded} przejazd(ów), bo nie ma potwierdzenia, że pojazd jest dostępny. "
                            "Dla tramwajów dostępność znamy dopiero, gdy ZTP przypisze pojazd do kursu (zwykle ok. godziny przed odjazdem).")
    if not picked:
        out["notes"].append("Nie znaleziono przejazdu bez przesiadki w najbliższych 90 minutach (w obszarze demo).")
    options = []
    for i, r in enumerate(picked, 1):
        wait = max(0, round((r["dep"] - (now + timedelta(minutes=r["walk_to"]["time_min"]))).total_seconds() / 60))
        total = round((r["arrive"] - now).total_seconds() / 60)
        bs, als = transit.stops[r["board"]], transit.stops[r["alight"]]
        counts = {k: r["walk_to"]["hazard_counts"][k] + r["walk_from"]["hazard_counts"][k] for k in r["walk_to"]["hazard_counts"]}
        summary = (f"Idź {r['walk_to']['length_m']} m do przystanku {bs['name']}, {bs['mode']} {r['line']} w kierunku "
                   f"{r['headsign']} o {_fmt(r['dep'])}, wysiądź na przystanku {als['name']} ({_fmt(r['arr'])}), "
                   f"potem idź {r['walk_from']['length_m']} m do celu.")
        options.append({
            "id": f"przejazd{i}", "summary": summary, "depart": _fmt(now), "board_departure": _fmt(r["dep"]),
            "arrive": _fmt(r["arrive"]), "total_min": total, "wait_min": wait,
            "walk_m": r["walk_to"]["length_m"] + r["walk_from"]["length_m"], "hazard_counts": counts,
            "ride": {"mode": bs["mode"], "line": r["line"], "headsign": r["headsign"], "stops_between": r["stops_between"],
                     "board_stop": {"id": bs["id"], "name": bs["name"], "lon": bs["lon"], "lat": bs["lat"]},
                     "alight_stop": {"id": als["id"], "name": als["name"], "lon": als["lon"], "lat": als["lat"]},
                     "departs": _fmt(r["dep"]), "arrives": _fmt(r["arr"]), "service_date": r["dep"].strftime("%Y-%m-%d"),
                     "ride_min": round((r["arr"] - r["dep"]).total_seconds() / 60), **r["acc"]},
            "walk_to": r["walk_to"], "walk_from": r["walk_from"], "_board_id": r["board"],
        })
    wo = out["walk_only"]
    if wo is not None:
        wmin = wo["time_min"]
        for o in options:
            o["faster_than_walking_min"] = round(wmin - o["total_min"], 1)
    out["options"] = options
    out["notes"].append("Dostępność przystanków (wysokość peronu, krawężniki przy przystanku) nie jest w danych ZTP - sprawdź na miejscu. "
                        "Godziny z rozkładu; sprawdź prognozę na żywo.")
    return out
