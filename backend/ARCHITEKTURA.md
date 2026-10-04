# Architektura, dane, wdrożenie i bezpieczeństwo

Dokument odpowiada na pytania z briefu: jak jest zbudowane rozwiązanie, skąd bierzemy dane i co robimy, gdy źródło padnie,
jak dodać źródło / kategorię / obszar / miasto, gdzie to hostować i ile kosztuje, jak chronimy prywatność oraz co z dostępnością (WCAG).
Rzeczy niesprawdzone albo będące szacunkiem są oznaczone **[założenie]** lub **[niesprawdzone]**.

## 1. Podział: pobieranie danych oddzielone od prezentacji

```
 ŹRÓDŁA ZEWNĘTRZNE                 WARSTWA POBIERANIA (offline, cron)               WARSTWA PREZENTACJI (online)
 ┌────────────────────┐            ┌─────────────────────────────┐                  ┌────────────────────────────┐
 │ OpenStreetMap      │──Overpass─▶│ pipeline/fetch_osm          │─┐                │ api/main.py  (FastAPI)     │
 │ Overpass (meta)    │───────────▶│ pipeline/fetch_overpass_meta│ │ pliki:         │  /api/routes /plan /nearest│
 │ GUGiK NMT (WCS)    │───────────▶│ pipeline/fetch_dem          │ ├─▶ data/raw/*   │  /api/places /gaps /export │
 │ Adresy (OSM)       │───────────▶│ pipeline/fetch_addresses    │ │   public/data/ │  /api/reports /admin/...   │
 │ ZTP GTFS (rozkład) │───────────▶│ pipeline/fetch_gtfs         │─┘   *.geojson    │  /api/health /stats /sources│
 │ ZTP GTFS-Realtime  │──── na żywo, bez zapisu, cache 20 s ─────────────────────────▶│ engine/ (routing, profile, │
 │ MPK / TTSS (tabor) │─ ręczny CSV engine/data/tram_fleet.csv ───────────────────────▶│  fleet, realtime, voice…)  │
 └────────────────────┘            └─────────────────────────────┘     facts.json    └─────────────┬──────────────┘
                                          pipeline/run_all.py                                       │ JSON / GeoJSON
                                                                                       ┌────────────▼──────────────┐
                                                                                       │ Front (hack-yeah-city)    │
                                                                                       │ + /embed/place/{id} (HTML)│
                                                                                       └───────────────────────────┘
```

- **Pobieranie** (`pipeline/`): skrypty uruchamiane ręcznie lub z crona (`python -m pipeline.run_all`). Każdy zapisuje pliki i **nie zna API**.
  Wspólny format faktów (`facts.json/csv`): `feature_id, attribute, value, source, source_url, license, retrieved_at, observed_at, confidence, status`.
- **Prezentacja** (`api/`, `engine/`): API przy starcie wczytuje pliki do pamięci i nie woła zewnętrznych usług poza GTFS-Realtime.
  Awaria Overpass, GUGiK czy portalu ZTP nie wyłącza aplikacji, bo działa na ostatnio zapisanych danych.
- **Front** czyta tylko API i statyczne GeoJSON-y; nie zna żadnego źródła zewnętrznego.

### Model zaufania do danych (sedno wiarygodności)
Każda informacja ma źródło, datę, pewność i status: `potwierdzone | prawdopodobne | niezweryfikowane | sprzeczne | brak`.
- Brak tagu w źródle = `brak` („brak danych”), **nigdy** „dostępne”.
- Data ostatniej edycji obiektu w OSM jest oznaczona osobno (`observed_basis = last_edit`) i daje słabszy status niż `check_date`.
- Zgłoszenie użytkownika jest zawsze `niezweryfikowane`, widoczne obok danych ze źródła. Gdy mówi co innego niż źródło: status `sprzeczne`, obie wersje na karcie.
  Moderator (`ADMIN_TOKEN`) może zgłoszenie zaakceptować (`potwierdzone`) albo odrzucić.
- Dostępność **pojazdu** (autobus/tramwaj) jest osobno od dostępności **przystanku**; przystanki zawsze „brak danych”, bo ZTP nie publikuje ich dostępności.
  Pojazd: `yes` (dwa źródła zgodne), `likely` (deklaracja przewoźnika), `unknown`, `no`, `conflict` (źródła się wykluczają). Podstawa jest w `wheelchair_basis`.
- Poprawa błędnych/nieaktualnych danych: (1) zgłoszenie w aplikacji, (2) linki `osm_edit_url` / `osm_note_url` przy każdym miejscu – poprawka w OSM trafia do wszystkich użytkowników OSM,
  (3) `GET /api/gaps` wskazuje, gdzie poprawka jest najpotrzebniejsza.

## 2. Dane miejskie: konkretne zbiory, częstotliwość, awarie

| Źródło | Co bierzemy | Jak często odświeżamy | Gdy źródło nie działa |
|---|---|---|---|
| OpenStreetMap przez Overpass (`fetch_osm`) | sieć piesza, miejsca (POI), przejścia, krawężniki, tagi dostępności | **[założenie]** raz na dobę lub tydzień (cron) | API działa na ostatnich plikach; `retrieved_at` widoczne w każdym fakcie; baner o danych zapisanych (`store.outage`); `fetch_osm` próbuje 4 serwerów Overpass |
| Overpass `out meta` (`fetch_overpass_meta`) | data ostatniej edycji obiektu | z pobraniem OSM; krok **opcjonalny** | brak pliku = obiekty bez daty edycji, nic się nie psuje |
| GUGiK NMT (WCS) | nachylenie chodników | rzadko (model terenu zmienia się latami) **[założenie]** co rok | nachylenie z ostatniego pliku; źródło nachylenia zapisane przy każdej krawędzi |
| ZTP GTFS statyczny | przystanki, rozkład | codziennie (ZTP aktualizuje pliki codziennie) | ostatni zapisany rozkład; `generated_at` w `/api/health` |
| ZTP GTFS-Realtime | prognozy przyjazdów, numer i flaga pojazdu | na żądanie, cache 20 s | do 10 min stary cache oznaczony `stale`; potem komunikat „tylko rozkład” (trasy i plan działają bez live) |
| Wykaz taboru (TTSS) i deklaracja MPK | typ taboru tramwajów; autobusy niskopodłogowe | ręcznie, gdy zmieni się flota **[założenie]** co kwartał | brak = `unknown`, nigdy `yes` |
| Obrysy budynków OSM (`buildings.geojson`, krok w `fetch_osm`) | wielokąty budynków, adres z tagów `addr:*`, tagi dostępności budynków spoza listy POI | z pobraniem OSM | brak pliku = klik zwraca najbliższy obiekt i najbliższy adres (oznaczony jako przybliżony) |
| Naloty dronem / kontrole terenowe (`surveys.yaml`, `data/raw/survey_observations.json`) | data ostatniego sprawdzenia terenu, obserwacje (zastawiony chodnik, remont, zniszczona nawierzchnia, wąski chodnik) | co **3 miesiące** (`interval_months`), po nalocie ręcznie: wpis + `python -m pipeline.import_survey` | brak wpisu = „brak nalotu” (aplikacja nie udaje świeżości); dane starsze niż interwał oznaczone jako nieświeże |
| Zgłoszenia użytkowników | wersje atrybutów | na bieżąco | zapis do pliku JSON (prototyp); w produkcji baza |

Monitoring: `GET /api/health` (stan każdego źródła, wiek cache), `GET /api/stats` (pokrycie i świeżość danych), `GET /api/sources` (rejestr źródeł z licencją i statusem jej weryfikacji).
Symulacja awarii do pokazu: `POST /api/dev/outage {"on": true}` (wyłączane na produkcji przez `HACKYEAH_DEV=0`).

**Licencje do potwierdzenia przed wdrożeniem komercyjnym** (otwarte w `sources.yaml`, `license_status: do_potwierdzenia`): ZTP GTFS/GTFS-RT, strona MPK jako źródło deklaracji, wykaz taboru TTSS, adresy/PRG.
OSM wymaga atrybucji i share-alike dla publicznie udostępnianej bazy pochodnej (ODbL) – eksport `/api/export/places` niesie atrybucję.

## 3. Jak coś dodać

**Nowe źródło danych o dostępności** (np. portal miejski, audyty):
1. Dopisz wpis w `sources.yaml` (licencja, aktualność, jak weryfikujemy, ograniczenia). `python -m pipeline.make_sources_doc` odświeży `SOURCES.md`.
2. Napisz `pipeline/fetch_<zrodlo>.py`, który zapisuje **wiersze w tym samym formacie faktów** (patrz wyżej) do `facts.json`. Nic w API nie trzeba zmieniać: karta miejsca, sprzeczności i eksport biorą wszystkie fakty o danym `feature_id`.
3. Dodaj krok do `pipeline/run_all.py` (lista `STEPS`).

**Nowy nalot dronem lub kontrola terenowa** (co kwartał):
1. Dopisz wpis w `surveys.yaml` (`id`, `type: dron|spacer_terenowy|audyt`, `status`, `date`, `next_planned`, `area` = ścieżka do GeoJSON z wielokątem nalotu albo `null` dla całego obszaru, `method`, `covers`, `does_not_cover`). Wpis przykładowy ma `demo: true` i jest tak podpisany w aplikacji; zastąp go prawdziwym albo usuń.
2. Obserwacje: CSV (`surveys/TEMPLATE_obserwacje.csv`: `lon,lat,type,text`) → `python -m pipeline.import_survey obserwacje.csv --survey <id>`. Punkty poza obszarem demo są odrzucane; ponowny import tego samego nalotu zastępuje poprzednie obserwacje.
3. Restart API. Aplikacja pokazuje „ostatni nalot”, świeżość, pokrycie trasy i obserwacje przy trasie (`/api/surveys`, `/api/surveys/at`, `/api/surveys/observations`, `meta.ostatni_nalot`, `routes[].properties.nalot`). Obserwacje **nie zmieniają wyboru trasy**, tylko dodają ostrzeżenia z datą.
**Uwaga prawna/organizacyjna dla lotów:** patrz `BIZNES.md` §5 (lista „do zweryfikowania”: uprawnienia, strefy lotnicze w Krakowie, loty nad ludźmi, RODO). **[niesprawdzone]**

**Nowa kategoria obiektów lub atrybut:** `config.yaml` → `osm.poi_tags` (co pobieramy) i `osm.fact_attributes` (jakie tagi stają się faktami); w `api/main.py` dopisz etykietę w `ATTR_LABELS` i, jeśli chcesz wyszukiwać „najbliższą …”, wpis w `NEAREST_KINDS`.

**Nowy obszar w tym mieście:** podmień wielokąt `aoi/AOI_srodmiescie.geojson` (dowolny CRS zapisany w pliku) i uruchom `python -m pipeline.run_all`.

**Nowe miasto:**
```
cp cities/TEMPLATE.yaml cities/wroclaw.yaml        # uzupełnij: aoi, nazwa, adresy GTFS (jeśli są), katalogi danych
CITY_CONFIG=cities/wroclaw.yaml python -m pipeline.run_all
CITY_CONFIG=cities/wroclaw.yaml uvicorn api.main:create_app --factory --port 8000
```
Część piesza (OSM + NMT) jest niezależna od miasta w Polsce. Część komunikacji zależy od operatora: adresy GTFS są w konfiguracji, ale `engine/fleet.py`
(klasyfikacja taboru MPK/TTSS) jest adapterem **krakowskim**; dla innego miasta bez własnego adaptera pojazdy mają `unknown` (to bezpieczne wartości domyślne). **[niesprawdzone]** na drugim mieście.

## 4. Wdrożenie, własność i koszty (poza infrastrukturą UMK)

- **Uruchomienie:** zwykły proces Pythona (venv + `uvicorn`), dane w katalogu `data/`. Pakowanie w kontener to możliwy kolejny krok po prototypie (nie jest jego częścią).
- **Front:** statyczne pliki (Vite build) na dowolnym hostingu statycznym/CDN; adres API w jednej zmiennej.
- **Gdzie:** mały serwer VPS lub PaaS w UE, konto należące do podmiotu prowadzącego projekt (stowarzyszenie/spółka/zespół), a nie do urzędu. Dane i kod są otwarte i przenośne, więc miasto może przejąć hosting bez migracji.
- **Koszty [założenie, szacunek rzędu wielkości; sprawdzić aktualne cenniki]:** VPS 2 vCPU / 4 GB: ok. 5–15 € miesięcznie; domena: kilkadziesiąt zł rocznie; hosting statyczny: 0 € na darmowych planach; kopia zapasowa/monitoring: 0–5 € miesięcznie.
  Największy ukryty koszt to **praca ludzka**: moderacja zgłoszeń i audyty terenowe, nie serwery (patrz `BIZNES.md`).
- **Skala:** siatka i miejsca są w pamięci procesu. Dla Śródmieścia to niewiele; dla całego Krakowa trzeba **zmierzyć** zużycie RAM i czas startu **[niesprawdzone]**.
  Skalowanie poziome: API jest bezstanowe poza (a) zgłoszeniami w pliku i (b) licznikami limitów w pamięci – w produkcji: PostgreSQL/PostGIS dla zgłoszeń, Redis dla limitów, kilka replik za load balancerem.
- **Zmienne środowiskowe:** `ADMIN_TOKEN`, `CORS_ORIGINS`, `TRUST_PROXY`, `CITY_CONFIG`, `DATA_RAW_DIR`, `DATA_OUT_DIR`, `REPORTS_PATH`, `SIGNALS_PATH` i `PHOTOS_DIR` (zgłoszenia społeczności i ich zdjęcia, też na wolumen), `HACKYEAH_DEV=0` (opis w nagłówku `api/main.py`).

## 5. Prywatność i bezpieczeństwo

**Prywatność (privacy by design):**
- Brak kont, rejestracji i pytań o niepełnosprawność. Zamiast „kim jesteś” użytkownik podaje **parametry** (`prefs`: bez schodów, maks. nachylenie, min. szerokość…); nazwy grup (wózek, senior…) są tylko skrótami do gotowych zestawów parametrów.
  Wyniki zależą od parametrów, nie od deklaracji zdrowotnej.
- Pozycja GPS zostaje w przeglądarce; do API trafiają tylko współrzędne zapytania. Rozpoznawanie i czytanie mowy robi przeglądarka (Web Speech API); backend dostaje tekst.
- Zapytania zawierają współrzędne w adresie URL, dlatego na serwerze produkcyjnym uruchamiamy `uvicorn` z `--no-access-log`. Nie zapisujemy adresów IP; w pamięci trzymany jest tylko licznik do limitu zgłoszeń (znika po restarcie).
- Zgłoszenia nie zawierają danych osobowych (miejsce, atrybut, wartość, krótki komentarz bez znaczników).
- **Konto opcjonalne = plik na urządzeniu.** Domyślnie przeglądanie jest anonimowe. Użytkownik może zapisać profil (grupa, włączone/wyłączone udogodnienia, tryb interfejsu, ulubione miejsca) w pamięci przeglądarki i pobrać go jako plik JSON. Serwer ma tylko dwa bezstanowe endpointy: `GET /api/profile/schema` i `POST /api/profile/validate` (sprawdza i normalizuje plik; **nic nie zapisuje**, test `test_server_keeps_no_trace_of_the_profile`). Powód: wymagania dostępnościowe to dane o zdrowiu (RODO art. 9) – najbezpieczniej ich nie zbierać.
- **Lokalizacja:** pozycja pochodzi z urządzenia (Geolocation API) po kliknięciu użytkownika, trafia do API jako zwykłe parametry zapytania (`/api/whereami`, trasy, `nearest`) i **nie jest zapisywana** po stronie serwera. Dlatego `--no-access-log` na serwerze produkcyjnym jest ważne (współrzędne są w adresie URL).
- **Naloty dronem:** w API trafiają wyłącznie wektorowe obserwacje (punkt, typ, krótki opis), bez zdjęć. Surowe materiały (twarze, tablice rejestracyjne) trzymamy poza repozytorium i krótko **[do uzgodnienia: RODO, okres przechowywania]**.
- **[do zrobienia]** polityka prywatności na stronie, informacja o przetwarzaniu mowy przez przeglądarkę (może korzystać z usługi dostawcy przeglądarki).

**Bezpieczeństwo (zrobione):** walidacja wejścia (pydantic, limity długości, zakresy, białe listy atrybutów i profili); czyszczenie znaczników z komentarzy i `html.escape` w stronie osadzanej;
nagłówki `X-Content-Type-Options`, `Referrer-Policy`, `Cache-Control: no-store` dla API; CSP bez skryptów dla `/embed` (`frame-ancestors *` świadomie, bo to widżet do osadzania);
limit zgłoszeń na adres (10/h) i potwierdzeń (30/h); CORS ograniczany zmienną `CORS_ORIGINS`; moderacja wyłączona, dopóki serwer nie ma `ADMIN_TOKEN` (wtedy 404);
endpointy `/api/dev/*` wyłączane na produkcji. Zgłoszenia nigdy nie nadpisują danych źródłowych.

**[do zrobienia]:** limity na poziomie reverse proxy (ochrona przed DoS), HTTPS (terminacja na proxy), przypięcie wersji zależności (`pip freeze`), `pip-audit`, rotacja `ADMIN_TOKEN`, kopie zapasowe zgłoszeń, rejestr zmian moderacji.

## 6. Zależności, licencje, przenośność
Python 3.12+: osmnx, geopandas, shapely, networkx, pandas, numpy, rasterio, pyproj, requests, PyYAML, gtfs-realtime-bindings, FastAPI, pydantic, uvicorn, httpx (testy), pytest (testy).
Wszystkie to biblioteki open source o licencjach typu MIT/BSD/Apache (wg naszej wiedzy; **zweryfikuj**: `pip install pip-licenses && pip-licenses`).
Brak zależności od usług chmurowych jednego dostawcy: dane to GeoJSON/CSV/JSON i standardowy GTFS; API to zwykły proces HTTP. Wyjście z prototypu = przeniesienie kontenera i wolumenu.

## 7. Dostępność (WCAG 2.2 AA): co zrobione, co do zrobienia
Backend daje **materiał** dostępny z założenia, front musi go poprawnie wyświetlić. Pełna lista kontrolna dla frontu: `FRONTEND.md` §4.

| Obszar | Zrobione po stronie backendu | Do zrobienia (front / następny etap) |
|---|---|---|
| Tekstowa alternatywa dla mapy (1.1.1) | trasa jako lista kroków w tekście, lista zagrożeń z odległościami, `GET /api/nearest`, `GET /embed/place/{id}` – strona HTML bez JS | wyświetlić listę obok mapy jako widok podstawowy |
| Nie tylko kolor (1.4.1) | każda waga zagrożenia i status ma nazwę tekstową (`severity`, `status`, `*_text`) | ikony + kształty obok koloru |
| Czytnik ekranu (4.1.2) | gotowe zdania w `spoken` i `narration`; semantyczny HTML w `/embed` (nagłówki, tabela, `lang`) | role i etykiety ARIA, regiony `aria-live` |
| Klawiatura, fokus (2.1.1, 2.4.7, 2.4.11) | – | pełna obsługa bez myszy, widoczny fokus, fokus niezasłonięty |
| Kontrast, powiększenie (1.4.3, 1.4.4, 1.4.10) | `/embed`: kolory tekstu policzone ręcznie wzorem WCAG – jasny motyw 8,0–17,4:1, ciemny 10,4–16,0:1 (wymóg AA: 4,5:1); ciemny motyw wg `prefers-color-scheme` | motyw wysokiego kontrastu, skalowanie do 200% |
| Rozmiar celu (2.5.8) | – | cele dotykowe ≥ 24 px (zalecane 44 px) |
| Alternatywa dla przeciągania mapy (2.5.7) | wybór punktów przez adres/nazwę (`/api/geocode`), głos | przyciski przesuwania/zoomu mapy |
| Głos wejście/wyjście | `GET /api/voice/command` (polskie polecenia), `narration` z odległością zapowiedzi | przycisk mikrofonu, czytanie przez SpeechSynthesis, pole tekstowe jako alternatywa |
| Prosty język (3.1.5) | komunikaty krótkie, bez żargonu; brak danych opisany wprost | przegląd tekstów interfejsu |
| Prosty język i tryb prosty (3.1.5) | `properties.simple`: jedno zdanie na krok, kierunek skrętu, ostrzeżenie w osobnym polu (nie tylko kolor), parametr `simple_steps`; `spoken_summary` do czytania na głos | wielkie kafelki, tekst ≥ 20 px, tryb skupienia bez animacji (`FRONTEND.md` §10) |
| Lokalizacja (3.3.x, 2.2.1) | `/api/whereami` z komunikatem o niedokładności i o obszarze bez danych, bez limitów czasu | zgoda po kliknięciu, ręczna alternatywa (`FRONTEND.md` §12) |
| Spójna pomoc (3.2.6), błędy (3.3.1) | błędy 422 z podpowiedzią co poprawić (`dostepne_preferencje`) | wyświetlanie błędów obok pola |

Audyt narzędziowy (axe/Lighthouse) i test z czytnikiem NVDA/VoiceOver **nie zostały jeszcze wykonane [niesprawdzone]**.

## 8. Testy
`python -m pytest -q` – 203 testy na danych syntetycznych, bez sieci i bez plików z `data/raw` (routing i przeszkody, preferencje i katalog, polecenia głosowe z dopytywaniem i odmianą nazw, „gdzie jestem” i geokodowanie odwrotne, tryb prosty,
profil lokalny, budynki i toalety, naloty dronem, flota i GTFS-RT, plan z komunikacją, zgłoszenia/moderacja, karta miejsca, braki danych, eksport, zdrowie systemu, konfiguracja miasta, panel scenariuszy demo).
Szablon CI: `ci/backend-tests.yml`. **Niesprawdzone na żywych danych:** pełny przebieg `run_all` na nowym AOI (w tym nowe tagi budynków), integracja z żywym GTFS-RT w produkcji, wydajność przy całym mieście.

## 9. Znane ograniczenia (uczciwie)
- Dane OSM o krawężnikach, szerokości drzwi i ławkach są ubogie; to luka danych, którą pokazujemy zamiast ją ukrywać (`/api/stats`, `/api/kerbs`, `/api/gaps`).
- Klasyfikacja taboru tramwajowego (niska/wysoka podłoga) wymaga potwierdzenia przez MPK; wpis `conflict` pokaże się dopiero, gdy ZTP i typ taboru się rozjadą.
- Plan z komunikacją: tylko jeden przejazd (bez przesiadek) w obszarze demo.
- Nachylenie z NMT opisuje teren, nie sam chodnik; krótkie odcinki (<10 m) traktujemy jako niepewne.
- Prototyp trzyma zgłoszenia w pliku JSON: do jednej instancji.
- Naloty: w repozytorium jest jeden wpis **przykładowy** (`demo: true`). Mechanizm jest przetestowany, ale prawdziwy nalot wymaga sprawdzenia przepisów i zgód (`BIZNES.md` §5). Dron nie widzi szerokości drzwi, stopni pod zadaszeniem ani wnętrz; aplikacja pokazuje to użytkownikowi.
- Budynki i toalety: nowe tagi (winda, rampa, toaleta, `building=*`) w `config.yaml` nie były sprawdzone na żywym Overpass; w OSM większość budynków nie ma tych tagów, więc w wielu miejscach zobaczymy „brak danych” (to uczciwy obraz, nie błąd).
- Klik w budynek (`/api/at`): adres budynku pochodzi z tagów OSM albo z punktu adresowego w obrysie; gdy ich brak, podajemy najbliższy adres i **oznaczamy go jako przybliżony**. Pobieranie wszystkich obrysów budynków nie było sprawdzone na żywym Overpass (rozmiar `buildings.geojson` do zmierzenia).
- Tryb prosty: kierunek skrętu liczony z geometrii trasy (przy bardzo krótkich odcinkach tekst brzmi po prostu „Idź…”); nie jest to nawigacja zakręt po zakręcie.
- Asystent głosowy: tylko język polski, proste reguły (nie model językowy); przy nietypowych sformułowaniach odpowiada podpowiedzią. Wymaga przeglądarki z Web Speech API (pole tekstowe jako zapas).
