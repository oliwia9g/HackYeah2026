"""Zgloszenia spolecznosci: problem w terenie z opisem, opcjonalnym zdjeciem, glosami (+/-) i komentarzami.

Zasady (uczciwosc i prywatnosc):
- zgloszenie jest zawsze NIEZWERYFIKOWANE (chyba ze moderator je zaakceptuje) i NIE zmienia samo trasy ani danych o miejscach;
- bez kont i bez danych osobowych: nie zapisujemy adresow IP (glosy pamietamy tylko w pamieci procesu, zeby nie liczyc dwa razy);
- zdjecie: tylko JPEG, ograniczony rozmiar, serwer WYCINA dane EXIF (m.in. wspolrzedne GPS, model telefonu) i inne metadane;
- moderator moze ukryc zgloszenie lub komentarz (np. twarz, tablica rejestracyjna, wulgaryzmy).
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

CATEGORIES = {
    "zastawiony_chodnik": "Zastawiony chodnik",
    "uszkodzona_nawierzchnia": "Uszkodzona nawierzchnia",
    "brak_podjazdu": "Brak podjazdu lub rampy",
    "schody_bez_alternatywy": "Schody bez alternatywy",
    "zepsuta_winda": "Zepsuta winda lub podnośnik",
    "wysoki_kraweznik": "Wysoki krawężnik",
    "remont": "Remont lub wykop",
    "inne": "Inny problem",
}

MAX_PHOTO_BYTES = 2_000_000
MAX_PHOTO_SIDE = 6000
ID_RE = re.compile(r"^[0-9a-f]{8,16}$")


def clean_text(s: str | None, limit: int) -> str:
    """Usuwa znaki sterujace i znaczniki HTML; front i tak wstawia tekst jako tekst, to drugie zabezpieczenie."""
    s = re.sub(r"<[^>]*>", "", s or "")
    s = re.sub(r"[\x00-\x08\x0b-\x1f<>]", "", s)
    return s.strip()[:limit]


def clean_jpeg(data: bytes) -> tuple[bytes, int, int]:
    """Sprawdza, ze to JPEG, wycina metadane (APP1..APP15, komentarze) i zwraca (bajty, szerokosc, wysokosc).
    Rzuca ValueError, gdy plik nie wyglada na poprawny JPEG albo jest zbyt duzy."""
    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError("Zdjęcie jest za duże (limit 2 MB).")
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ValueError("Dozwolone jest tylko zdjęcie w formacie JPEG.")
    out = bytearray(b"\xff\xd8")
    i, w, h = 2, 0, 0
    while i < len(data):
        if data[i] != 0xFF:
            raise ValueError("Uszkodzony plik JPEG.")
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break
        m = data[i]
        i += 1
        if m == 0xD9:
            raise ValueError("Uszkodzony plik JPEG (brak obrazu).")
        if m == 0x01 or 0xD0 <= m <= 0xD7 or m == 0x00:
            continue
        if i + 2 > len(data):
            raise ValueError("Uszkodzony plik JPEG.")
        ln = int.from_bytes(data[i:i + 2], "big")
        if ln < 2 or i + ln > len(data):
            raise ValueError("Uszkodzony plik JPEG.")
        seg = data[i:i + ln]
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if ln < 8:
                raise ValueError("Uszkodzony plik JPEG.")
            h, w = int.from_bytes(seg[3:5], "big"), int.from_bytes(seg[5:7], "big")
            if not (0 < w <= MAX_PHOTO_SIDE and 0 < h <= MAX_PHOTO_SIDE):
                raise ValueError("Nieprawidłowe wymiary zdjęcia.")
        if m == 0xDA:   # poczatek danych obrazu: dalej kopiujemy do ostatniego znacznika konca
            if not w:
                raise ValueError("Uszkodzony plik JPEG.")
            rest = data[i + ln:]
            end = rest.rfind(b"\xff\xd9")
            if end < 0:
                raise ValueError("Uszkodzony plik JPEG (brak końca).")
            out += b"\xff\xda" + seg + rest[:end] + b"\xff\xd9"
            return bytes(out), w, h
        # zostawiamy tylko segmenty potrzebne do wyswietlenia; APP0 (JFIF) zostaje, EXIF/XMP/ICC/komentarze wylatuja
        if m == 0xE0 or not (0xE1 <= m <= 0xEF or m == 0xFE):
            out += bytes([0xFF, m]) + seg
        i += ln
    raise ValueError("Uszkodzony plik JPEG.")


class SignalStore:
    def __init__(self, path: Path, photos_dir: Path):
        self.path, self.photos_dir = Path(path), Path(photos_dir)
        self.items: list[dict] = json.loads(self.path.read_text("utf-8")) if self.path.exists() else []
        self.voters: dict[str, dict[str, str]] = {}   # id zgloszenia -> {klucz klienta: "up"/"down"}; tylko w pamieci

    # ---- zapis ----
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, self.path)

    def get(self, sid: str, include_hidden: bool = False) -> dict | None:
        if not ID_RE.match(sid or ""):
            return None
        s = next((x for x in self.items if x["id"] == sid), None)
        if s is None or (s.get("moderation") == "odrzucone" and not include_hidden):
            return None
        return s

    def add(self, lon: float, lat: float, category: str, description: str, photo: bytes | None = None,
            photo_alt: str | None = None, demo: bool = False) -> dict:
        sid = uuid.uuid4().hex[:10]
        has_photo = False
        if photo:
            self.photos_dir.mkdir(parents=True, exist_ok=True)
            (self.photos_dir / f"{sid}.jpg").write_bytes(photo)
            has_photo = True
        s = {"id": sid, "lon": round(lon, 6), "lat": round(lat, 6), "category": category,
             "description": clean_text(description, 500), "has_photo": has_photo,
             "photo_alt": clean_text(photo_alt, 200) or None, "created_at": datetime.now(timezone.utc).isoformat(),
             "up": 0, "down": 0, "comments": [], "demo": demo}
        self.items.append(s)
        self.save()
        return s

    def photo_path(self, sid: str) -> Path | None:
        s = self.get(sid)
        if not s or not s.get("has_photo"):
            return None
        p = self.photos_dir / f"{sid}.jpg"
        return p if p.exists() else None

    # ---- glosy i komentarze ----
    def vote(self, sid: str, who: str, value: str) -> dict | None:
        s = self.get(sid)
        if s is None:
            return None
        seen = self.voters.setdefault(sid, {})
        prev = seen.get(who)
        if prev == value or (prev is None and value == "none"):
            return s
        if prev:
            s[prev] = max(0, int(s.get(prev, 0)) - 1)
        if value in ("up", "down"):
            s[value] = int(s.get(value, 0)) + 1
            seen[who] = value
        else:
            seen.pop(who, None)
        self.save()
        return s

    def my_vote(self, sid: str, who: str) -> str | None:
        return self.voters.get(sid, {}).get(who)

    def comment(self, sid: str, text: str) -> dict | None:
        s = self.get(sid)
        if s is None:
            return None
        c = {"id": uuid.uuid4().hex[:8], "text": clean_text(text, 300), "created_at": datetime.now(timezone.utc).isoformat()}
        s["comments"].append(c)
        self.save()
        return c

    # ---- widoki publiczne ----
    @staticmethod
    def _status(s: dict) -> tuple[str, str]:
        if s.get("moderation") == "zaakceptowane":
            return "sprawdzone", "Sprawdzone przez moderatora"
        return "niezweryfikowane", "Zgłoszenie społeczności, niezweryfikowane"

    def public(self, s: dict, who: str | None = None, detail: bool = False) -> dict:
        status, status_text = self._status(s)
        visible = [c for c in s.get("comments", []) if c.get("moderation") != "odrzucone"]
        up, down = int(s.get("up", 0)), int(s.get("down", 0))
        out = {"id": s["id"], "category": s["category"], "category_label": CATEGORIES.get(s["category"], s["category"]),
               "description": s["description"], "has_photo": bool(s.get("has_photo")), "created_at": s["created_at"],
               "up": up, "down": down, "comments_count": len(visible), "status": status, "status_text": status_text,
               "questioned": down >= 3 and down > up, "demo": bool(s.get("demo")),
               "lon": s["lon"], "lat": s["lat"]}
        if detail:
            out["photo_url"] = f"/api/signals/{s['id']}/photo" if s.get("has_photo") else None
            out["photo_alt"] = s.get("photo_alt")
            out["comments"] = [{"id": c["id"], "text": c["text"], "created_at": c["created_at"]} for c in visible]
            out["my_vote"] = self.my_vote(s["id"], who) if who else None
        return out

    def collection(self) -> dict:
        feats = []
        for s in self.items:
            if s.get("moderation") == "odrzucone":
                continue
            p = self.public(s)
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]}, "properties": p})
        return {"type": "FeatureCollection", "features": feats, "count": len(feats)}

    def seed_demo(self, spots: list[tuple[float, float]]):
        if any(s.get("demo") for s in self.items) or not spots:
            return
        texts = [("zastawiony_chodnik", "Chodnik zastawiony samochodami, wózkiem nie da się przejść (PRZYKŁADOWE zgłoszenie - dane demo)"),
                 ("brak_podjazdu", "Przy wejściu są stopnie, brak rampy (PRZYKŁADOWE zgłoszenie - dane demo)"),
                 ("uszkodzona_nawierzchnia", "Dziura w nawierzchni przy przejściu (PRZYKŁADOWE zgłoszenie - dane demo)")]
        for (lon, lat), (cat, txt) in zip(spots, texts):
            s = self.add(lon, lat, cat, txt, demo=True)
            s["up"] = 2
        self.save()
