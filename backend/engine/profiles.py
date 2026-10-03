"""Profile użytkowników = zestawy preferencji (NIE deklaracja niepełnosprawności).

Każdy profil ma:
- hard: twarde progi (przekroczenie => krawędź wykluczona z trasy)
- weights: miękkie mnożniki kosztu (1.0 = neutralnie, >1 = unikaj)
- needs: jakie udogodnienia pokazać na karcie miejsca / warstwy mapy
- unknown_penalty: kara za brak danych o krawędzi (tryb "tylko pewne" wyklucza je całkiem)
- bench_every_m + weights.long_segment_no_rest: krawędzie dalej niż bench_every_m (po sieci pieszej) od najbliższej
  ławki z OSM dostają mnożnik kosztu. To ocena komfortu, nie twarda blokada; brak ławki w OSM nie znaczy, że jej nie ma.

Wartości progów to punkt startowy - dostroić po audycie danych i testach na trasach.
"""

PROFILES = {
    "wozek_inwalidzki": {
        "label": "Wózek inwalidzki",
        "hard": {
            "forbid_steps": True,
            "max_incline_pct": 6.0,
            "require_kerb": ["lowered", "flush"],   # na przejściach; brak danych => niepewne
            "min_width_m": 0.9,
        },
        "weights": {"surface_rough": 3.0, "incline_per_pct": 0.25},
        "needs": ["windy", "toalety_dostepne", "szerokosc_wejscia", "tramwaje_niskopodlogowe"],
        "unknown_penalty": 1.6,
    },
    "wozek_dziecko": {
        "label": "Wózek z dzieckiem",
        "hard": {"forbid_steps": True, "max_incline_pct": 8.0, "require_kerb": ["lowered", "flush"],
                 "min_width_m": 0.7},
        "weights": {"surface_rough": 2.0, "incline_per_pct": 0.15},
        "needs": ["przewijak", "windy", "toalety", "tramwaje_niskopodlogowe"],
        "unknown_penalty": 1.4,
    },
    "niewidomy_slabowidzacy": {
        "label": "Osoba niewidoma / słabowidząca",
        "hard": {"forbid_steps": False, "require_tactile_at_crossing": False},
        "weights": {"no_tactile_paving": 1.8, "no_sound_signal": 2.0, "unlit": 1.5,
                    "stairs_no_handrail": 2.5, "surface_rough": 1.3},
        "needs": ["prowadzenie_dotykowe", "sygnalizacja_dzwiekowa", "oswietlenie", "porecze"],
        "unknown_penalty": 1.3,
    },
    "gluchy_niedoslyszacy": {
        "label": "Osoba głucha / niedosłysząca",
        # trasa bez specjalnych ograniczeń - ten profil wpływa głównie na KARTĘ MIEJSCA
        "hard": {},
        "weights": {},
        "needs": ["petla_indukcyjna", "informacja_wizualna", "tlumacz_pjm"],
        "unknown_penalty": 1.0,
    },
    "senior": {
        "label": "Senior",
        "hard": {"forbid_steps": False, "max_incline_pct": 8.0},
        "weights": {"incline_per_pct": 0.2, "surface_rough": 1.8, "long_segment_no_rest": 1.4},
        "needs": ["lawki", "toalety", "cien", "tramwaje_niskopodlogowe"],
        "unknown_penalty": 1.3,
        "bench_every_m": 300,
    },
    "ciaza": {
        "label": "Kobieta w ciąży",
        "hard": {"forbid_steps": False, "max_incline_pct": 10.0},
        "weights": {"incline_per_pct": 0.15, "surface_rough": 1.3, "long_segment_no_rest": 1.3},
        "needs": ["lawki", "toalety", "apteki_przychodnie", "tramwaje_niskopodlogowe"],
        "unknown_penalty": 1.2,
        "bench_every_m": 400,
    },
}

# ---------- własne preferencje (bez nazw grup i bez deklarowania niepełnosprawności) ----------
CUSTOM: dict = {}          # klucz "wlasne_xxxx" -> profil zbudowany z preferencji
_CUSTOM_MAX = 200
PREF_HELP = {
    "nostairs": "bez schodów", "incline:N": "maksymalne nachylenie w % (1-15)", "width:M": "minimalna szerokość przejścia w m (0.5-1.5)",
    "kerb": "tylko obniżone/zrównane krawężniki na przejściach", "smooth": "unikaj kostki i nierównej nawierzchni",
    "tactile": "preferuj prowadzenie dotykowe", "sound": "preferuj sygnalizację dźwiękową", "lit": "unikaj nieoświetlonych odcinków",
    "bench:M": "ławka co najwyżej co M metrów (100-1000)", "speed:V": "tempo marszu w km/h (2-6)",
    "need:X": "dodaj udogodnienie do sprawdzania w miejscach: toilet, lift, changing, loop, tactile, lit, bench",
    "relax:X": "zdejmij wymóg wynikający z wybranej grupy: " + "stairs, incline, kerb, width, surface, bench, tactile, sound, lit, handrail, "
               "toilet, lift, changing, loop, lowfloor, entrance_width",
}

# ---------- katalog barier i udogodnień: co można włączyć lub wyłączyć niezależnie od grupy ----------
# id -> (etykieta, opis, [(sekcja, klucz)] gdzie siedzi w profilu, typ: "bariera" | "udogodnienie", token dodawania lub None)
CATALOG = {
    "stairs": ("Schody", "Trasa omija schody", [("hard", "forbid_steps")], "bariera", "nostairs"),
    "incline": ("Nachylenie", "Ogranicza strome odcinki (parametr: maks. % nachylenia)", [("hard", "max_incline_pct"), ("weights", "incline_per_pct")], "bariera", "incline:6"),
    "kerb": ("Wysokie krawężniki", "Na przejściach wymaga krawężnika obniżonego lub zrównanego", [("hard", "require_kerb")], "bariera", "kerb"),
    "width": ("Wąskie przejścia", "Minimalna szerokość przejścia (parametr w m)", [("hard", "min_width_m")], "bariera", "width:0.9"),
    "surface": ("Nierówna nawierzchnia", "Unika kostki i nierównej nawierzchni", [("weights", "surface_rough")], "bariera", "smooth"),
    "bench": ("Brak ławek", "Preferuje trasy z miejscami do odpoczynku", [("weights", "long_segment_no_rest"), ("top", "bench_every_m"), ("needs", "lawki")], "udogodnienie", "bench:300"),
    "tactile": ("Prowadzenie dotykowe", "Preferuje przejścia z prowadzeniem dotykowym", [("weights", "no_tactile_paving"), ("needs", "prowadzenie_dotykowe")], "udogodnienie", "tactile"),
    "sound": ("Sygnał dźwiękowy", "Preferuje sygnalizację dźwiękową na przejściach", [("weights", "no_sound_signal"), ("needs", "sygnalizacja_dzwiekowa")], "udogodnienie", "sound"),
    "lit": ("Oświetlenie", "Unika nieoświetlonych odcinków", [("weights", "unlit"), ("needs", "oswietlenie")], "udogodnienie", "lit"),
    "handrail": ("Poręcze", "Ostrzega o schodach bez poręczy", [("weights", "stairs_no_handrail"), ("needs", "porecze")], "bariera", None),
    "toilet": ("Dostępna toaleta", "Sprawdza toaletę dostępną dla wózka w miejscu", [("needs", "toalety"), ("needs", "toalety_dostepne")], "udogodnienie", "need:toilet"),
    "lift": ("Winda", "Sprawdza dostęp bez schodów / windę", [("needs", "windy")], "udogodnienie", "need:lift"),
    "changing": ("Przewijak", "Sprawdza przewijak w miejscu", [("needs", "przewijak")], "udogodnienie", "need:changing"),
    "loop": ("Pętla indukcyjna", "Sprawdza pętlę indukcyjną w miejscu", [("needs", "petla_indukcyjna")], "udogodnienie", "need:loop"),
    "lowfloor": ("Niska podłoga w pojeździe", "Pokazuje dostępność pojazdu komunikacji", [("needs", "tramwaje_niskopodlogowe")], "udogodnienie", None),
    "entrance_width": ("Szerokość wejścia", "Sprawdza szerokość drzwi wejściowych", [("needs", "szerokosc_wejscia")], "udogodnienie", None),
}
NEED_TOKENS = {"toilet": "toalety_dostepne", "lift": "windy", "changing": "przewijak", "loop": "petla_indukcyjna",
               "tactile": "prowadzenie_dotykowe", "lit": "oswietlenie", "bench": "lawki"}


def get_profile(key: str) -> dict:
    return PROFILES[key] if key in PROFILES else CUSTOM[key]


def custom_profile(spec: str) -> str:
    """Tekst preferencji (np. "nostairs,incline:6,kerb,bench:300") -> klucz profilu "wlasne_xxxx".
    Wyniki zależą tylko od preferencji, nie od tego, kim jest użytkownik. Zły token -> ValueError z opisem."""
    import hashlib
    hard, weights, bits, speed, bench, needs = {}, {}, [], None, None, []

    def num(tok, name, lo, hi):
        try:
            v = float(tok.split(":", 1)[1])
        except (IndexError, ValueError):
            raise ValueError(f"'{name}' wymaga liczby, np. {name}:6")
        if not lo <= v <= hi:
            raise ValueError(f"'{name}' musi być w zakresie {lo}-{hi}")
        return v

    tokens = sorted({t.strip().lower() for t in (spec or "").split(",") if t.strip()})
    for t in tokens:
        name = t.split(":", 1)[0]
        if name in ("nostairs", "bez_schodow"):
            hard["forbid_steps"] = True; bits.append("bez schodów")
        elif name == "incline":
            v = num(t, name, 1, 15); hard["max_incline_pct"] = v; weights["incline_per_pct"] = 0.2; bits.append(f"nachylenie do {v:g}%")
        elif name == "width":
            v = num(t, name, 0.5, 1.5); hard["min_width_m"] = v; bits.append(f"szerokość od {v:g} m")
        elif name == "kerb":
            hard["require_kerb"] = ["lowered", "flush"]; bits.append("niskie krawężniki")
        elif name == "smooth":
            weights["surface_rough"] = 2.5; bits.append("gładka nawierzchnia")
        elif name == "tactile":
            weights["no_tactile_paving"] = 1.8; bits.append("prowadzenie dotykowe")
        elif name == "sound":
            weights["no_sound_signal"] = 2.0; bits.append("sygnał dźwiękowy")
        elif name == "lit":
            weights["unlit"] = 1.5; bits.append("oświetlenie")
        elif name == "bench":
            bench = num(t, name, 100, 1000); weights["long_segment_no_rest"] = 1.4; bits.append(f"ławka co {bench:g} m")
        elif name == "speed":
            speed = num(t, name, 2, 6)
        elif name == "need":
            what = t.split(":", 1)[1] if ":" in t else ""
            if what not in NEED_TOKENS:
                raise ValueError(f"'need' wymaga jednej z wartości: {', '.join(NEED_TOKENS)}")
            needs.append(NEED_TOKENS[what]); bits.append(CATALOG[what][0].lower())
        else:
            raise ValueError(f"Nieznana preferencja '{t}'. Dostępne: {', '.join(PREF_HELP)}")
    if not tokens:
        raise ValueError("Puste preferencje")
    key = "wlasne_" + hashlib.sha1(",".join(tokens).encode()).hexdigest()[:8]
    if key not in CUSTOM:
        if len(CUSTOM) >= _CUSTOM_MAX:
            CUSTOM.pop(next(iter(CUSTOM)))
        prof = {"label": "Własne preferencje" + (": " + ", ".join(bits) if bits else ""), "hard": hard, "weights": weights,
                "needs": sorted(set(needs)), "unknown_penalty": 1.4 if hard else 1.2}
        if bench:
            prof["bench_every_m"] = bench
        if speed:
            prof["speed_kmh"] = speed
        CUSTOM[key] = prof
    return key


def profile_speed(key: str, default: float, table: dict) -> float:
    if key in table:
        return table[key]
    return CUSTOM.get(key, {}).get("speed_kmh", default)


# Profile można łączyć (np. senior + wózek): bierzemy ostrzejszy próg i wyższy mnożnik.
def merge_profiles(keys: list[str]) -> dict:
    merged = {"label": " + ".join(get_profile(k)["label"] for k in keys), "hard": {}, "weights": {},
              "needs": [], "unknown_penalty": 1.0}
    for k in keys:
        p = get_profile(k)
        for name, val in p["hard"].items():
            if name == "max_incline_pct":
                merged["hard"][name] = min(val, merged["hard"].get(name, val))
            elif name == "min_width_m":
                merged["hard"][name] = max(val, merged["hard"].get(name, val))
            else:
                merged["hard"][name] = merged["hard"].get(name, False) or val
        for name, val in p["weights"].items():
            merged["weights"][name] = max(val, merged["weights"].get(name, val))
        merged["needs"] += [n for n in p["needs"] if n not in merged["needs"]]
        merged["unknown_penalty"] = max(merged["unknown_penalty"], p["unknown_penalty"])
        if "bench_every_m" in p:   # przy laczeniu profili bierzemy surowszy (mniejszy) odstep miedzy lawkami
            merged["bench_every_m"] = min(p["bench_every_m"], merged.get("bench_every_m", p["bench_every_m"]))
    return merged


# ---------- zdejmowanie i dodawanie wymagan na wybranych grupach ----------
def active_items(prof: dict) -> list[str]:
    """Id pozycji katalogu, ktore dany profil (juz scalony) faktycznie wymusza."""
    out = []
    for cid, (_, _, places, _, _) in CATALOG.items():
        for sec, key in places:
            src = prof if sec == "top" else prof.get(sec, {})
            if (key in src) and (src[key] not in (False, None, [], 0) if sec != "needs" else True) or (sec == "needs" and key in prof.get("needs", [])):
                out.append(cid)
                break
    return out


def _relax(prof: dict, ids: list[str]) -> dict:
    prof = {**prof, "hard": dict(prof.get("hard", {})), "weights": dict(prof.get("weights", {})), "needs": list(prof.get("needs", []))}
    for cid in ids:
        for sec, key in CATALOG[cid][2]:
            if sec == "top":
                prof.pop(key, None)
            elif sec == "needs":
                prof["needs"] = [n for n in prof["needs"] if n != key]
            else:
                prof[sec].pop(key, None)
    return prof


def build_profile(group_keys: list[str], spec: str | None) -> list[str]:
    """Grupy (sztywne 6) + wlasne preferencje -> lista kluczy profili.
    Tokeny `relax:X` zdejmuja wymog wynikajacy z grup, `need:X` i pozostale dodaja. Zwraca [] gdy nic nie wybrano.
    Zly token -> ValueError z opisem."""
    import hashlib
    keys = list(group_keys)
    tokens = [t.strip().lower() for t in (spec or "").split(",") if t.strip()]
    relax = sorted({t.split(":", 1)[1] if ":" in t else "" for t in tokens if t.split(":", 1)[0] == "relax"})
    rest = [t for t in tokens if t.split(":", 1)[0] != "relax"]
    bad = [r for r in relax if r not in CATALOG]
    if bad:
        raise ValueError(f"Nieznana wartość relax: {', '.join(bad) or '(pusta)'}. Dostępne: {', '.join(CATALOG)}")
    if rest:
        keys.append(custom_profile(",".join(rest)))
    if not relax:
        return keys
    if not keys:
        raise ValueError("'relax' zdejmuje wymagania wybranej grupy - najpierw wybierz grupę albo preferencje.")
    base = merge_profiles(keys)
    derived = _relax(base, relax)
    key = "wlasne_" + hashlib.sha1((",".join(keys) + "|" + ",".join(relax)).encode()).hexdigest()[:8]
    if key not in CUSTOM:
        if len(CUSTOM) >= _CUSTOM_MAX:
            CUSTOM.pop(next(iter(CUSTOM)))
        derived["label"] = base["label"] + " (bez: " + ", ".join(CATALOG[r][0].lower() for r in relax) + ")"
        CUSTOM[key] = derived
    return [key]


def resolve_selection(group_keys: list[str], on: list[str], off: list[str]) -> str:
    """Wybor z ekranu „Moje wymagania” (wlacz te pozycje, wylacz tamte, przy wybranych grupach) -> tekst `prefs`.
    on: id pozycji katalogu, ewentualnie z parametrem (incline:6); off: id pozycji do zdjecia z grupy. Zly wybor -> ValueError."""
    base = set(active_items(merge_profiles(group_keys))) if group_keys else set()
    tokens = []
    for raw in [x.strip().lower() for x in on if x and x.strip()]:
        cid = raw.split(":", 1)[0]
        if cid not in CATALOG:
            raise ValueError(f"Nieznana pozycja '{cid}'. Dostępne: {', '.join(CATALOG)}")
        if ":" in raw:
            if cid not in ("incline", "width", "bench"):
                raise ValueError(f"Pozycja '{cid}' nie ma parametru.")
            tokens.append(raw)
        elif cid not in base:
            if not CATALOG[cid][4]:
                raise ValueError(f"Pozycji '{cid}' nie można dodać; można ją tylko zdjąć z grupy.")
            tokens.append(CATALOG[cid][4])
    for cid in [x.strip().lower() for x in off if x and x.strip()]:
        if cid not in CATALOG:
            raise ValueError(f"Nieznana pozycja '{cid}'. Dostępne: {', '.join(CATALOG)}")
        if cid in base:
            tokens.append(f"relax:{cid}")
    return ",".join(dict.fromkeys(tokens))


def catalog() -> dict:
    """Dane do ekranu „Moje wymagania”: sztywne 6 grup z ich domyslnymi pozycjami + wszystkie pozycje do wlaczenia/wylaczenia."""
    groups = [{"key": k, "label": p["label"], "domyslne": active_items(merge_profiles([k]))} for k, p in PROFILES.items()]
    items = [{"id": cid, "label": lab, "opis": desc, "rodzaj": kind, "token_dodaj": add, "token_usun": f"relax:{cid}"}
             for cid, (lab, desc, _, kind, add) in CATALOG.items()]
    return {"grupy": groups, "pozycje": items,
            "jak_uzyc": "Wybierz grupę (opcjonalnie), potem dla każdej pozycji: odznaczona domyślna = token_usun, zaznaczona niedomyślna = token_dodaj. "
                        "Złóż je po przecinku w parametr prefs albo użyj /api/catalog/resolve."}
