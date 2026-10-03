"""Proste rozumienie polskich polecen glosowych (tekst z rozpoznawania mowy w przegladarce -> intencja).

Rozpoznawanie mowy (STT) i czytanie na glos (TTS) robi przegladarka (Web Speech API, pl-PL), dane osobowe nie opuszczaja
urzadzenia. Backend dostaje juz TEKST. Zwraca intencje, rozpoznane parametry i gotowa odpowiedz do przeczytania.
Nie zgadujemy: gdy czegos nie rozumie, pyta/odpowiada, jak sformulowac polecenie.
"""
from __future__ import annotations

import re

PROFILE_WORDS = {   # fraza -> klucz profilu (dluzsze frazy pierwsze)
    "wozek_dziecko": ["wózkiem z dzieckiem", "wózek z dzieckiem", "wózkiem dziecięcym", "wózek dziecięcy", "z dzieckiem w wózku",
                      "z dzieckiem", "z małym dzieckiem"],
    "wozek_inwalidzki": ["wózkiem inwalidzkim", "wózek inwalidzki", "wózka inwalidzkiego", "na wózku inwalidzkim", "na wózku"],
    "niewidomy_slabowidzacy": ["osoba niewidoma", "osoby niewidomej", "niewidomy", "niewidoma", "niewidomego", "słabowidzący",
                               "słabowidząca", "niedowidzący"],
    "gluchy_niedoslyszacy": ["osoba głucha", "głuchy", "głucha", "niesłyszący", "niedosłyszący", "niedosłysząca"],
    "senior": ["senior", "seniorka", "seniora", "osoba starsza", "starsza osoba"],
    "ciaza": ["w ciąży", "kobieta w ciąży", "ciężarna", "ciąża"],
}
ROUTE_VERBS = r"(?:jak dojść|jak dojechać|jak trafić|dojść|prowadź mnie|prowadź|trasa|wyznacz trasę|znajdź trasę|pokaż trasę|droga)"


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower().replace(",", " ").replace(".", " ")).strip()


def detect_profiles(text: str) -> tuple[list, str]:
    """Zwraca (klucze profili, tekst bez fraz o profilu)."""
    found = []
    for key, words in PROFILE_WORDS.items():
        for w in sorted(words, key=len, reverse=True):
            if w in text:
                found.append(key)
                text = text.replace(w, " ")
                break
    text = re.sub(r"\b(dla|jako|jestem|idę|chcę|proszę|mam)\b", " ", text)
    return found, re.sub(r"\s+", " ", text).strip()


def parse_command(raw: str) -> dict:
    text = _norm(raw)
    if not text:
        return {"intent": "help", "reply": HELP}
    profiles, rest = detect_profiles(text)
    if re.search(r"\b(przystank\w*|tramwaj\w*|autobus\w*|odjazd\w*|komunikacj\w*)\b", rest) and not re.search(r" do ", " " + rest + " "):
        return {"intent": "transit_nearby", "profiles": profiles, "reply": "Sprawdzam najbliższe przystanki i odjazdy."}
    m = re.search(r"(?:^|\b)(?:z|ze|od)\s+(?P<a>.+?)\s+(?:do|na)\s+(?P<b>.+)$", rest)
    if m:
        a, b = m.group("a").strip(), m.group("b").strip()
        a = re.sub(r"^" + ROUTE_VERBS + r"\s+", "", a).strip()
        if a and b:
            return {"intent": "route", "from_q": a, "to_q": b, "profiles": profiles,
                    "reply": f"Wyznaczam trasę z {a} do {b}."}
    m = re.search(r"(?:^|\b)" + ROUTE_VERBS + r"\s+(?:do|na)\s+(?P<b>.+)$", rest) or re.search(r"(?:^|\b)(?:do|na)\s+(?P<b>.+)$", rest)
    if m and m.group("b").strip():
        b = m.group("b").strip()
        return {"intent": "route", "from_q": None, "from_gps": True, "to_q": b, "profiles": profiles,
                "reply": f"Wyznaczam trasę z Twojego położenia do {b}."}
    return {"intent": "help", "profiles": profiles, "reply": HELP}


HELP = ("Nie zrozumiałam polecenia. Możesz powiedzieć na przykład: trasa z Rynku Głównego do Dworca Głównego dla wózka inwalidzkiego, "
        "albo: jak dojść do Plant 5, albo: jakie są przystanki w pobliżu.")
