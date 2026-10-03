# backend: silnik danych i API „Kraków bez barier”

Trasy i karty miejsc dopasowane do potrzeb osób z ograniczeniami (wózek, wózek dziecięcy, niewidomi, głusi, seniorzy, ciąża) lub do własnych preferencji.
Zasada: **każda informacja ma źródło, datę i status; brak danych nigdy nie oznacza „dostępne”; zgłoszenia użytkowników są niezweryfikowane.**

## Start (z katalogu `backend/`)
```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pipeline.run_all                               # pobiera i przetwarza dane (kilkanaście minut)
uvicorn api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
# dokumentacja i klikanie po API:  http://localhost:8000/docs
```
Kroki można też uruchamiać osobno: `fetch_osm`, `fetch_dem`, `fetch_addresses`, `fetch_gtfs`, (opcjonalnie) `fetch_overpass_meta` – patrz `pipeline/run_all.py`.

## Testy
```bash
pip install -r requirements-dev.txt
python -m pytest -q          # 203 testy na danych syntetycznych, bez sieci
```

## Dokumenty
| Plik | Dla kogo | O czym |
|---|---|---|
| `FRONTEND.md` | zespół frontu | co podłączyć do API, słownik wartości, ekrany, lista WCAG, ścieżka demo |
| `ARCHITEKTURA.md` | jury, deweloperzy | architektura, źródła i awarie, jak dodać źródło/kategorię/miasto, hosting i koszty, prywatność, WCAG |
| `BIZNES.md` | jury | model biznesowy, program nalotów dronem, plan od prototypu do usługi, ryzyka |
| `ODBIORCY_I_ADOPCJA.md` | jury, zespół | dla kogo jest aplikacja, scenariusze, jak zachęcić do używania, profil bez konta |
| `STORYTELLING.md` | zespół | opowieść do pokazu, scenariusz filmu (3 min), szkielet 10 slajdów, trudne pytania jury |
| `SOURCES.md` | jury | rejestr źródeł danych (generowany z `sources.yaml`) |

## Inne miasto
`cp cities/TEMPLATE.yaml cities/<miasto>.yaml`, uzupełnij, potem `CITY_CONFIG=cities/<miasto>.yaml python -m pipeline.run_all` i to samo `CITY_CONFIG` przy starcie API.

## Wdrożenie
Na serwerze: ten sam zestaw komend co w „Start” (venv, `pipeline.run_all`, `uvicorn`), najlepiej za reverse proxy z HTTPS. Zmienne: `ADMIN_TOKEN`, `CORS_ORIGINS`, `TRUST_PROXY`, `CITY_CONFIG` (opis w nagłówku `api/main.py` i w `ARCHITEKTURA.md` §4). Pakowanie w kontener jest możliwym kolejnym krokiem (nie jest częścią prototypu).

## Najważniejsze endpointy
`/api/routes` (warianty tras ze znacznikami zagrożeń), `/api/plan` (z komunikacją), `/api/nearest` (najbliższa toaleta/ławka/apteka chodnikami),
`/api/places/{id}` (karta + dopasowanie do wymagań), `/api/reports` (zgłoszenia), `/api/gaps` (gdzie brakuje danych), `/api/stats`, `/api/health`, `/api/sources`,
`/api/export/places` (otwarte dane z proweniencją), `/api/voice/command` (asystent głosowy), `/embed/place/{id}` (karta do osadzenia),
`/api/whereami` (gdzie jestem), `/api/at` (klik w mapę: budynek, adres, udogodnienia i bariery), `/api/catalog` + `/api/catalog/resolve` (dobieranie wymagań), `/api/surveys*` (naloty dronem, świeżość danych),
`/api/profile/schema` + `/api/profile/validate` (profil lokalny bez konta), `routes[].properties.simple` (tryb prosty).
