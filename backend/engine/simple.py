"""Tryb prosty: trasa w kilku krotkich krokach, jednym zdaniem na krok, z kierunkiem skretu.

Dla osob starszych, z ADHD i innych trudnosci w skupieniu, oraz do czytania na glos: maks. kilka krokow, bez skrotow i liczb
z dokladnoscia do metra, ostrzezenia jako osobne pole (zeby front mogl je wyroznic ikona, a nie tylko kolorem).
Kierunek skretu liczymy z geometrii trasy; gdy sie nie da (krotkie odcinki), piszemy samo „idź”.
"""
from __future__ import annotations

import math

MAX_STEPS = 7
TURN_STRAIGHT = 30     # stopni: ponizej tego uznajemy, ze idziemy prosto
TURN_BACK = 150


def _xy(c, lat0):
    return (c[0] * 111_320 * math.cos(math.radians(lat0)), c[1] * 110_540)


def _round_m(m: float) -> int:
    return int(round(m / 10.0) * 10) if m >= 100 else int(round(m / 5.0) * 5) or 5


def _bearing(a, b) -> float:
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360


class _Line:
    def __init__(self, coords, total_m):
        lat0 = sum(c[1] for c in coords) / len(coords)
        self.pts = [_xy(c, lat0) for c in coords]
        cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        self.cum = cum
        self.scale = (cum[-1] / total_m) if total_m and cum[-1] else 1.0     # dlugosc ze wspolrzednych vs dlugosc z grafu

    def at(self, d_graph: float):
        d = max(0.0, min(self.cum[-1], d_graph * self.scale))
        for i in range(len(self.cum) - 1):
            if self.cum[i + 1] >= d:
                seg = self.cum[i + 1] - self.cum[i]
                t = 0.0 if seg == 0 else (d - self.cum[i]) / seg
                a, b = self.pts[i], self.pts[i + 1]
                return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        return self.pts[-1]

    def turn_at(self, d_graph: float, window=15.0):
        """Kat skretu w punkcie d (dodatni = w prawo) albo None, gdy za malo geometrii."""
        before, here, after = self.at(d_graph - window), self.at(d_graph), self.at(d_graph + window)
        if math.hypot(here[0] - before[0], here[1] - before[1]) < 3 or math.hypot(after[0] - here[0], after[1] - here[1]) < 3:
            return None
        delta = (_bearing(here, after) - _bearing(before, here) + 540) % 360 - 180
        return delta


def _turn_word(delta):
    if delta is None:
        return None
    if abs(delta) < TURN_STRAIGHT:
        return "prosto"
    if abs(delta) >= TURN_BACK:
        return "zawroc"
    return "prawo" if delta > 0 else "lewo"


def simple_route(steps: list, coords: list, length_m: float, time_min: float, hazard_counts: dict | None = None,
                 max_steps: int = MAX_STEPS) -> dict:
    """Zwraca {"summary", "steps": [...], "spoken"}; kazdy krok: n, text, distance_m, turn, warning, warning_text."""
    items = []
    total = sum(st["length_m"] for st in steps) or float(length_m or 1)
    line = _Line(coords, total) if coords and len(coords) > 1 else None
    for i, st in enumerate(steps):
        delta = line.turn_at(st.get("start_m", 0)) if (line and i > 0) else None
        items.append({"kind": st.get("kind") or "chodnik", "name": st.get("name"), "m": st["length_m"], "status": st["status"],
                      "notes": list(st.get("notes") or []), "turn": _turn_word(delta) if i > 0 else "start"})
    # laczymy kolejne zwykle odcinki, jesli nie ma miedzy nimi skretu i nie ma ostrzezen
    def mergeable(a, b):
        return (a["kind"] == b["kind"] == "chodnik" and a["status"] == b["status"] == 0 and not a["notes"] and not b["notes"]
                and b["turn"] in ("prosto", None))
    merged = []
    for it in items:
        if merged and mergeable(merged[-1], it):
            merged[-1]["m"] += it["m"]
        else:
            merged.append(dict(it))
    while len(merged) > max_steps:       # nadal za duzo: scalamy najkrotsza pare zwyklych odcinkow
        cands = [(merged[i]["m"] + merged[i + 1]["m"], i) for i in range(len(merged) - 1)
                 if merged[i]["kind"] == merged[i + 1]["kind"] == "chodnik" and merged[i]["status"] == merged[i + 1]["status"] == 0
                 and not merged[i]["notes"] and not merged[i + 1]["notes"]]
        if not cands:
            break
        _, i = min(cands)
        merged[i]["m"] += merged[i + 1]["m"]
        merged[i]["name"] = merged[i].get("name") or merged[i + 1].get("name")
        del merged[i + 1]
    out = []
    for n, it in enumerate(merged, 1):
        m = _round_m(it["m"])
        street = f" ulicą {it['name']}" if it.get("name") and it["kind"] == "chodnik" else ""
        if it["kind"] == "schody":
            text = f"Schody, około {m} metrów."
        elif it["kind"] == "przejscie":
            text = "Przejdź przez jezdnię po przejściu dla pieszych."
        else:
            lead = {"start": "Idź", "prosto": "Idź prosto", "prawo": "Skręć w prawo i idź", "lewo": "Skręć w lewo i idź",
                    "zawroc": "Zawróć i idź", None: "Idź"}[it["turn"]]
            text = f"{lead}{street} około {m} metrów."
        warn = None
        if it["status"] == 2:
            warn = "Przeszkoda: " + (it["notes"][0] if it["notes"] else "trasa może być niedostępna")
        elif it["status"] == 1 or it["notes"]:
            warn = "Uwaga: " + (it["notes"][0] if it["notes"] else "brak pewnych danych")
        out.append({"n": n, "text": text, "distance_m": m, "turn": it["turn"], "kind": it["kind"],
                    "warning": bool(warn), "warning_text": warn})
    out.append({"n": len(out) + 1, "text": "Jesteś u celu.", "distance_m": 0, "turn": "koniec", "kind": "cel",
                "warning": False, "warning_text": None})
    mins = max(1, round(time_min or 0))
    counts = hazard_counts or {}
    attention = counts.get("blokada", 0) + counts.get("ostrzezenie", 0)
    unknown = counts.get("brak_danych", 0)
    summary = f"Trasa ma około {_round_m(length_m)} metrów, to około {mins} min."
    if attention:
        summary += f" Na trasie jest {attention} {'miejsce' if attention == 1 else 'miejsc' if attention > 4 else 'miejsca'} wymagające uwagi."
    if unknown:
        summary += f" W {unknown} miejscach nie mamy danych."
    return {"summary": summary, "steps": out, "max_steps": max_steps}


def spoken_summary(props: dict, limit: int = 3) -> str:
    """Zdanie(a) do przeczytania na glos: dlugosc, czas i najblizsze zagrozenia z odlegloscia od startu."""
    mins = max(1, round(props.get("time_min") or 0))
    out = f"Trasa ma około {_round_m(props.get('length_m') or 0)} metrów, to około {mins} min."
    hz = [h for h in props.get("hazards", []) if h["severity"] in ("blokada", "ostrzezenie")]
    if not hz:
        out += " Nie znamy żadnych przeszkód na tej trasie, ale brak informacji nie gwarantuje, że ich nie ma."
        return out
    out += f" Uwaga na {len(hz)} {'miejsce' if len(hz) == 1 else 'miejsc' if len(hz) > 4 else 'miejsca'}:"
    parts = [f"po {_round_m(h['at_m'])} metrach {h['spoken'][:1].lower() + h['spoken'][1:]}" for h in hz[:limit]]
    out += " " + "; ".join(parts) + "."
    if len(hz) > limit:
        out += f" Oraz {len(hz) - limit} kolejnych."
    return out
