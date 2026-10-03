"""Rozumienie polskich polecen glosowych (tekst z rozpoznawania mowy w przegladarce -> intencja) dla asystenta glosowego.

Rozpoznawanie mowy (STT) i czytanie na glos (TTS) robi przegladarka (Web Speech API, pl-PL), dane osobowe nie opuszczaja
urzadzenia. Backend dostaje juz TEKST. Zwraca intencje, rozpoznane parametry i gotowa odpowiedz do przeczytania.
Nie zgadujemy: gdy czegos nie rozumie, odpowiada, jak sformulowac polecenie.

Intencje obslugiwane przez serwer (zwracaja `call` do wykonania przez front):
  route            trasa „z X do Y” / „jak dojsc do Y”
  nearest          „najblizsza toaleta / lawka / apteka / winda ...” (albo „jak dojsc do toalety” -> route_to_first)
  where_am_i       „gdzie jestem”, „co jest wokol”
  transit_nearby   „przystanki w poblizu”
  set_profile      „jestem niewidomy”, „bez schodow” - zmiana wymagan (prefs/profiles) bez trasy
Intencje obslugiwane przez front (pole `client_action`, bez wywolania serwera): repeat, next_step, stop, list_hazards,
remaining, confirm, deny, choose (z `index`).
"""
from __future__ import annotations

import re

from engine.profiles import PROFILES

# profil -> wyrazenia regularne (polskie formy fleksyjne); kolejnosc ma znaczenie: wozek dzieciecy PRZED samym "wozek"
PROFILE_PATTERNS = [
    ("wozek_dziecko", [r"wózk\w*\s+(?:z\s+)?dziec\w*", r"wózk\w*\s+dziecięc\w*", r"z\s+(?:małym\s+|malutkim\s+)?dziec\w*",
                       r"z\s+dzieć\w*", r"z\s+niemowl\w*"]),
    ("wozek_inwalidzki", [r"wózk\w*\s+inwalidzk\w*", r"(?:osob\w*\s+)?na\s+wózku", r"(?:dla|z)\s+wózk\w*", r"wózk\w*"]),
    ("niewidomy_slabowidzacy", [r"niewidom\w*", r"słabowidz\w*", r"niedowidz\w*", r"ociemniał\w*"]),
    ("gluchy_niedoslyszacy", [r"głuch\w*", r"niesłysz\w*", r"niedosłysz\w*"]),
    ("senior", [r"senior\w*", r"osob\w*\s+starsz\w*", r"starsz\w*\s+osob\w*", r"emeryt\w*"]),
    ("ciaza", [r"w\s+ciąży", r"ciężarn\w*", r"ciąż\w*"]),
]
# frazy o wymaganiach -> token prefs (tak jak w /api/catalog)
PREF_PATTERNS = [
    (r"bez\s+schod\w*", "nostairs"), (r"niski\w*\s+krawężnik\w*", "kerb"), (r"obniżon\w*\s+krawężnik\w*", "kerb"),
    (r"gładk\w*\s+nawierzchni\w*", "smooth"), (r"(?:unikaj|bez)\s+kostki", "smooth"), (r"dobrze\s+oświetlon\w*", "lit"),
    (r"oświetlon\w*\s+(?:trasa|droga|ulice)", "lit"), (r"z\s+ławkami", "bench:300"), (r"prowadzeni\w*\s+dotykow\w*", "tactile"),
    (r"sygnał\w*\s+dźwiękow\w*", "sound"), (r"dźwiękow\w*\s+sygnaliz\w*", "sound"),
]
# rodzaje udogodnien (klucze jak w NEAREST_KINDS w api/main.py)
KIND_PATTERNS = [
    ("toaleta", r"toalet\w*|ubikacj\w*|\bwc\b"), ("lawka", r"ławk\w*|miejsce\s+do\s+siedzenia|usiąść|odpocząć"),
    ("apteka", r"apte\w*"), ("przychodnia", r"przychodni\w*|lekarz\w*|szpital\w*|pogotowi\w*"),
    ("kawiarnia", r"kawiar\w*|kawę\b|kawa\b"), ("restauracja", r"restaurac\w*|zjeść|jedzeni\w*"),
    ("woda", r"wod[ęay]\s+pitn\w*|woda\s+pitna|napić\s+się"), ("bankomat", r"bankomat\w*"), ("poczta", r"poczt\w*"),
    ("muzeum", r"muze\w*"), ("parking", r"parking\w*"), ("winda", r"wind[aęy]\b|windzie"),
]
ROUTE_VERBS = r"(?:jak dojść|jak dojechać|jak trafić|dojść|prowadź mnie|prowadź|trasa|wyznacz trasę|znajdź trasę|pokaż trasę|droga)"
NEAREST_LEAD = r"(?:najbliższ\w+|gdzie\s+(?:jest|znajdę|mogę\s+znaleźć)|szukam|potrzebuję|czy\s+jest|jest\s+tu|jakaś|jakiś|w\s+pobliżu)"

CLIENT_ACTIONS = [   # (akcja, wzorzec calego polecenia)
    ("repeat", r"(?:powtórz|jeszcze raz|powiedz jeszcze raz|powtórz to|nie zrozumiałem|nie zrozumiałam)"),
    ("next_step", r"(?:dalej|następny krok|następny|co dalej|następna wskazówka)"),
    ("stop", r"(?:stop|przestań|cisza|koniec|anuluj|wystarczy|zamknij się|nie czytaj)"),
    ("list_hazards", r".*\b(?:przeszkod\w*|zagrożeni\w*|uwag\w*|niebezpiecz\w*)\b.*(?:trasie|drodze|po drodze)?.*"),
    ("remaining", r".*(?:ile jeszcze|ile zostało|jak daleko|ile mi zostało).*"),
    ("confirm", r"(?:tak|dobrze|zgoda|ok|okej|potwierdzam|poproszę)"),
    ("deny", r"(?:nie|nie chcę|zmień|inaczej)"),
]
ORDINALS = {"pierwsz": 1, "jeden": 1, "jedynk": 1, "drugi": 2, "dwa": 2, "dwójk": 2, "trzeci": 3, "trzy": 3, "trójk": 3, "czwart": 4, "cztery": 4}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower().replace(",", " ").replace(".", " ").replace("?", " ").replace("!", " ")).strip()


def detect_profiles(text: str) -> tuple[list, str]:
    """Zwraca (klucze profili, tekst bez fraz o profilu)."""
    found, rest, _ = _detect(text)
    return found, rest


def _detect(text: str) -> tuple[list, str, bool]:
    """(profile, tekst bez fraz o profilu, czy zgadujemy). Samo "wózek" bez doprecyzowania = wózek inwalidzki (ostrzejszy profil,
    ktory pokrywa tez wozek dzieciecy) - mowimy to uzytkownikowi w odpowiedzi."""
    found, assumed = [], False
    for key, pats in PROFILE_PATTERNS:
        for pat in pats:
            m = re.search(r"\b(?:(?:na|z|ze|dla)\s+)?" + pat + r"\b", text)   # razem z przyimkiem, zeby nie zostawal w tekscie
            if m:
                found.append(key)
                assumed = assumed or (key == "wozek_inwalidzki" and "inwalidzk" not in m.group(0) and "na wózku" not in m.group(0))
                text = text[: m.start()] + " " + text[m.end():]
                break
    text = re.sub(r"\b(dla|jako|jestem|idę|chcę|proszę|mam|osoby|osoba|osobę|osób|się|poruszam)\b", " ", text)
    return found, re.sub(r"\s+", " ", text).strip(), assumed


def _detect_prefs(text: str) -> tuple[list, str]:
    found = []
    for pat, token in PREF_PATTERNS:
        m = re.search(r"\b" + pat, text)
        if m:
            if token not in found:
                found.append(token)
            text = text[: m.start()] + " " + text[m.end():]
    return found, re.sub(r"\s+", " ", text).strip()


def _kind_of(text: str) -> str | None:
    for key, pat in KIND_PATTERNS:
        if re.search(r"(?<!\w)(?:" + pat + r")", text):
            return key
    return None


def _only_kind(text: str) -> str | None:
    """Gdy cale „dokad” to tylko rodzaj udogodnienia („do toalety”), zwraca klucz rodzaju."""
    for key, pat in KIND_PATTERNS:
        if re.fullmatch(r"(?:najbliższ\w+\s+)?(?:" + pat + r")", text.strip()):
            return key
    return None


ASSUME_WHEELCHAIR = "Zakładam wózek inwalidzki; jeśli chodzi o wózek dziecięcy, powiedz: z wózkiem dziecięcym."
HELP = ("Nie zrozumiałam polecenia. Możesz powiedzieć na przykład: trasa z Rynku Głównego do Dworca Głównego dla wózka inwalidzkiego, "
        "albo: jak dojść do Plant 5, albo: gdzie jest najbliższa toaleta, albo: gdzie jestem, albo: jakie są przystanki w pobliżu.")


def parse_command(raw: str) -> dict:
    text = _norm(raw)
    if not text:
        return {"intent": "help", "reply": HELP}
    # --- polecenia dla frontu (kontekst rozmowy jest po stronie frontu) ---
    route_form = re.search(r"\b(?:z|ze|od)\s+.+?\s+(?:do|na)\s", text + " ")
    for action, pat in CLIENT_ACTIONS:
        if re.fullmatch(pat, text) and not (action in ("list_hazards", "remaining") and route_form):
            return {"intent": action, "client_action": action, "reply": ""}
    m = re.fullmatch(r"(?:ten\s+|numer\s+|opcja\s+|wariant\s+)?(\w+)(?:\s+proszę)?", text)
    if m:
        w = m.group(1)
        idx = int(w) if w.isdigit() else next((v for k, v in ORDINALS.items() if w.startswith(k)), None)
        if idx and idx <= 9:
            return {"intent": "choose", "client_action": "choose", "index": idx, "reply": ""}

    if re.search(r"\b(?:gdzie\s+jestem|gdzie\s+się\s+znajduję|na\s+jakiej\s+ulicy|jaka\s+to\s+ulica|co\s+(?:jest\s+)?(?:wokół|obok|dookoła)|co\s+tu\s+jest)\b", text):
        return {"intent": "where_am_i", "profiles": _detect(text)[0], "prefs": "", "assumed": None, "reply": "Sprawdzam, gdzie jesteś."}
    profiles, rest, assumed = _detect(text)
    prefs, rest = _detect_prefs(rest)
    note = ASSUME_WHEELCHAIR if assumed else None
    base = {"profiles": profiles, "prefs": ",".join(prefs), "assumed": note}

    if re.search(r"\b(przystank\w*|tramwaj\w*|autobus\w*|odjazd\w*|komunikacj\w*)\b", rest) and not re.search(r" do ", " " + rest + " "):
        return {**base, "intent": "transit_nearby", "reply": "Sprawdzam najbliższe przystanki i odjazdy."}

    # --- najblizsze udogodnienie: „gdzie jest najbliższa toaleta”, „potrzebuję ławki” ---
    kind = _kind_of(rest)
    has_route_form = re.search(r"(?:^|\b)(?:z|ze|od)\s+.+?\s+(?:do|na)\s+", rest)
    if kind and not has_route_form and re.search(NEAREST_LEAD, rest) and not re.search(r"\b(?:do|na)\s+\w", rest):
        return {**base, "intent": "nearest", "kind": kind, "reply": f"Szukam najbliższego miejsca: {kind}."}

    m = re.search(r"(?:^|\b)(?:z|ze|od)\s+(?P<a>.+?)\s+(?:do|na)\s+(?P<b>.+)$", rest)
    if m:
        a, b = m.group("a").strip(), m.group("b").strip()
        a = re.sub(r"^" + ROUTE_VERBS + r"\s+", "", a).strip()
        if a and b:
            return {**base, "intent": "route", "from_q": a, "to_q": b,
                    "reply": f"Wyznaczam trasę z {a} do {b}." + (" " + note if note else "")}
    m = re.search(r"(?:^|\b)" + ROUTE_VERBS + r"\s+(?:do|na)\s+(?P<b>.+)$", rest) or re.search(r"(?:^|\b)(?:do|na)\s+(?P<b>.+)$", rest)
    if m and m.group("b").strip():
        b = m.group("b").strip()
        k = _only_kind(b)
        if k:   # „jak dojść do toalety” = najblizsza toaleta + trasa do niej
            return {**base, "intent": "nearest", "kind": k, "route_to_first": True,
                    "reply": f"Szukam najbliższego miejsca ({k}) i wyznaczę trasę."}
        return {**base, "intent": "route", "from_q": None, "from_gps": True, "to_q": b,
                "reply": f"Wyznaczam trasę z Twojego położenia do {b}." + (" " + note if note else "")}

    # --- sama zmiana wymagan: „jestem niewidomy”, „bez schodów” ---
    if profiles or prefs:
        names = [PROFILES[k]["label"].lower() for k in profiles] + (["własne wymagania"] if prefs else [])
        return {**base, "intent": "set_profile", "reply": "Ustawiam: " + ", ".join(names) + "." + (" " + note if note else "")}
    return {"intent": "help", "profiles": profiles, "prefs": "", "reply": HELP}
