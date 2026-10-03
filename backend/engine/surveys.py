"""Rejestr nalotow dronem (i innych kontroli terenowych): KIEDY ostatnio sprawdzalismy dany obszar i co z tego wynika.

Po co: dane z OSM starzeja sie po cichu. Regularny nalot (domyslnie co 3 miesiace) daje dwie rzeczy:
(1) obserwacje terenowe (zastawiony chodnik, remont, zniszczona nawierzchnia) z data i zrodlem,
(2) uczciwa informacje w aplikacji, jak SWIEZE sa dane w danym miejscu - zamiast udawac, ze wszystko jest aktualne.

Czego nalot NIE widzi (wazne dla uczciwosci): szerokosci drzwi, progow i stopni pod okapem/zadaszeniem, wnetrz budynkow,
wysokosci krawezników ponizej kilku cm. Zob. pole `does_not_cover` przy kazdym nalocie - front powinien je pokazac.

Rejestr: surveys.yaml (edytowany recznie po kazdym nalocie). Obserwacje: data/raw/survey_observations.json
(tworzy je `python -m pipeline.import_survey plik.csv`).
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

TYPE_LABEL = {"dron": "nalot dronem", "spacer_terenowy": "kontrola terenowa", "audyt": "audyt dostępności"}
OBS_TYPES = {   # typ obserwacji -> (etykieta, tekst do przeczytania)
    "zastawiony_chodnik": ("Zastawiony chodnik", "zastawiony chodnik"),
    "chodnik_zablokowany": ("Zablokowany chodnik", "zablokowany chodnik"),
    "remont": ("Remont lub wykop", "remont na chodniku"),
    "nawierzchnia_zniszczona": ("Zniszczona nawierzchnia", "zniszczona nawierzchnia"),
    "waski_chodnik": ("Wąski chodnik", "wąski chodnik"),
    "przeszkoda": ("Przeszkoda na chodniku", "przeszkoda na chodniku"),
}
MIN_DAYS_PER_MONTH = 30.44


def _d(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except (TypeError, ValueError):
        return None


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, 28))


def _fmt(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "brak terminu"


def _local_xy(lon, lat, lat0):
    return (lon * 111_320 * math.cos(math.radians(lat0)), lat * 110_540)


class Surveys:
    def __init__(self, registry: dict | None = None, observations: list | None = None, aoi=None, root: Path | None = None):
        reg = registry or {}
        self.interval_months = int(reg.get("interval_months", 3))
        self.aoi = aoi
        self.items: list[dict] = []
        for s in reg.get("surveys") or []:
            d = _d(s.get("date"))
            geom = None
            if s.get("area") and root is not None and (Path(root) / s["area"]).exists():
                from pipeline.common import _read_aoi
                geom = _read_aoi(Path(root) / s["area"])
            self.items.append({**s, "_date": d, "_geom": geom if geom is not None else aoi,
                               "_done": (s.get("status", "wykonany") == "wykonany") and d is not None})
        self.observations = [o for o in (observations or []) if o.get("type") in OBS_TYPES]

    @classmethod
    def from_files(cls, cfg: dict, root: Path, raw: Path, aoi):
        import yaml
        reg_path = Path(root) / (cfg.get("surveys") or "surveys.yaml")
        reg = yaml.safe_load(reg_path.read_text("utf-8")) if reg_path.exists() else {}
        obs_path = Path(raw) / "survey_observations.json"
        obs = json.loads(obs_path.read_text("utf-8")).get("observations", []) if obs_path.exists() else []
        return cls(reg, obs, aoi, root)

    @property
    def available(self) -> bool:
        return any(s["_done"] for s in self.items)

    # ---------- pojedynczy punkt ----------
    def _covering(self, lon, lat) -> list[dict]:
        import shapely
        return [s for s in self.items if s["_done"] and s["_geom"] is not None and shapely.contains_xy(s["_geom"], lon, lat)]

    def _status(self, s: dict | None, today: date, covering_planned: dict | None = None) -> dict:
        if s is None:
            return {"has_survey": False, "fresh": False,
                    "text": "Brak nalotu ani kontroli terenowej w tym obszarze. Dane pochodzą z OpenStreetMap i zgłoszeń użytkowników."}
        d = s["_date"]
        age = (today - d).days
        due = _add_months(d, self.interval_months)
        fresh = today <= due
        label = TYPE_LABEL.get(s.get("type", "dron"), "kontrola terenowa")
        demo = " (PRZYKŁADOWE - dane demo)" if s.get("demo") else ""
        nxt = _d(s.get("next_planned"))
        if fresh:
            text = f"Ostatni {label}: {_fmt(d)} ({age} dni temu). Dane z tego obszaru uznajemy za świeże do {_fmt(due)}.{demo}"
        else:
            months = int(age // MIN_DAYS_PER_MONTH)
            text = (f"Ostatni {label}: {_fmt(d)} ({months} mies. temu) - dane mogą być nieaktualne. "
                    f"Następny planowany: {_fmt(nxt)}.{demo}")
        return {"has_survey": True, "survey_id": s.get("id"), "type": s.get("type", "dron"), "date": d.isoformat(), "age_days": age,
                "fresh": fresh, "fresh_until": due.isoformat(), "next_planned": nxt.isoformat() if nxt else None,
                "method": s.get("method"), "covers": s.get("covers") or [], "does_not_cover": s.get("does_not_cover") or [],
                "demo": bool(s.get("demo")), "text": text}

    def status_at(self, lon: float, lat: float, today: date | None = None) -> dict:
        today = today or date.today()
        cov = self._covering(lon, lat)
        latest = max(cov, key=lambda s: s["_date"]) if cov else None
        return self._status(latest, today)

    # ---------- trasa ----------
    def route_status(self, coords: list, today: date | None = None) -> dict:
        """Jaka czesc trasy lezy w obszarze objetym swiezym nalotem i kiedy byl ostatni. Przyblizenie liczone po wierzcholkach."""
        import shapely
        today = today or date.today()
        done = [s for s in self.items if s["_done"] and s["_geom"] is not None]
        if not coords or not done:
            return {"has_survey": False, "coverage_fresh_pct": 0, "text": self._status(None, today)["text"]}
        xs, ys = [c[0] for c in coords], [c[1] for c in coords]
        in_any = [False] * len(coords)
        in_fresh = [False] * len(coords)
        latest = None
        for s in done:
            m = shapely.contains_xy(s["_geom"], xs, ys)
            fresh = today <= _add_months(s["_date"], self.interval_months)
            for i, v in enumerate(m):
                if v:
                    in_any[i] = True
                    in_fresh[i] = in_fresh[i] or fresh
                    if latest is None or s["_date"] > latest["_date"]:
                        latest = s
        n = len(coords)
        pct_fresh = round(100 * sum(in_fresh) / n)
        pct_any = round(100 * sum(in_any) / n)
        if not any(in_any):
            return {"has_survey": False, "coverage_fresh_pct": 0, "coverage_any_pct": 0, "text": self._status(None, today)["text"]}
        st = self._status(latest, today)
        return {"has_survey": True, "coverage_fresh_pct": pct_fresh, "coverage_any_pct": pct_any, "last_date": st["date"],
                "demo": st["demo"],
                "text": f"{pct_fresh}% trasy leży w obszarze ze świeżym nalotem (ostatni: {_fmt(_d(st['date']))})."
                        + (" PRZYKŁADOWE - dane demo." if st["demo"] else "")}

    def observations_along(self, coords: list, max_m: float = 12.0, today: date | None = None) -> list[dict]:
        """Obserwacje z nalotow w poblizu trasy: [{...obs, at_m, dist_m, observed_at}] posortowane wzdluz trasy."""
        if not coords or not self.observations:
            return []
        lat0 = sum(c[1] for c in coords) / len(coords)
        pts = [_local_xy(c[0], c[1], lat0) for c in coords]
        cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        by_id = {s.get("id"): s for s in self.items}
        out = []
        for o in self.observations:
            px, py = _local_xy(o["lon"], o["lat"], lat0)
            best = None
            for i in range(len(pts) - 1):
                (ax, ay), (bx, by) = pts[i], pts[i + 1]
                dx, dy = bx - ax, by - ay
                seg2 = dx * dx + dy * dy
                t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                dist = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
                if best is None or dist < best[0]:
                    best = (dist, cum[i] + t * math.sqrt(seg2))
            if best and best[0] <= max_m:
                s = by_id.get(o.get("survey_id")) or {}
                out.append({**o, "dist_m": round(best[0]), "at_m": round(best[1]),
                            "observed_at": s["_date"].isoformat() if s.get("_date") else None, "demo": bool(s.get("demo"))})
        return sorted(out, key=lambda x: x["at_m"])

    # ---------- caly obszar ----------
    def overview(self, today: date | None = None) -> dict:
        today = today or date.today()
        done = sorted((s for s in self.items if s["_done"]), key=lambda s: s["_date"], reverse=True)
        planned = [s for s in self.items if not s["_done"]]
        fresh_geoms = [s["_geom"] for s in done if today <= _add_months(s["_date"], self.interval_months) and s["_geom"] is not None]
        fresh_pct = None
        if fresh_geoms and self.aoi is not None and self.aoi.area > 0:
            from shapely.ops import unary_union
            fresh_pct = round(100 * unary_union(fresh_geoms).intersection(self.aoi).area / self.aoi.area)
        elif self.aoi is not None:
            fresh_pct = 0
        return {"interval_months": self.interval_months,
                "last": self._status(done[0], today) if done else self._status(None, today),
                "area_with_fresh_survey_pct": fresh_pct,
                "surveys": [self._status(s, today) | {"id": s.get("id")} for s in done],
                "planned": [{"id": s.get("id"), "date": _fmt(s["_date"]), "type": s.get("type", "dron")} for s in planned],
                "observations_count": len(self.observations),
                "note": ("Nalot widzi ukształtowanie powierzchni i przeszkody z góry (nawierzchnia, zastawione chodniki, remonty, szerokość chodnika). "
                         "Nie widzi szerokości drzwi, stopni pod zadaszeniem ani wnętrz budynków - te dane nadal pochodzą z OSM, audytów i zgłoszeń.")}
