"""Lokalny geokoder (adresy i ulice z OSM dla obszaru demo) - bez zewnetrznych serwerow i bez danych osobowych.

Zapytania: "Florianska 12", "ul. Florianska", "pl nowy", "Grodzka 5a". Bez polskich znakow tez dziala.
Wyniki sa tylko z obszaru demo; brak adresu w OSM = brak wyniku (nie zgadujemy lokalizacji).
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path

PREFIXES = {"ul", "ulica", "al", "aleja", "pl", "plac", "os", "osiedle"}
NUM_RE = re.compile(r"^(?P<street>.*?)[\s,]+(?P<num>\d+\s?[a-zA-Z]?(?:/\d+[a-zA-Z]?)?)\s*$")


def norm(s: str) -> str:
    s = (s or "").replace("ł", "l").replace("Ł", "L")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[.,]", " ", s)).strip()


def strip_prefix(s: str) -> str:
    parts = s.split()
    if len(parts) > 1 and parts[0] in PREFIXES:
        parts = parts[1:]
    return " ".join(parts)


def parse_query(q: str) -> tuple[str, str | None]:
    """Zwraca (ulica_znormalizowana, numer_lub_None)."""
    q = (q or "").strip()
    m = NUM_RE.match(q)
    if m and m.group("street").strip():
        return strip_prefix(norm(m.group("street"))), m.group("num").replace(" ", "").lower()
    return strip_prefix(norm(q)), None


class Geocoder:
    def __init__(self, data: dict | None):
        data = data or {}
        self.meta = {k: data.get(k) for k in ("generated_at", "source", "license", "source_url")}
        self.entries = []
        for e in data.get("entries", []):
            e = dict(e)
            e["_street"] = strip_prefix(norm(e["street"]))
            e["_num"] = (e.get("number") or "").replace(" ", "").lower() or None
            self.entries.append(e)
        self.street_names = sorted({e["_street"] for e in self.entries})

    @classmethod
    def from_file(cls, path: Path) -> "Geocoder":
        path = Path(path)
        return cls(json.loads(path.read_text("utf-8")) if path.exists() else None)

    @property
    def available(self) -> bool:
        return bool(self.entries)

    @staticmethod
    def _label(e: dict) -> str:
        if e["type"] == "ulica":
            return f"{e['street']} (ulica)"
        return f"{e['street']} {e['number']}" + (f", {e['city']}" if e.get("city") else "")

    def reverse(self, lon: float, lat: float, max_adres_m: float = 60.0, max_ulica_m: float = 150.0) -> dict | None:
        """Najblizszy adres (a gdy brak - ulica) wokol punktu: do funkcji „gdzie jestem”. None, gdy w danych OSM nic nie ma blisko."""
        import math
        kx, ky = 111_320 * math.cos(math.radians(lat)), 110_540
        best_a = best_u = None
        for e in self.entries:
            d = math.hypot((e["lon"] - lon) * kx, (e["lat"] - lat) * ky)
            if e["type"] == "adres":
                if d <= max_adres_m and (best_a is None or d < best_a[0]):
                    best_a = (d, e)
            elif d <= max_ulica_m and (best_u is None or d < best_u[0]):
                best_u = (d, e)
        pick = best_a or best_u
        if not pick:
            return None
        d, e = pick
        return {"label": self._label(e), "street": e["street"], "number": e.get("number"), "type": e["type"], "distance_m": round(d)}

    def search(self, q: str, limit: int = 8) -> list[dict]:
        street, num = parse_query(q)
        if len(street) < 2:
            return []
        scored = []
        names = [n for n in self.street_names if n.startswith(street)] or [n for n in self.street_names if street in n]
        fuzzy = False
        if not names:   # literowka: "florianka" -> "floriańska"
            names = difflib.get_close_matches(street, self.street_names, n=3, cutoff=0.8)
            fuzzy = bool(names)
        nameset = set(names)
        for e in self.entries:
            if e["_street"] not in nameset:
                continue
            if num:
                if e["type"] == "ulica":
                    score = 3   # ulica bez numeru jako zapas, gdy numeru brak w OSM
                elif e["_num"] == num:
                    score = 0
                elif e["_num"] and e["_num"].startswith(num):
                    score = 1
                else:
                    continue
            else:
                score = 0 if e["type"] == "ulica" else 1
            exact = 0 if e["_street"] == street else 1
            scored.append((score, exact, len(e["_street"]), e["_num"] or "", e))
        scored.sort(key=lambda x: x[:4])
        res = [{"id": e["id"], "label": self._label(e), "type": e["type"], "street": e["street"], "number": e.get("number"),
                "lon": e["lon"], "lat": e["lat"], "exact": sc == 0 and bool(num) and e["type"] == "adres",
                "approximate": e["type"] == "ulica" and bool(num),
                "fuzzy": fuzzy} for sc, _, _, _, e in scored[:limit]]
        return res


# ---------- odmiana: "z Rynku Glownego do Dworca Glownego" -> "rynek glowny", "dworzec glowny" ----------
# Ludzie (i rozpoznawanie mowy) uzywaja form odmienionych, a w danych sa mianowniki. Reguly sa przyblizone: dajemy KANDYDATOW,
# a dopiero trafienie w prawdziwa nazwe z danych decyduje (zla odmiana po prostu nic nie znajdzie).
_SUFFIX_RULES = [("ego", "y"), ("ego", "i"), ("iej", "a"), ("ej", "a"), ("ym", "y"), ("im", "i"), ("ca", "zec"), ("ca", "ec"),
                 ("ku", "ek"), ("owi", ""), ("u", ""), ("a", ""), ("y", "a"), ("e", "a")]
_LEADING = {"na", "w", "we", "do", "z", "ze", "od", "przy", "pod", "nad", "u", "kolo", "obok", "pod"}
_MAX_CANDIDATES = 30


def deinflect(q: str) -> list[str]:
    """Kandydaci form podstawowych dla zapytania (bez oryginalu), od najmniej zmienionych. Liczby i numery domow zostawiamy."""
    words = norm(q).split()
    while len(words) > 1 and words[0] in _LEADING:
        words = words[1:]
    options = []
    for w in words:
        alts = [w]
        if not re.search(r"\d", w) and len(w) > 3:
            for suf, rep in _SUFFIX_RULES:
                if w.endswith(suf) and len(w) - len(suf) >= 3:
                    alt = w[: len(w) - len(suf)] + rep
                    if alt not in alts:
                        alts.append(alt)
        options.append(alts)
    cands: list[tuple[int, str]] = [(0, "")]
    for alts in options:
        nxt = []
        for cost, prefix in cands:
            for i, a in enumerate(alts):
                nxt.append((cost + (1 if i else 0), (prefix + " " + a).strip()))
        cands = sorted(nxt)[: 400]
    original = norm(q)
    out, seen = [], {original}
    for _, c in sorted(cands):
        if c not in seen:
            seen.add(c)
            out.append(c)
        if len(out) >= _MAX_CANDIDATES:
            break
    return out
