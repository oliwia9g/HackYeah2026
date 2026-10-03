"""Profil lokalny („konto bez konta”): plik JSON, ktory uzytkownik trzyma NA SWOIM URZADZENIU.

Dlaczego nie konto na serwerze: wymagania dostepnosciowe to dane o zdrowiu (RODO art. 9, szczegolna kategoria). Najbezpieczniejsze jest
ich nie zbierac. Front zapisuje plik w pamieci przegladarki (localStorage/IndexedDB) i pozwala go pobrac/wczytac na innym urzadzeniu.
Serwer tylko SPRAWDZA plik (walidacja, normalizacja, zamiana wyboru na parametry API) i niczego nie zapamietuje.

Format wersja 1:
  {"format": "krakow-bez-barier-profil", "version": 1, "name": "Babcia Hela",
   "groups": ["senior"], "on": ["toilet", "incline:6"], "off": ["bench"],
   "ui": {"mode": "prosty", "font_scale": 1.5, "contrast": "wysoki", "reduce_motion": true, "voice_replies": true, "max_steps": 5},
   "places": [{"label": "Dom", "lon": 19.94, "lat": 50.06}]}
"""
from __future__ import annotations

import json
import re

from engine.profiles import CATALOG, PROFILES, active_items, build_profile, merge_profiles, resolve_selection

FORMAT = "krakow-bez-barier-profil"
VERSION = 1
MAX_BYTES = 20_000
UI_MODES = {"standard": "Standardowy", "prosty": "Prosty: duże kafelki, kilka kroków, jedno zdanie na krok",
            "skupienie": "Skupienie (np. ADHD): jeden krok naraz, bez animacji, spokojne kolory, bez presji czasu"}
CONTRASTS = ("normalny", "wysoki")
KNOWN = {"format", "version", "name", "groups", "on", "off", "ui", "places"}
UI_DEFAULT = {"mode": "standard", "font_scale": 1.0, "contrast": "normalny", "reduce_motion": False, "voice_replies": False, "max_steps": 7}
LIMITS = {"name": 40, "places": 20, "label": 40, "font_scale": (1.0, 2.0), "max_steps": (3, 9), "lists": 30}
_CTRL = re.compile(r"[\x00-\x1f\x7f<>]")

EXAMPLES = {
    "babcia": {"format": FORMAT, "version": VERSION, "name": "Babcia Hela", "groups": ["senior"], "on": ["toilet"], "off": [],
               "ui": {"mode": "prosty", "font_scale": 1.6, "contrast": "wysoki", "reduce_motion": True, "voice_replies": True, "max_steps": 5},
               "places": [{"label": "Dom", "lon": 19.9400, "lat": 50.0610}]},
    "wozek_toaleta": {"format": FORMAT, "version": VERSION, "name": "Marek", "groups": ["wozek_inwalidzki"], "on": ["toilet", "lift"],
                      "off": [], "ui": {"mode": "standard"}, "places": []},
    "skupienie": {"format": FORMAT, "version": VERSION, "name": "Ola", "groups": [], "on": ["lit", "bench:400"], "off": [],
                  "ui": {"mode": "skupienie", "reduce_motion": True, "max_steps": 4}, "places": []},
}


def schema() -> dict:
    """Opis formatu pliku dla frontu (JSON Schema + przyklady + zasady prywatnosci)."""
    return {
        "format": FORMAT, "version": VERSION, "max_bytes": MAX_BYTES,
        "json_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "required": ["format", "version"],
            "properties": {
                "format": {"const": FORMAT}, "version": {"type": "integer", "minimum": 1},
                "name": {"type": "string", "maxLength": LIMITS["name"], "description": "Dowolna nazwa profilu, tylko dla użytkownika."},
                "groups": {"type": "array", "items": {"enum": list(PROFILES)}, "uniqueItems": True},
                "on": {"type": "array", "items": {"type": "string"}, "description": "Id pozycji z /api/catalog do włączenia (opcjonalnie z parametrem: incline:6, width:0.9, bench:300)."},
                "off": {"type": "array", "items": {"enum": list(CATALOG)}, "description": "Id pozycji do zdjęcia z wybranej grupy."},
                "ui": {"type": "object", "properties": {
                    "mode": {"enum": list(UI_MODES)}, "font_scale": {"type": "number", "minimum": 1.0, "maximum": 2.0},
                    "contrast": {"enum": list(CONTRASTS)}, "reduce_motion": {"type": "boolean"}, "voice_replies": {"type": "boolean"},
                    "max_steps": {"type": "integer", "minimum": 3, "maximum": 9}}},
                "places": {"type": "array", "maxItems": LIMITS["places"], "items": {"type": "object", "required": ["label", "lon", "lat"],
                          "properties": {"label": {"type": "string", "maxLength": LIMITS["label"]}, "lon": {"type": "number"}, "lat": {"type": "number"}}}},
            }},
        "tryby_interfejsu": UI_MODES, "przyklady": EXAMPLES,
        "prywatnosc": ["Plik jest zapisany tylko na urządzeniu użytkownika; serwer go nie przechowuje ani nie zapisuje w logach.",
                       "Wymagania dostępnościowe to dane o zdrowiu: nie wysyłamy ich do analityki ani osobom trzecim.",
                       "Ulubione miejsca (adres domowy) są tylko w pliku: do serwera trafiają wyłącznie jako zwykłe współrzędne trasy, gdy użytkownik o nią poprosi.",
                       "Użytkownik może w każdej chwili pobrać plik, wczytać go na innym urządzeniu lub usunąć dane z przeglądarki."],
    }


def _clean_text(v, limit, field, errors):
    if not isinstance(v, str):
        errors.append(f"'{field}' musi być tekstem.")
        return None
    return _CTRL.sub("", v).strip()[:limit]


def _str_list(v, field, errors):
    if v is None:
        return []
    if not isinstance(v, list) or any(not isinstance(x, str) for x in v) or len(v) > LIMITS["lists"]:
        errors.append(f"'{field}' musi być listą tekstów (maks. {LIMITS['lists']}).")
        return []
    return list(dict.fromkeys(x.strip().lower() for x in v if x.strip()))


def validate(doc, inside=None) -> dict:
    """Sprawdza plik profilu. Zwraca {"ok", "errors", "warnings", "profile", "query": {"profiles","prefs"}, "etykieta", "aktywne"}.
    `inside(lon, lat) -> bool` (opcjonalnie) oznacza, czy ulubione miejsca leza w obszarze z danymi. Bledy NIE rzucaja wyjatkow."""
    errors, warnings = [], []
    out = {"ok": False, "errors": errors, "warnings": warnings, "profile": None, "query": {"profiles": "", "prefs": ""},
           "etykieta": None, "aktywne": []}
    if not isinstance(doc, dict):
        errors.append("Plik musi być obiektem JSON.")
        return out
    try:
        if len(json.dumps(doc, ensure_ascii=False)) > MAX_BYTES:
            errors.append(f"Plik jest za duży (maks. {MAX_BYTES // 1000} kB).")
            return out
    except (TypeError, ValueError):
        errors.append("Plik zawiera wartości, których nie da się zapisać jako JSON.")
        return out
    if doc.get("format") != FORMAT:
        errors.append(f"To nie jest plik profilu tej aplikacji (pole 'format' powinno mieć wartość '{FORMAT}').")
        return out
    ver = doc.get("version")
    if not isinstance(ver, int) or isinstance(ver, bool) or ver < 1:
        errors.append("Pole 'version' musi być liczbą całkowitą od 1.")
        return out
    if ver > VERSION:
        warnings.append(f"Plik pochodzi z nowszej wersji formatu ({ver}); wczytujemy tylko pola, które znamy (wersja {VERSION}).")
    unknown = sorted(k for k in doc if k not in KNOWN)
    if unknown:
        warnings.append("Pominięto nieznane pola: " + ", ".join(k[:30] for k in unknown[:10]) + ".")

    name = None
    if doc.get("name") is not None:
        name = _clean_text(doc["name"], LIMITS["name"], "name", errors)

    groups = _str_list(doc.get("groups"), "groups", errors)
    bad = [g for g in groups if g not in PROFILES]
    if bad:
        errors.append("Nieznane grupy: " + ", ".join(b[:30] for b in bad) + ". Dostępne: " + ", ".join(PROFILES) + ".")
        groups = [g for g in groups if g in PROFILES]
    on = _str_list(doc.get("on"), "on", errors)
    off = _str_list(doc.get("off"), "off", errors)

    ui = dict(UI_DEFAULT)
    raw_ui = doc.get("ui")
    if raw_ui is not None and not isinstance(raw_ui, dict):
        errors.append("'ui' musi być obiektem.")
        raw_ui = {}
    for k, v in (raw_ui or {}).items():
        if k == "mode":
            if v in UI_MODES:
                ui["mode"] = v
            else:
                errors.append(f"Nieznany tryb interfejsu. Dostępne: {', '.join(UI_MODES)}.")
        elif k == "contrast":
            if v in CONTRASTS:
                ui["contrast"] = v
            else:
                errors.append(f"Kontrast: {', '.join(CONTRASTS)}.")
        elif k in ("reduce_motion", "voice_replies"):
            if isinstance(v, bool):
                ui[k] = v
            else:
                errors.append(f"'ui.{k}' musi być true albo false.")
        elif k in ("font_scale", "max_steps"):
            lo, hi = LIMITS[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                errors.append(f"'ui.{k}' musi być liczbą.")
                continue
            clamped = min(hi, max(lo, v))
            if clamped != v:
                warnings.append(f"'ui.{k}' poza zakresem {lo}-{hi}: ustawiono {clamped}.")
            ui[k] = int(clamped) if k == "max_steps" else round(float(clamped), 2)
        else:
            warnings.append(f"Pominięto nieznane ustawienie interfejsu 'ui.{k[:30]}'.")

    places = []
    raw_places = doc.get("places")
    if raw_places is not None and (not isinstance(raw_places, list)):
        errors.append("'places' musi być listą.")
        raw_places = []
    if len(raw_places or []) > LIMITS["places"]:
        warnings.append(f"Za dużo ulubionych miejsc: zostawiono pierwsze {LIMITS['places']}.")
    for i, p in enumerate((raw_places or [])[:LIMITS["places"]], 1):
        if not isinstance(p, dict):
            errors.append(f"Miejsce {i}: oczekiwano obiektu z polami label, lon, lat.")
            continue
        lab = _clean_text(p.get("label"), LIMITS["label"], f"places[{i}].label", errors) if p.get("label") is not None else ""
        lon, lat = p.get("lon"), p.get("lat")
        ok_num = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (lon, lat))
        if not ok_num or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            errors.append(f"Miejsce {i}: współrzędne 'lon' i 'lat' muszą być liczbami (lon -180..180, lat -90..90).")
            continue
        if not lab:
            errors.append(f"Miejsce {i}: brak nazwy ('label').")
            continue
        item = {"label": lab, "lon": round(float(lon), 6), "lat": round(float(lat), 6)}
        if inside is not None:
            item["inside_area"] = bool(inside(item["lon"], item["lat"]))
        places.append(item)

    query = {"profiles": ",".join(groups), "prefs": ""}
    label, aktywne = None, []
    try:
        prefs = resolve_selection(groups, on, off)
        keys = build_profile(groups, prefs)
        query["prefs"] = prefs
        if keys:
            merged = merge_profiles(keys)
            label, aktywne = merged["label"], sorted(active_items(merged))
        if off and not groups:
            warnings.append("Lista 'off' zdejmuje wymagania wybranej grupy, a żadnej grupy nie wybrano: pominięto.")
    except ValueError as e:
        errors.append(str(e))

    out["profile"] = {"format": FORMAT, "version": VERSION, "name": name, "groups": groups, "on": on, "off": off, "ui": ui, "places": places}
    out["query"] = query
    out["etykieta"] = label or ("Pieszy (bez ograniczeń)" if not errors else None)
    out["aktywne"] = aktywne
    out["ok"] = not errors
    if out["ok"] and (groups or on or off):
        warnings.append("Plik opisuje wymagania dostępnościowe (dane o zdrowiu): trzymaj go tylko na swoim urządzeniu.")
    return out
