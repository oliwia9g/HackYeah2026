# backend: silnik danych "Kraków bez barier"

Obszar demo: Stare Miasto + Kazimierz + okolice Dworca Głównego (bbox w `config.yaml`).

## Start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m pipeline.fetch_osm --audit   # 1) najpierw audyt pokrycia tagów (kilka minut)
python -m pipeline.fetch_osm           # 2) pełny eksport do ../hack-yeah-city/public/data/
```

## Co powstaje w `public/data/`

| Plik | Zawartość |
|---|---|
| `edges.geojson` | krawędzie sieci pieszej + tagi (surface, kerb, incline, ...) |
| `pois.geojson` | miejsca (punkty) + tagi dostępności |
| `crossings.geojson` | przejścia, krawężniki, windy, schody |
| `facts.csv/json` | fakty z proweniencją: źródło, licencja, data, pewność, status |
| `audit.json` | pokrycie tagów (gotowy slajd o jakości danych) |

## Kontrakt z frontem

Każdy fakt: `feature_id, attribute, value, source, source_url, license, retrieved_at,
observed_at, confidence, status`. Statusy: `potwierdzone | prawdopodobne | niezweryfikowane |
sprzeczne | brak`. **Brak danych nigdy nie jest pokazywany jako "dostępne".**

## Dalej (kolejność)

1. `fetch_dem.py`: NMT z Geoportalu, nachylenie na krawędzie
2. `fetch_gtfs.py`: przystanki i kursy niskopodłogowe ZTP
3. `engine/routing.py`: koszty per profil z `engine/profiles.py`, trasa + opis tekstowy
4. izochrona, wyspy niedostępności, panel jakości danych
