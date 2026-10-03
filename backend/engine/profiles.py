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

# Profile można łączyć (np. senior + wózek): bierzemy ostrzejszy próg i wyższy mnożnik.
def merge_profiles(keys: list[str]) -> dict:
    merged = {"label": " + ".join(PROFILES[k]["label"] for k in keys), "hard": {}, "weights": {},
              "needs": [], "unknown_penalty": 1.0}
    for k in keys:
        p = PROFILES[k]
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
