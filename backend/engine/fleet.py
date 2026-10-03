"""Dostepnosc POJAZDU (tramwaj/autobus) z kilku zrodel, z jawnym statusem.

Wartosci `wheelchair`: yes | likely | unknown | no | conflict
- yes      : dwa zrodla sie zgadzaja (flaga ZTP na zywo + typ taboru) albo flaga ZTP dla pojazdu o nieznanym typie
- likely   : prawdopodobne - deklaracja przewoznika / typ taboru, bez potwierdzenia dla tego pojazdu
- no       : pojazd wysokopodlogowy lub oznaczony jako niedostepny
- conflict : zrodla sie wykluczaja (np. ZTP: dostepny, a typ taboru: wysoka podloga)
- unknown  : brak danych (NIGDY nie znaczy "dostepne")
Dostepnosc pojazdu to nie dostepnosc przystanku (wysokosc peronu, krawezniki) - to osobna informacja.
"""
from __future__ import annotations

import csv
from pathlib import Path

FLEET_CSV = Path(__file__).parent / "data" / "tram_fleet.csv"
WC_TEXT = {
    "yes": "pojazd oznaczony jako dostępny",
    "likely": "prawdopodobnie dostępny",
    "no": "pojazd niedostępny dla wózka",
    "conflict": "sprzeczne dane o dostępności pojazdu",
    "unknown": "brak danych o dostępności pojazdu",
}
BUS_DECLARATION = ("Wg MPK Kraków od 2018 r. osoby na wózkach korzystają wyłącznie z autobusów niskopodłogowych "
                   "(mpk.krakow.pl). To deklaracja przewoźnika, nie sprawdzenie tego pojazdu - rampa może być niesprawna, "
                   "a część linii obsługują inni przewoźnicy.")
BUS_SOURCE_URL = "https://mpk.krakow.pl/artykul/13/dostepnosc-dla-osob-z-ograniczona-mobilnoscia"
TRAM_FLEET_URL = "https://api.ttss.pl/vehicles/trams/"
OK = ("yes", "likely")   # co przepuszcza filtr "tylko dostepne"


def _num(label: str | None) -> str:
    digits = "".join(ch for ch in (label or "") if ch.isdigit())
    return digits[-3:] if digits else ""


def load_tram_fleet(path: Path = FLEET_CSV) -> dict:
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8") as f:
        rows = csv.DictReader(line for line in f if not line.startswith("#"))
        # ZTP podaje w GTFS-RT sam numer taborowy (np. "603"), a wykaz TTSS ma prefiks literowy (np. "RP603").
        # Numery sa unikalne, wiec kluczem jest numer: cyfry z konca oznaczenia.
        return {_num(r["vehicle_id"]): {"model": r["model"], "floor": r["floor"], "id": r["vehicle_id"].strip()} for r in rows}


TRAM_FLEET = load_tram_fleet()


def vehicle_access(mode: str, rt_flag: str, label: str | None) -> dict:
    """rt_flag: yes/no/unknown z GTFS-RT. Zwraca {wheelchair, text, basis, model}."""
    if mode == "autobus":
        if rt_flag in ("yes", "no"):
            return _r(rt_flag, "flaga ZTP (GTFS-RT)")
        return _r("likely", "deklaracja MPK Kraków: flota niskopodłogowa od 2018 r.")
    fleet = TRAM_FLEET.get(_num(label)) if _num(label) else None
    floor = fleet["floor"] if fleet else None
    model = fleet["model"] if fleet else None
    if floor == "high":
        if rt_flag == "yes":
            return _r("conflict", "ZTP: dostępny, ale typ taboru (%s) ma wysoką podłogę" % model, model)
        return _r("no", "typ taboru: wysoka podłoga (%s)" % model, model)
    if floor == "low":
        if rt_flag == "yes":
            return _r("yes", "flaga ZTP + typ taboru niskopodłogowy (%s), dwa źródła się zgadzają" % model, model)
        if rt_flag == "no":
            return _r("conflict", "ZTP: niedostępny, ale typ taboru (%s) jest niskopodłogowy" % model, model)
        return _r("likely", "typ taboru niskopodłogowy (%s), bez flagi ZTP" % model, model)
    # nieznany lub czesciowo niskopodlogowy typ -> opieramy sie tylko na fladze ZTP
    if rt_flag in ("yes", "no"):
        return _r(rt_flag, "flaga ZTP (GTFS-RT), typ taboru nieznany" if not model else "flaga ZTP, tabor częściowo niskopodłogowy (%s)" % model, model)
    return _r("unknown", "brak flagi i nieznany typ taboru", model)


def _r(wc: str, basis: str, model: str | None = None) -> dict:
    return {"wheelchair": wc, "wheelchair_text": WC_TEXT[wc], "wheelchair_basis": basis, "vehicle_model": model}
