# Front: co podłączyć do API (Kraków bez barier)

Dla: Mikołaj, Krzysztof. Backend: `uvicorn api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload` (w Codespaces port 8000 ustaw na **Public**).
Pełna lista parametrów z możliwością klikania: **`<API>/docs`** (Swagger). Adres API trzymajcie w jednej zmiennej (`VITE_API` albo podobnie).
Dane statyczne warstw leżą w `hack-yeah-city/public/data/*.geojson` (po `git pull` na `main`).

**Co nowego w tej wersji (zaznaczone 🆕 poniżej):** własne preferencje zamiast nazw grup (`prefs`), „najbliższa toaleta/ławka/apteka…” chodnikami, werdykt „czy to miejsce pasuje do moich wymagań” (`fit`),
potwierdzanie zgłoszeń i linki „popraw w OpenStreetMap”, ekran „o danych” (`/api/stats`), „pomóż uzupełnić dane” (`/api/gaps`), osadzalna karta miejsca (`/embed/place/...`), eksport otwartych danych, panel scenariuszy demo, stan systemu (`/api/health`).

**🆕🆕 Dodane w ostatniej rundzie (sekcje 10–16 na dole, czytajcie je w tej kolejności):**
tryb **prosty** („dla babci”) i tryb **skupienia** (np. ADHD) z gotowymi krokami trasy w `properties.simple` (§10); **asystent głosowy** dla niewidomych z dopytywaniem i „jak dojść do toalety” (§11);
**lokalizacja** urządzenia i „gdzie jestem” (§12); **profil lokalny** = konto bez konta, plik na urządzeniu (§13); ekran **„Moje wymagania”** z dobieraniem i usuwaniem udogodnień/barier przy sztywnych 6 grupach (§14);
**budynki i toalety** (winda, rampa, toaleta; §15); **nalot dronem** i widoczna świeżość danych (§16); **klik w budynek → adres, udogodnienia, bariery** (§17, `GET /api/at`).

## 0. Zasady, które front musi respektować (wymóg briefu)
1. **Brak danych nigdy nie znaczy „dostępne”.** Pokazujcie tekst z API (`*_text`, `summary.text`, `wheelchair_basis`, `fit.text`) dosłownie, nie przerabiajcie na zielony ptaszek.
2. **Każdy fakt ma źródło, datę i status.** Na karcie pokażcie `source`, `observed_at`/`retrieved_at`, `status`. Zgłoszenia użytkowników są zawsze **niezweryfikowane**, dopóki moderator ich nie zaakceptuje.
3. **Informacja nie może zależeć tylko od koloru** (WCAG): zawsze ikona + tekst.
4. Stopka z atrybucją: `atrybucja` z odpowiedzi (OSM ODbL, GUGiK, ZTP). Link do `/api/sources`.
5. **Domyślnie anonimowo, bez kont na serwerze.** Opcjonalny „profil” to plik na urządzeniu użytkownika (§13). Pozycja GPS zostaje w przeglądarce (do API wysyłamy tylko współrzędne zapytania, §12). 🆕 **Nie pytajcie „jaką masz niepełnosprawność”** – pytajcie o to, **czego użytkownik potrzebuje** (sekcja 2, punkt 1, i §14). Sześć grup (`profiles`) jest stałych; nie dodawajcie własnych kategorii ludzi, tylko pozwólcie dobrać pozycje (§14).

## 1. Słownik wartości (stabilny)
**Profile** (skróty; `profiles=` w zapytaniach, można kilka po przecinku): `wozek_inwalidzki`, `wozek_dziecko`, `niewidomy_slabowidzacy`, `gluchy_niedoslyszacy`, `senior`, `ciaza`. Etykiety: `GET /api/meta`.

🆕 **Preferencje** (`prefs=` we wszystkich zapytaniach o trasę, plan, izochronę, najbliższe, kartę miejsca; można razem z `profiles`): tokeny po przecinku, np. `prefs=nostairs,incline:6,width:0.9,kerb,bench:300`.
Lista i opisy: `GET /api/meta` → `preferencje`.
| token | znaczenie | kontrolka |
|---|---|---|
| `nostairs` | bez schodów | przełącznik |
| `incline:N` | maks. nachylenie w % (1–15) | suwak |
| `width:M` | min. szerokość przejścia w m (0,5–1,5) | suwak |
| `kerb` | tylko obniżone/zrównane krawężniki | przełącznik |
| `smooth` | unikaj kostki i nierównej nawierzchni | przełącznik |
| `tactile` / `sound` / `lit` | prowadzenie dotykowe / sygnał dźwiękowy / oświetlenie | przełączniki |
| `bench:M` | ławka co najwyżej co M m (100–1000) | suwak |
| `speed:V` | tempo marszu km/h (2–6) | suwak |
Zły token → `422` z `detail.dostepne_preferencje` (słownik token → opis).

**Status faktu / odcinka** (`status`): `potwierdzone` ✓, `prawdopodobne` ~, `niezweryfikowane` ?, `sprzeczne` ⚠, `brak` – (brak danych). Zawsze: ikona + słowo.

**`wheelchair` pojazdu** (autobus/tramwaj; zawsze razem z `wheelchair_text` i `wheelchair_basis`):
| wartość | pokaż jako |
|---|---|
| `yes` | „Dostępny” (+ ikona ✓), źródło w podpisie |
| `likely` | „Prawdopodobnie dostępny” (inna ikona niż `yes`, np. ✓?) |
| `unknown` | „Brak danych” (szary, ?) |
| `no` | „Niedostępny” (✗) |
| `conflict` | „Sprzeczne dane” (⚠), kliknięcie pokazuje `wheelchair_basis` |

**Waga zagrożenia** `severity`: `blokada` (nie do pokonania dla profilu), `ostrzezenie` (utrudnienie), `brak_danych` (nie wiadomo). Typ: `type` (np. `schody`, `krawezniki_wysoki`, `krawezniki_brak_danych`, `nawierzchnia`, `nachylenie`, `brak_lawki`, `brak_prowadzenia`, `sygnalizator_bez_dzwieku`, `brak_oswietlenia`, `waski`) – na ikonę.

**Krawężnik** `kerb_class`: `wysoki`, `obnizony`, `rowny`, `pochyly`, `brak` (bez krawężnika), `brak_danych`.

🆕 **Dopasowanie miejsca** `fit.verdict`: `pasuje` ✓, `prawdopodobnie_pasuje` ~, `nie_pasuje` ✗, `sprzeczne` ⚠, `brak_danych` ?, `brak_kryteriow` (preferencje nie dotyczą tego miejsca). Każdy punkt `fit.checks[]` ma `verdict` (`tak` / `nie` / `czesciowo` / `brak_danych` / `sprzeczne`), `verdict_text`, `status`, `source`, `observed_at`. Pokażcie jako **listę kontrolną** („✓ Wejście bez schodów – potwierdzone, OSM, 2026-05”; „? Szerokość wejścia co najmniej 0,9 m – brak danych”). „Pasuje” pojawia się tylko, gdy wszystkie sprawdzone warunki są spełnione **i potwierdzone**.

**Status odcinka na mapie** (`edges_status.geojson`, pole `s`: jeden znak na profil w kolejności z `profiles.json`): `0` ok, `1` niepewne, `2` zablokowane.

## 2. Co zbudować (priorytety)

### P1 – bez tego nie ma dema
1. **Wybór wymagań (🆕 zmiana).** Dwie ścieżki w jednym panelu: (a) „Szybki wybór” = przyciski-skróty profili (`profiles=`), (b) „Moje wymagania” = kontrolki z tabeli preferencji (`prefs=`). Wybór zapamiętać w `localStorage` na urządzeniu (nie wysyłamy go na serwer). Skróty mogą ustawiać kontrolki (np. „wózek” → `nostairs`, `kerb`, `width:0.9`), ale użytkownik widzi i zmienia **parametry**. W UI nie używajcie sformułowań „osoba niepełnosprawna” jako warunku korzystania.
2. **Pola „Skąd / Dokąd”** z podpowiedziami: `GET /api/geocode?q=...` (adresy, ulice, nazwy miejsc, przystanki; literówki poprawia, wtedy `fuzzy:true` – pokażcie „dopasowanie przybliżone”). Dodatkowo: przycisk „Moja lokalizacja” (Geolocation API) i wybór kliknięciem w mapę (wtedy `from_lon/from_lat`). Punkt poza obszarem → komunikat 422 z API.
3. **Trasy do wyboru: `GET /api/routes?from_q=...&to_q=...&profiles=...&prefs=...`**
   Zwraca `routes[]` (GeoJSON Feature) + `recommended`. Pokażcie **karty wariantów** obok siebie: `label`, `length_m`, `time_min`, `extra_m` (ile dłużej niż najkrótsza), liczniki `hazard_counts` (blokady / utrudnienia / braki danych), znaczek „Polecana” dla `recommended`. Wybór karty rysuje linię (`geometry`) na mapie. Warianty: *Najbardziej dostępna*, *Zrównoważona*, *Najkrótsza (pokazuje przeszkody)*. Pole `tez_jako` mówi, że kilka wariantów jest identycznych. `properties.start_label`/`end_label` = jak API zrozumiało punkty.
4. **Znaczniki zagrożeń na mapie**: `properties.hazards[]` → marker w `lon/lat`, ikona wg `type`, obwódka/kształt wg `severity` (nie sam kolor). Klik/fokus → popup: `text`, `at_m` („po 106 m”), `street`, `source`. Zagrożenia o `length_m>0` można dodatkowo obrysować wzdłuż trasy.
5. **Lista kroków**: `properties.steps[]` (tekst gotowy, `status` 0/1/2 → ikonka OK / UWAGA / PRZESZKODA). Pod trasą `warnings[]` jako baner. **To jest też widok tekstowy zamiast mapy** (WCAG) – nie chowajcie go.
6. **Karta miejsca**: `GET /api/places/{id}?profile=...&prefs=...` (id z `/api/places?q=` albo z klikniętego obiektu `pois.geojson`). Pokażcie `summary.text`, 🆕 `fit` (lista kontrolna, gdy są wybrane wymagania), tabelę `attributes` z źródłem, datą i statusem (przy wielu `versions` – wszystkie wersje obok siebie), `banner` (np. awaria źródła), sekcję `transit`.
7. **Zgłoszenie od użytkownika**: `POST /api/reports` `{feature_id, attribute, value, comment}` (atrybuty z błędu 422 lub z listy w `/docs`). Odpowiedź ma `status: "niezweryfikowane"` i 🆕 `osm_edit_url`, `osm_note_url` – pokażcie po wysłaniu: „Dziękujemy. Chcesz poprawić źródło dla wszystkich? [Popraw w OpenStreetMap]”. Limit 429 → przyjazny komunikat.

### P2 – mocno podnosi wartość
8. **Plan z komunikacją: `GET /api/plan?from_q=&to_q=&profiles=&prefs=`**. Przełącznik „Pieszo / Z komunikacją”. `walk_only` – zwykła trasa; `options[]` – po 3 segmenty: `walk_to` (Feature, przerywana linia), `ride` (jazda: gruba linia między `board_stop` i `alight_stop`, kolor wg `mode`), `walk_from`. Karta opcji: `summary`, godziny (`board_departure`, `arrive`), `total_min`, `wait_min`, `faster_than_walking_min` (może być **ujemne** = wolniej niż pieszo; wtedy napiszcie „wolniej niż pieszo o N min” i nie wyróżniajcie opcji, ale jej nie chowajcie – bywa jedyną bez przeszkód), **odznaka dostępności pojazdu** (`ride.wheelchair` + `wheelchair_basis`), `live_at_board_stop`. Gdy `options` puste, pokażcie `notes[]`. Zawsze wyświetlcie uwagę, że **dostępność przystanku nie jest w danych ZTP**. Dla wymagań „bez schodów” API domyślnie pokazuje tylko pojazdy `yes`/`likely`.
9. 🆕 **„Najbliżej mnie”: `GET /api/nearest?lon=&lat=&kind=toaleta&profiles=&prefs=&accessible=`**. Przyciski rodzajów z `GET /api/meta` → `rodzaje_udogodnien` (toaleta, ławka, apteka, przychodnia, kawiarnia, restauracja, woda, bankomat, poczta, muzeum, parking). Wynik: `results[]` z `walk_m` (**po chodnikach wg wymagań**, nie w linii prostej), `walk_min`, `straight_m`, `wheelchair{value_text,status,source,observed_at}`. Pokażcie odległość po chodnikach, a w drugiej linii „w linii prostej: …”. Kliknięcie → trasa do tego miejsca (`to_place=id` w `/api/routes`). `accessible=true` = tylko obiekty z potwierdzonym tagiem dostępności. Gdy `results` puste – wyświetlcie `note`.
10. **Przystanki w pobliżu**: `GET /api/transit/nearby?lon=&lat=&radius=&only_accessible=` – lista przystanków, odjazdy z rozkładu (`departures`) i **na żywo** (`live.departures` z `vehicle`, `vehicle_model`, `wheelchair*`). Jeśli `live.available` = true, pokazujcie **live zamiast rozkładu**. `accessibility_note` pokażcie raz nad listą.
11. **Warstwy mapy** (przełączniki):
    - granica obszaru: `GET /api/area` (ustawcie `fitBounds` na `bbox`),
    - status odcinków: `edges_status.geojson` (kolor wg znaku `s[i]` dla wybranego profilu; plus wzór linii),
    - krawężniki: `GET /api/kerbs` (`kerb_class`, `kerb_text`; **brak_danych** pokazujcie wprost, to nasza luka danych),
    - przystanki: `transit_stops.geojson`,
    - najgorsze bariery: `GET /api/barriers?profile=...&top=15` (ranking, każdy ma `lon/lat`, `powod`, `odcina_wezlow`).
12. 🆕 **Potwierdzanie zgłoszeń**: przy wersji z `user_report: true` przycisk „U mnie też tak” → `POST /api/reports/{report_id}/confirm` (`report_id` jest w wersji atrybutu). Pokazujcie `community_text` („3 os. potwierdziło”). To **nie zmienia statusu** – nadal „niezweryfikowane”. Przy każdej wersji link „Popraw w OSM” (`osm_edit_url`) i „Zostaw notatkę” (`osm_note_url`).
13. **Przycisk „Głos” (wejście)**: patrz sekcja 3.
14. 🆕 **Baner stanu systemu**: raz po wczytaniu `GET /api/health`. Gdy `status` = `czesciowo`, pokażcie krótki, spokojny komunikat z `co_widzi_uzytkownik` dla każdego z `niedostepne` (np. „Dane na żywo chwilowo niedostępne – pokazujemy sam rozkład”). Banery z pola `banner`/`warnings` w odpowiedziach też.

### P3 – jeśli zostanie czas (a jury lubi to widzieć)
15. 🆕 **Ekran „O danych”: `GET /api/stats`** – uczciwy obraz pokrycia: `miejsca.pokrycie_atrybutow` (pasek % na atrybut), `miejsca.statusy_faktow`, `miejsca.wiek_faktow`, `siec_piesza.przejsc_z_danymi_o_krawezniku_pct`, `siec_piesza.nachylenie_zrodlo_pct`, `zgloszenia`. Podpis z `uwaga`. Do tego link do `/api/sources` (rejestr źródeł: pochodzenie, licencja, aktualność, weryfikacja) i do `GET /api/export/places?format=csv` („Pobierz otwarte dane”).
16. 🆕 **„Pomóż uzupełnić dane”: `GET /api/gaps?lon=&lat=&radius_m=&category=&limit=`** – lista miejsc, gdzie brak lub niepewność danych kosztuje najwięcej (`priorytet`, `powody`, `brakuje`, `distance_m`). Przy każdym: [Zgłoś dostępność] (formularz → `POST /api/reports`) i [Popraw w OSM] (`osm_edit_url`). Doskonałe do pokazania „jak poprawić błędne dane” z briefu.
17. 🆕 **Osadzalna karta (dla hoteli/organizatorów): `<iframe src="<API>/embed/place/{id}?prefs=...">`** – gotowa strona HTML bez JS. Zróbcie podstronę „Dla firm” z przykładem iframe i z kodem do skopiowania. Ustawcie `title` na iframe (WCAG 2.4.1/4.1.2) i nie ustawiajcie sztywnej wysokości mniejszej niż ~500 px.
18. **Izochrona**: `GET /api/isochrone?lon=&lat=&profiles=&minutes=15` – wielokąt „dokąd dojdę w 15 min”; porównanie profili obok siebie świetnie wygląda na demo (obszar kurczy się dla wózka).
19. **Nawigacja głosowa w ruchu** (sekcja 3).
20. 🆕 **Panel scenariuszy demo (ukryty, np. `?demo=1`): `GET /api/demo/scenarios`** – gotowe przypadki z briefu: dane sprzeczne, niepełne, brak danych, awaria źródła, trasa z przeszkodami, tramwaj na żywo, najbliższa toaleta. Każdy ma `url`/`place_id` do otwarcia. Przyciski do `POST /api/dev/seed` (dodaje zgłoszenia PRZYKŁADOWE oznaczone „dane demo”) i `POST /api/dev/outage {"on":true|false}` (symulacja awarii źródła). **Dane przykładowe zawsze oznaczajcie** „dane demo” (wymóg briefu).
21. **Strona „Źródła danych”**: `GET /api/sources` – dla każdego źródła pochodzenie, licencja i `license_status` (jeśli `do_potwierdzenia`, pokażcie to), aktualność, weryfikacja, `data_retrieved_at`.

## 3. Głos (agent głosowy / mowa na tekst)
Rozpoznawanie i czytanie robi **przeglądarka** (Web Speech API, Chrome/Edge/Safari): nic nie idzie na nasz serwer poza tekstem polecenia.

**Wejście (mikrofon):**
```js
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const rec = new SR(); rec.lang = 'pl-PL'; rec.interimResults = false;
rec.onresult = async (e) => {
  const text = e.results[0][0].transcript;
  const r = await (await fetch(`${API}/api/voice/command?q=${encodeURIComponent(text)}`)).json();
  speak(r.reply);                       // odpowiedź do przeczytania
  if (r.call) { /* r.call.endpoint + r.call.params -> wywołaj, a przy r.call.needs_gps podstaw pozycję użytkownika */ }
};
rec.start();
```
`intent` z serwera: `route`, `nearest`, `where_am_i`, `transit_nearby`, `set_profile`, `clarify`, `not_found`, `help`; polecenia obsługiwane lokalnie przez front (pole `client_action`): `repeat`, `next_step`, `stop`, `list_hazards`, `remaining`, `confirm`, `deny`, `choose`. Gdy `from_gps` lub `needs_gps` – wstawcie pozycję z Geolocation (§12). **Pełna pętla dialogu: §11.**
🆕 Rozumie też **odmienione nazwy** („z Rynku Głównego do Dworca Głównego”) i formy typu „dla wózka”, „na wózku inwalidzkim”, „z dzieckiem”, „dla osoby niewidomej”, „jestem seniorem”, „w ciąży”. Samo „wózek” bez doprecyzowania = wózek inwalidzki; wtedy odpowiedź ma pole **`assumed`** (tekst) – `reply` już go zawiera, ale pokażcie go też na ekranie.
Zawsze zostawcie **pole tekstowe** jako alternatywę (nie każdy może mówić, nie każda przeglądarka ma STT).

**Wyjście (czytanie):**
```js
function speak(t){ const u = new SpeechSynthesisUtterance(t); u.lang='pl-PL'; speechSynthesis.cancel(); speechSynthesis.speak(u); }
```
Dodatkowo każdy komunikat wrzucajcie do regionu `aria-live="polite"` (czytniki ekranu) – głos z przeglądarki i czytnik nie powinny się dublować, więc dajcie przełącznik „Czytaj na głos”.

**Nawigacja z ostrzeżeniami w ruchu:** `properties.narration[]` ma `announce_at_m`, `text`, `severity`, `lon/lat`, `hazard_ids`. Pętla: co kilka sekund policz przebytą odległość wzdłuż trasy (najbliższy punkt linii; albo prosty `haversine` do kolejnego zagrożenia) i gdy użytkownik minie `announce_at_m`, powiedz `„Za 30 metrów: ”+text` (raz na komunikat). **Tryb demo**: suwak „symuluj marsz” przesuwa pozycję po linii – pozwala pokazać głos bez chodzenia po Krakowie.

## 4. Dostępność (WCAG 2.2 AA) – lista kontrolna (to trafia też do prezentacji: „zrobione” vs „zaplanowane”)
Zaznaczajcie realny stan w kolumnie Status (✓ zrobione / ◐ w trakcie / ☐ zaplanowane) – brief wymaga **uczciwej listy**, więc nie zaznaczajcie, czego nie sprawdziliście.
| Wymaganie | Co zrobić | Status |
|---|---|---|
| `<html lang="pl">`, tytuł strony, landmarki (`header`, `main`, `nav`) | podstawa | ☐ |
| Klawiatura (2.1.1): cała obsługa bez myszy, brak pułapek | Tab/Shift+Tab, Enter/Spacja, Esc zamyka okna | ☐ |
| Widoczny fokus (2.4.7) i niezasłonięty (2.4.11) | obrys ≥ 2 px o kontraście ≥ 3:1; fokus nie chowa się pod paskami | ☐ |
| Kontrast (1.4.3 / 1.4.11) | tekst ≥ 4,5:1, elementy interfejsu i ikony ≥ 3:1; sprawdzić w DevTools | ☐ |
| Nie tylko kolor (1.4.1) | status/zagrożenie = ikona + słowo + (kształt) | ☐ |
| Powiększenie (1.4.4, 1.4.10) | 200% bez utraty treści, brak przewijania poziomego przy 320 px | ☐ |
| Rozmiar celu (2.5.8) | co najmniej 24×24 px (zalecane 44) | ☐ |
| Alternatywa dla przeciągania (2.5.7) | przyciski +/− i strzałki do mapy; adres zamiast klikania | ☐ |
| Mapa nie jest jedyną drogą (1.1.1) | lista kroków i zagrożeń obok mapy, widok tekstowy domyślny dla czytnika | ☐ |
| Czytnik ekranu (4.1.2, 4.1.3) | `aria-label` markerów = `spoken` + „po 106 metrach”; `aria-live` dla komunikatów o trasie | ☐ |
| Formularze (3.3.1, 3.3.2) | etykiety, błędy przy polu z podpowiedzią, nie sam kolor | ☐ |
| Ruch (2.3.3 / ustawienia systemu) | respektować `prefers-reduced-motion`; tryb wysokiego kontrastu / ciemny | ☐ |
| Głos (nasze rozszerzenie) | mikrofon + czytanie na głos + pole tekstowe jako alternatywa | ☐ |
| Prosty język (3.1.5) | krótkie zdania, bez żargonu | ☐ |
| Tryb prosty i skupienia | tekst ≥ 20 px, cele ≥ 56 px, `font_scale` do 200%, bez gestów, bez animacji w trybie skupienia (§10) | ☐ |
| Lokalizacja (3.3.x, 2.2.1) | zgoda dopiero po kliknięciu, ręczna alternatywa (adres/mapa), brak limitów czasu (§12) | ☐ |
| Test | axe DevTools / Lighthouse (cel ≥ 95) + test z NVDA lub VoiceOver | ☐ |
Nie używajcie słowa „dostępne” bez wartości `yes` i podanej podstawy.

## 5. Typowe błędy API (pokażcie przyjazny komunikat)
- `404` „Nie znaleziono adresu” (podpowiedź: ulica + numer lub nazwa miejsca) / „Nie znaleziono trasy” (`hint` w odpowiedzi).
- `422` punkt poza obszarem demo (Śródmieście), nieznany profil, 🆕 zły token preferencji (`detail.dostepne_preferencje`), nieznany rodzaj w `/api/nearest` (`detail.dostepne`).
- `429` za dużo zgłoszeń. `503` brak danych (po stronie backendu).

## 6. Stan danych / ograniczenia do wiedzy
- Obszar demo = obręb Kraków-Śródmieście; przystanki i przejazdy tylko w jego granicach, bez przesiadek.
- Krawężniki: w OSM są prawie wszędzie **bez tagu `kerb`**, więc większość przejść będzie miała `brak_danych`. To luka danych, nie błąd; zachęcajcie do zgłoszeń (`/api/gaps`).
- Tramwaje mają pewną dostępność dopiero, gdy ZTP przypisze pojazd do kursu (zwykle ok. godziny przed odjazdem); wcześniej `unknown`. Autobusy: `likely` (deklaracja MPK od 2018 r., nie sprawdzenie pojazdu).
- Wszystkie godziny w strefie Europe/Warsaw.

## 7. Szybkie adresy do testów (`<API>` = adres backendu)
- `/api/meta`, `/api/area`, `/api/sources`, 🆕 `/api/stats`, `/api/health`
- `/api/geocode?q=floriańska 10`
- `/api/routes?from_q=Floriańska 10&to_q=Dworzec Główny&profiles=wozek_inwalidzki`
- 🆕 `/api/routes?from_q=Floriańska 10&to_q=Dworzec Główny&prefs=nostairs,kerb,incline:6`
- `/api/plan?from_q=Floriańska 10&to_q=Dworzec Główny&profiles=wozek_inwalidzki`
- 🆕 `/api/nearest?lon=19.937&lat=50.061&kind=toaleta&profiles=wozek_inwalidzki`
- `/api/transit/nearby?lon=19.937&lat=50.061`
- `/api/kerbs`, `/api/barriers?profile=wozek_inwalidzki`
- 🆕 `/api/gaps?lon=19.937&lat=50.061&radius_m=800`
- 🆕 `/embed/place/{id}?prefs=nostairs,width:0.9` (otwórz w przeglądarce)
- 🆕 `/api/export/places?format=csv`, `/api/demo/scenarios`
- `/api/voice/command?q=trasa z Floriańska 10 do Dworca Głównego dla wózka inwalidzkiego`
- 🆕🆕 `/api/routes?from_q=Floriańska 10&to_q=Dworzec Główny&profiles=senior&simple_steps=5` (patrz `properties.simple`, `properties.spoken_summary`, `properties.nalot`)
- 🆕🆕 `/api/whereami?lon=19.937&lat=50.061&accuracy_m=20`, `/api/catalog`, `/api/catalog/resolve?profiles=senior&on=toilet,incline:6&off=bench`
- 🆕🆕 `/api/surveys`, `/api/surveys/at?lon=19.937&lat=50.061`, `/api/surveys/observations`, `/api/profile/schema`, `POST /api/profile/validate`
- 🆕🆕 `/api/voice/command?q=jak dojść do toalety`, `/api/voice/command?q=gdzie jestem`, `/api/nearest?lon=19.937&lat=50.061&kind=winda`

## 8. Proponowany układ ekranów
1. **Główny**: lewy panel (Skąd/Dokąd, „Moje wymagania”, wyniki: karty tras, lista kroków i zagrożeń), po prawej mapa; pod spodem przyciski „Najbliżej mnie”, „Głos”.
2. **Karta miejsca** (panel lub osobna strona): podsumowanie, „Czy pasuje do moich wymagań”, tabela atrybutów ze źródłami, zgłoszenie, linki do OSM.
3. **O danych**: statystyki, źródła, eksport, „Pomóż uzupełnić dane”.
4. **Dla firm**: przykład iframe karty dostępności + krótki opis (patrz `BIZNES.md`).
5. **Dostępność aplikacji**: deklaracja z listy w sekcji 4 (zrobione/zaplanowane).

## 9. Ścieżka demo (ok. 3 min) – co musi działać płynnie
1. Wybór wymagań („bez schodów”, „niskie krawężniki”) → trasa Floriańska 10 → Dworzec Główny: trzy warianty, polecany, znaczniki zagrożeń, zapowiedź głosowa.
2. Karta miejsca ze **sprzecznymi danymi** (scenariusz `sprzeczne`): dwie wersje, źródła, daty, „niezweryfikowane”.
3. Miejsce **bez danych** (`brak_danych`): „Nie zakładamy, że jest dostępne” + link „Popraw w OSM”.
4. **Awaria źródła** (`POST /api/dev/outage`): aplikacja działa, baner o danych zapisanych.
5. „Najbliższa toaleta” chodnikami dla wózka vs dla pieszego.
6. Przejazd tramwajem/autobusem z odznaką dostępności pojazdu i jej podstawą.
7. Ekran „O danych” (pokrycie) i iframe dla hotelu.
8. 🆕🆕 **Tryb prosty** (§10): ta sama trasa dla seniora w pięciu krokach, jedno zdanie na krok, duże kafelki, „Przeczytaj”.
9. 🆕🆕 **Głos** (§11): „jak dojść do toalety” → asystent czyta wynik; dwuznaczna nazwa → dopytuje „które wybierasz?”.
10. 🆕🆕 **Ostatni nalot** (§16): data, „świeże do …”, co nalot obejmuje i czego nie (wpis demo podpisany „PRZYKŁADOWE – dane demo”).
11. 🆕🆕 **Profil na urządzeniu** (§13): „Pobierz mój profil”, wczytanie pliku, informacja „dane zostają u ciebie”.

---

# Rozszerzenia (🆕🆕 ostatnia runda): sekcje 10–16

## 10. Tryb prosty („dla babci”) i tryb skupienia (np. ADHD)
**Kontrolka „Wygląd”** – trzy duże przyciski z podpisami (nie same ikony): **Standardowy / Prosty / Skupienie**. Na pierwszym uruchomieniu osobny ekran z dwoma przyciskami: „Zwykły widok” i „Duże litery i prosty widok”. Wybór można zmienić zawsze (stały przycisk „Wygląd” w tym samym miejscu).
Dodatkowo suwak **„Wielkość liter”** 100–200 % (`ui.font_scale`) i przełącznik **„Wysoki kontrast”** (`ui.contrast`). Nie nazywajcie trybu „dla seniorów”, „dla ADHD” ani „dla niepełnosprawnych” – nazwy mają opisywać wygląd.

**Dane z backendu dla obu trybów** (nic nie trzeba liczyć po stronie frontu):
```
GET /api/routes?...&profiles=senior&simple_steps=5      # simple_steps 3–9 (domyślnie 7); skupienie: 4–5
routes[i].properties.simple = {
  "summary": "Trasa ma około 490 metrów, to około 8 min. Na trasie jest 1 miejsce wymagające uwagi.",
  "steps": [ {"n":1, "text":"Idź ulicą Objazd około 130 metrów.", "distance_m":130, "turn":"start|prosto|prawo|lewo|zawroc|koniec",
              "kind":"chodnik|schody|przejscie|cel", "warning":false, "warning_text":null}, ... ostatni: "Jesteś u celu." ],
  "max_steps": 5 }
routes[i].properties.spoken_summary = "Trasa ma około 490 metrów ... Uwaga na 1 miejsce: po 130 metrach nierówna nawierzchnia ..."
```
`turn` → strzałka (↑ → ← ↩) **razem z tekstem**; `warning=true` → osobny pas z ikoną ⚠/⛔ i `warning_text` (nigdy sam kolor). `kind` = ikona (schody, przejście, chodnik).

### 10.1. Tryb prosty
| Element | Zasada |
|---|---|
| Tekst | podstawowy ≥ 20 px (po przeskalowaniu `font_scale`), nagłówki ≥ 28 px, interlinia ≥ 1,5, bez kursywy i WERSALIKÓW, jedna czcionka bezszeryfowa |
| Kontrast | min. 4,5:1; w „wysokim kontraście” ≥ 7:1 |
| Ekran główny | 4–6 kafelków na pełną szerokość: „Dokąd idę?”, „Najbliższa toaleta”, „Najbliższa ławka”, „Gdzie jestem?”, „Przystanki w pobliżu”, „Powiedz, czego szukasz” (mikrofon). Kafelek = ikona + słowo, wysokość ≥ 96 px, odstęp ≥ 12 px |
| Cele dotykowe | ≥ 56 px (WCAG 2.5.8 wymaga 24 px; tu celowo więcej) |
| Gesty | **brak** pinch/swipe/długiego naciśnięcia/dwukliku. Wszystko jednym dotknięciem |
| Nawigacja | zawsze widoczne „Wstecz” i „Początek”; brak menu hamburgerowego i ukrytych elementów |
| Mapa | domyślnie **ukryta** za przyciskiem „Pokaż mapę”; głównym widokiem są kroki. Mapa ma przyciski +/− i strzałki |
| Trasa | jeden wariant (`recommended`) + przycisk „Pokaż inne trasy”. Nagłówek = `simple.summary`; każdy krok = kafelek (numer, strzałka, `text`); `warning` w osobnym pasie |
| Czytanie | przycisk „Przeczytaj” przy trasie (`spoken_summary`) i przy każdym kroku (`text`) |
| Język | pełne zdania, bez skrótów i żargonu. Statusy możecie przepisać prostszymi słowami, **zachowując sens**: „brak danych” → „Nie mamy informacji”; nigdy „dostępne” bez statusu `potwierdzone`/`yes` |
| Czas | bez limitów czasu, bez odliczania, bez automatycznego odświeżania pod palcem, bez wyskakujących okienek, bez autoodtwarzania dźwięku |
| Potwierdzenia | jedno pytanie naraz, odpowiedzi „Tak” / „Nie” jako duże przyciski; akcje nieodwracalne (usuń profil) z pytaniem |
| Stopka karty | „Dane sprawdzone z lotu: …” (§16) tylko jeśli `fresh` |

### 10.2. Tryb skupienia
| Element | Zasada |
|---|---|
| Jeden krok naraz | na ekranie tylko **bieżący krok** (duży tekst) + „Dalej” / „Wstecz” / „Powtórz”. Postęp **tekstem**: „Krok 2 z 5” (pasek opcjonalnie) |
| Ruch | **zero animacji** niezależnie od ustawień systemu (nie tylko `prefers-reduced-motion`); mapa bez płynnych przejazdów (`jumpTo` zamiast `flyTo`); brak migania i przesuwających się elementów |
| Kolory | stonowane, jeden kolor akcentu; ostrzeżenia ikoną i tekstem, bez czerwonego błyskania |
| Bodźce | domyślnie bez dźwięków (`voice_replies=false`), wibracja opcjonalna, brak powiadomień „ponaglających” |
| Presja czasu | brak odliczania i komunikatów typu „spiesz się”; odjazdy: „o 14:32 (za 6 min)” |
| Wybory | maks. 3 opcje na ekranie, jedna zaznaczona domyślnie |
| Długość tekstu | krok to jedno krótkie zdanie z `simple.steps[].text`; bez dodatkowych akapitów |
| Przejście do kolejnego kroku | ręcznie („Dalej”). Automatyczne przejście po GPS tylko jako **opcjonalny przełącznik** (domyślnie wyłączony) |
**Kierunek rozwoju (nie wymagane na hackathonie):** przypomnienie „czas wyjść na przystanek” (lokalne), „lista przed wyjściem” (bilet, leki), tryb bez dźwięków. Zbieramy pomysły od osób z ADHD – nie zakładajcie, co im pomaga, dopóki ich nie zapytacie.

### 10.3. Zapis ustawień wyglądu
Do profilu lokalnego (§13): `ui.mode` (`standard|prosty|skupienie`), `ui.font_scale`, `ui.contrast` (`normalny|wysoki`), `ui.reduce_motion`, `ui.voice_replies`, `ui.max_steps` (przekazujcie jako `simple_steps`).

## 11. Asystent głosowy (dla osób niewidomych i nie tylko)
Cel: obsługa **bez patrzenia na ekran**. Rozpoznawanie i czytanie robi przeglądarka (Web Speech API, `pl-PL`, patrz §3); serwer dostaje tylko tekst polecenia. Serwer jest **bezstanowy** – kontekst rozmowy (poprzednia trasa, lista wyborów, wybrane wymagania) trzyma front.

**Wygląd/zachowanie:**
- Duży przycisk mikrofonu (dolna połowa ekranu, `aria-label="Powiedz polecenie"`), krótki sygnał dźwiękowy po starcie nasłuchu. Gdy asystent zadał pytanie („Które wybierasz?”), nasłuch włącza się sam.
- Transkrypcja usłyszanego tekstu widoczna i w `aria-live="polite"`; pole tekstowe jako równoległa metoda; przycisk „Powtórz ostatnią odpowiedź”. Przełącznik „Czytaj na głos” (żeby czytnik ekranu i TTS się nie dublowały).
- Gdy przeglądarka nie ma STT (np. Firefox): pole tekstowe + czytanie odpowiedzi.

**Pętla dialogu (szkic):**
```js
const state = { profiles: '', prefs: '', pendingClarify: null, route: null, pos: null, lastSpoken: '' };

async function onUtterance(text) {
  const r = await (await fetch(`${API}/api/voice/command?q=${encodeURIComponent(text)}`)).json();
  if (r.client_action) return handleClientAction(r);                 // powtórz, dalej, stop, wybór numeru...
  if (r.assumed) show(r.assumed);                                    // np. „Zakładam wózek inwalidzki...” (reply już to zawiera)
  switch (r.intent) {
    case 'set_profile':  state.profiles = r.set.profiles || state.profiles;
                         state.prefs = [state.prefs, r.set.prefs].filter(Boolean).join(','); return say(r.reply);
    case 'clarify':      state.pendingClarify = r; return say(r.reply);          // „Znalazłam kilka miejsc: 1. ... 2. ... Które wybierasz?”
    case 'route':        return doCall(r.call, r);                                // r.call.needs_gps === 'from' => from_lon/from_lat z GPS
    case 'nearest':      return doNearest(r);                                     // wymaga GPS; patrz niżej
    case 'where_am_i':   return doWhereAmI();
    case 'transit_nearby': return doCall(r.call, r);
    default:             return say(r.reply);                                      // not_found, help
  }
}
```
**Obsługa intencji:**
| `intent` | Co robi front |
|---|---|
| `route` | woła `r.call.endpoint` z `r.call.params`; przy `needs_gps:"from"` dopisuje `from_lon/from_lat` z pozycji (§12). Po odpowiedzi czyta `routes[recommended].properties.spoken_summary`, potem: „Powiedz: dalej, powtórz, przeszkody albo stop.” |
| `clarify` | zapamiętuje `r.clarify` (`slot`: `from`/`to`, `choices[]` z `n`, `label`, `lon`, `lat`). Następna wypowiedź „drugi”/„numer 2” przychodzi jako `client_action:"choose"`, `index:2` → front dopisuje `{slot}_lon`, `{slot}_lat` z wybranej opcji do `r.call.params` i woła trasę |
| `nearest` | `GET /api/nearest` z `r.call.params` + `lon/lat` z GPS (+ aktualne `profiles/prefs`). Czyta pole **`spoken`**. Gdy `r.route_to_first` (np. „jak dojść do toalety”): po wyniku woła `/api/routes` z `to_place=results[0].id` i `from_lon/from_lat` z GPS, czyta `spoken_summary` |
| `where_am_i` | `GET /api/whereami?lon&lat&accuracy_m` → czyta `spoken` (§12) |
| `transit_nearby` | `GET /api/transit/nearby?lon&lat`; czyta najbliższe odjazdy (`live` zamiast rozkładu, gdy dostępne) |
| `set_profile` | zmienia wymagania w stanie (i w profilu lokalnym, jeśli użytkownik go zapisuje) – bez wołania API |
| `not_found`, `help` | czyta `reply` (podpowiada, jak sformułować polecenie) |

**`client_action` (bez wołania serwera):**
| akcja | Zachowanie |
|---|---|
| `repeat` | powtórz `state.lastSpoken` |
| `next_step` | przeczytaj następny krok (`simple.steps[n].text` albo kolejny element `narration`) |
| `stop` | `speechSynthesis.cancel()`, zakończ nasłuch |
| `list_hazards` | przeczytaj zagrożenia trasy o `severity` ≠ `brak_danych`, od najbliższych: „po 130 metrach: …” (`hazards[].spoken` + `at_m`) |
| `remaining` | policz z pozycji GPS: długość trasy minus przebyta; „Zostało około 200 metrów” |
| `choose` (`index`) | wybór z `pendingClarify.choices` (patrz wyżej); bez oczekującego wyboru: „Nie mam teraz nic do wyboru.” |
| `confirm` / `deny` | odpowiedź na ostatnie pytanie asystenta (np. „Zakładam wózek inwalidzki. Zgadza się?”) |

**Nawigacja z zapowiedziami w ruchu:** `properties.narration[]` (§3). Obserwacje z nalotów dronem dostają zapowiedź „… (według nalotu z 20.09.2026)” – czytajcie dosłownie, nie obcinajcie daty.
**Teksty:** asystent mówi w rodzaju żeńskim („Znalazłam”, „Nie zrozumiałam”). Jeśli chcecie inny, dajcie znać – to teksty w `engine/voice.py` i `api/main.py`.
**Prywatność (do podania w interfejsie):** rozpoznawanie mowy w niektórych przeglądarkach (np. Chrome) może wysyłać nagranie do usługi dostawcy przeglądarki. Pokażcie krótką informację przy pierwszym użyciu mikrofonu i dajcie wybór „pisanie zamiast mowy”. **[polityka prywatności do napisania]**
**Test:** NVDA (Windows) / VoiceOver (iOS, macOS) / TalkBack (Android) – przejście ścieżki: „jak dojść do toalety” → wynik → trasa → „przeszkody” → „stop”.

## 12. Lokalizacja urządzenia („Moja lokalizacja”, „Gdzie jestem”)
**Zasady:**
- Zgodę o lokalizację uruchamiamy **dopiero po kliknięciu** („Użyj mojej lokalizacji”, kafelek „Gdzie jestem?”) albo po poleceniu głosowym wymagającym pozycji (`needs_gps`). Nigdy przy wczytaniu strony.
- Wymaga HTTPS (localhost wyjątek). Pozycja **nie jest zapisywana** (ani w localStorage, ani w profilu, ani w analityce); do API trafiają tylko współrzędne zapytania.
- Zawsze ręczna alternatywa: wpisanie adresu (`/api/geocode`) lub wskazanie punktu na mapie.

```js
function getPosition() {
  return new Promise((ok, fail) => navigator.geolocation.getCurrentPosition(
    p => ok({ lon: p.coords.longitude, lat: p.coords.latitude, accuracy_m: p.coords.accuracy }),
    e => fail(e), { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }));
}
// śledzenie (watchPosition) tylko w trakcie nawigacji; zawsze clearWatch przy końcu trasy i przy wyjściu z ekranu
```
**Błędy (komunikaty po polsku, bez żargonu):**
| `e.code` | Komunikat | Co dalej |
|---|---|---|
| 1 `PERMISSION_DENIED` | „Nie masz włączonej lokalizacji dla tej strony. Możesz wpisać adres albo wskazać miejsce na mapie.” (+ krótka instrukcja włączenia w przeglądarce) | pole adresu / mapa |
| 2 `POSITION_UNAVAILABLE`, 3 `TIMEOUT` | „Nie udało się ustalić, gdzie jesteś. Spróbuj jeszcze raz albo wpisz adres.” | ponów / ręcznie |
**Dokładność:** `accuracy_m` > 50 → napis „Lokalizacja jest niedokładna (około N m)” – nie ukrywajcie. W budynkach GPS bywa błędny.
**Obszar:** punkt poza obszarem demo daje 422 w trasach/`nearest`; `/api/whereami` zwraca `inside_area:false` z komunikatem. Pokażcie go i zaproponujcie wybór punktu w obszarze.

**„Gdzie jestem”:** `GET /api/whereami?lon=&lat=&accuracy_m=` →
`{inside_area, text, spoken, address{label,street,number,type,distance_m}|null, nearby[{id,name,category,distance_m}], stop{name,mode,distance_m}|null, accuracy_m}`.
Pokażcie `text` dużą czcionką, przeczytajcie `spoken`. Brak adresu (`address:null`) to normalna sytuacja – tekst mówi to wprost. Klik w element z `nearby` otwiera kartę miejsca.
**Tryb demo:** pole „symuluj pozycję” (klik w mapę) – wyraźnie oznaczone, pozwala pokazać funkcje bez chodzenia po Krakowie.

## 13. Profil lokalny („konto” bez konta)
Domyślnie aplikacja działa **anonimowo** i nic nie zapisuje. Opcja: „Zapamiętać moje ustawienia na tym urządzeniu?” (domyślnie **Nie**). Gdy użytkownik zgodzi się, zapisujecie **plik profilu** w `localStorage`/IndexedDB (klucz np. `kbb.profile.v1`; zawsze w `try/catch` – tryb prywatny potrafi zablokować zapis) z opcjami:
- **„Pobierz mój profil”** (plik JSON, np. `moj-profil.json`), **„Wczytaj profil”** (`<input type="file" accept="application/json">`), **„Usuń moje dane z tego urządzenia”**.
- Przekazanie komuś (np. babci): plik wysłany komunikatorem. Rozmiar maks. 20 kB.

**Format i walidacja po stronie serwera (serwer niczego nie zapisuje):**
```
GET  /api/profile/schema     -> format, JSON Schema, tryby interfejsu, 3 przykłady (babcia, wozek_toaleta, skupienie), zasady prywatności
POST /api/profile/validate   -> body = zawartość pliku; odpowiedź: {ok, errors[], warnings[], profile{...znormalizowany plik}, query{profiles, prefs}, etykieta, aktywne[]}
```
Plik: `{"format":"krakow-bez-barier-profil","version":1,"name":"Babcia Hela","groups":["senior"],"on":["toilet"],"off":["bench"],
"ui":{"mode":"prosty","font_scale":1.6,"contrast":"wysoki","reduce_motion":true,"voice_replies":true,"max_steps":5},"places":[{"label":"Dom","lon":19.94,"lat":50.061}]}`.
- `groups` = klucze 6 grup; `on` / `off` = id pozycji z `/api/catalog` (§14), `on` ze skrótem parametru: `incline:6`, `width:0.9`, `bench:300`.
- Po wczytaniu pliku: `ok:false` → pokażcie `errors[]` po ludzku; `ok:true` → pokażcie `etykieta` + `warnings[]` i przycisk „Zastosuj”. Po zastosowaniu **używajcie `query.profiles` i `query.prefs`** w każdym zapytaniu.
- `places[].inside_area` mówi, czy ulubione miejsce leży w obszarze z danymi.
- Wyświetlcie zasady prywatności z `schema.prywatnosc` (plik zawiera dane o potrzebach zdrowotnych: zostaje u użytkownika).
- Nie dodawajcie logowania, e-maila ani synchronizacji przez serwer.

## 14. „Moje wymagania”: 6 stałych grup + dobieranie i usuwanie pozycji
`GET /api/catalog` → `grupy[]` (`key`, `label`, `domyslne[]` = id pozycji, które grupa włącza) i `pozycje[]` (`id`, `label`, `opis`, `rodzaj` = `bariera`|`udogodnienie`, `token_dodaj`, `token_usun`).
**Układ ekranu:**
1. (Opcjonalnie) wybór jednej lub kilku grup – 6 dużych kafelków; można nie wybrać żadnej.
2. Lista przełączników: sekcje **„Bariery, które omijam”** (`rodzaj=bariera`) i **„Udogodnienia, które chcę widzieć”** (`rodzaj=udogodnienie`). Stan początkowy = `domyslne` wybranych grup. Użytkownik może **wyłączyć** pozycję grupy (trafia do `off`) albo **włączyć** dodatkową (trafia do `on`).
3. Pozycje z parametrem: `incline` (suwak 1–15 %, wysyłajcie `incline:6`), `width` (0,5–1,5 m), `bench` (100–1000 m).
4. Pozycji, których nie można dodać (`token_dodaj: null`: `handrail`, `lowfloor`, `entrance_width`), nie pokazujcie jako włączalnych; pokazujcie je tylko, jeśli grupa je zawiera (można je wyłączyć).
5. Zamiana wyboru na parametry: `GET /api/catalog/resolve?profiles=senior&on=toilet,incline:6&off=bench` → `{profiles, prefs, aktywne[], etykieta}`. Wstawiajcie `profiles` i `prefs` do wszystkich zapytań. `etykieta` (np. „Senior + Własne preferencje: nachylenie do 6% (bez: brak ławek)”) pokażcie jako „Twoje wymagania”.
Zły wybór → 422 z `detail.message`. **Nie** twórzcie nowych grup ani nazw „typów ludzi”; jedyną nazwą jest lista z `/api/catalog`.

## 15. Budynki i toalety
Budynki użytku publicznego (szpital, urząd, dworzec, muzeum…), windy i toalety mają kartę jak inne miejsca: `GET /api/places/{id}?profile=…&prefs=…`.
- `attributes[].group` ∈ `wejscie`, `w_srodku`, `orientacja`, `inne`; słownik etykiet jest w `grupy`. Rysujcie sekcje w tej kolejności (nagłówek + lista). Cechy: winda (`elevator`), rampa (`ramp:wheelchair`, `ramp`), toaleta (`toilets`, `toilets:wheelchair`), szerokość drzwi, liczba stopni, drzwi automatyczne, poręcz, przewijak, pętla indukcyjna.
- `w_poblizu[]` – toalety i windy w pobliżu obiektu: `kind`, `name`, `distance_m`, **`line_of_sight:true` = odległość w linii prostej**, nie po chodnikach; podpiszcie „w linii prostej: 114 m”. Dostępność: `wheelchair{value_text,status,source,observed_at}` (ikona + słowo). Kliknięcie otwiera kartę tego obiektu.
- Toaleta: `fee` (płatna), `opening_hours` (zapis OSM – pokażcie jako „godziny (zapis OSM)” albo dosłownie), `changing_table`, `toilets:wheelchair`.
- Brak danych o toalecie/windzie w budynku: „Nie wiemy, czy w budynku jest dostępna toaleta” + [Zgłoś] + [Popraw w OSM]. **Nigdy** „jest”/„dostępna” bez potwierdzenia.
- „Najbliższa toaleta / winda / budynek”: `GET /api/nearest?kind=toaleta|winda|budynek&accessible=true` (odległość po chodnikach wg wymagań). Pole `spoken` jest gotowe do czytania.
- Dla wymagań z udogodnieniami (`toilet`, `lift`, `changing`, `loop` z §14) karta pokazuje werdykt `fit` jako listę kontrolną.

## 16. Nalot dronem: widoczna świeżość danych
Rejestr nalotów (jak często, kiedy ostatnio, co obejmuje). Wpis demo jest oznaczony `demo:true` i tekstem „PRZYKŁADOWE – dane demo” – **nie obcinajcie go** i nie prezentujcie jako prawdziwego lotu.
| Gdzie pokazać | Skąd |
|---|---|
| Stopka mapy/karty: „Ostatni nalot: 20.09.2026” | `GET /api/meta` → `ostatni_nalot` |
| Ekran „O danych” | `GET /api/surveys` → `last.text`, `last.fresh` (ikona + słowo „świeże”/„nieświeże”), `last.fresh_until`, `last.next_planned`, `last.covers[]`, **`last.does_not_cover[]` (zawsze pokazujcie obie listy)**, `note`, `area_with_fresh_survey_pct` |
| Przy trasie | `routes[].properties.nalot.text` (np. „100% trasy leży w obszarze ze świeżym nalotem …”), `coverage_fresh_pct` |
| Przy miejscu | `place.nalot` |
| Warstwa mapy „Obserwacje z lotu” | `GET /api/surveys/observations` (GeoJSON punktów; `properties.type`, `label`, `observed_at`, `source`, `demo`) – ikona wg typu (zastawiony chodnik, remont, zniszczona nawierzchnia, wąski chodnik, przeszkoda, chodnik zablokowany) |
| W punkcie | `GET /api/surveys/at?lon=&lat=` (kiedy to miejsce było ostatnio sprawdzone) |
Obserwacje leżące przy trasie są już w `hazards[]` (`type:"obserwacja_nalotu"`, `severity:"ostrzezenie"`, `source:"nalot 20.09.2026 …"`) i w `narration[]`, więc pojawią się na liście zagrożeń i w zapowiedziach głosowych bez dodatkowej pracy.
**Zasady tekstu:** „sprawdzone z lotu” zawsze z datą i z tym, czego nalot **nie** obejmuje. Obserwacja z lotu to stan z dnia nalotu – nie „dostępne”, nie „bez przeszkód”. `fresh:false` pokażcie jako „dane z okolicy mogą być nieaktualne”.

## 17. Klik w mapę / w budynek: adres, udogodnienia, bariery
`GET /api/at?lon=&lat=&profiles=&prefs=&snap_m=10` – jedno wywołanie po kliknięciu w dowolny punkt mapy. Zamienia współrzędne na **budynek** (obrys z OSM, `buildings.geojson`), a gdy to nie budynek, na najbliższy obiekt (ławka, przystanek, sklep ≤ 25 m). Klik tuż obok obrysu (do `snap_m`, domyślnie 10 m) też trafia w budynek.
Dane budynków trzeba pobrać (`python -m pipeline.run_all` pobiera je razem z resztą; powstaje `buildings.geojson` obok `pois.geojson`). Front może narysować ten plik jako warstwę „Budynki” (przezroczyste wielokąty, podświetlenie po najechaniu/fokusie) – ale **sam klik wystarczy wysłać do API**, nie trzeba samemu szukać budynku.

**Odpowiedź (najważniejsze pola):**
```
inside_area      false => poza obszarem demo, pokaż "text"
found            "budynek" | "obiekt" | "nic"
address          {label, street, number, distance_m, approximate, source} albo null
                 approximate=false: adres z tagów budynku albo punkt adresowy w obrysie; true: NAJBLIŻSZY adres/ulica ("około N m stąd")
building         {id, type, name, click_distance_m, footprint (GeoJSON Polygon do podświetlenia)} albo null
place            {id,name,category,lon,lat} (to samo co w karcie miejsca; "id" otwiera /api/places/{id})
summary          {level,text}  – jak w karcie miejsca
udogodnienia[]   {attribute,label,value_text,status,source,observed_at}   – TYLKO potwierdzone "tak" z danych
bariery[]        to samo – "nie", "ograniczony", stopnie przy wejściu ("3 stopnie")
informacje[]     fakty neutralne (szerokość drzwi, opis, godziny, opłata…)
sprzeczne[]      źródła się różnią; "versions" – pokażcie obie wersje
brak_danych[]    {attribute,label} – czego NIE wiemy (nigdy nie pokazujcie tego jako "jest")
w_budynku[]      obiekty (sklepy, toalety, windy…) leżące w obrysie, z krótkim statusem dostępności
w_poblizu[]      windy/toalety w pobliżu (odległość w linii prostej, "line_of_sight": true)
fit              werdykt dla wybranych wymagań (jak w karcie miejsca), null bez wymagań
nalot            kiedy ostatnio sprawdzaliśmy teren (§16)
text / spoken    gotowe zdanie do pokazania / przeczytania
osm_edit_url, osm_note_url   "Popraw w OpenStreetMap"
```
**Jak to pokazać (panel po kliknięciu):**
1. Nagłówek: nazwa (lub "Budynek bez nazwy") + **adres**. Gdy `address.approximate`, napis "Najbliższy adres: … (około N m stąd)" – nie podawajcie go jako adresu budynku.
2. Trzy listy z ikoną **i** słowem: ✓ Udogodnienia, ✗ Bariery, ? Brak danych. `sprzeczne` jako ⚠ z dwiema wersjami.
3. Sekcje wg `attributes[].group` (`grupy`: wejście, w środku, orientacja, inne) – jak w §15.
4. `w_budynku`: lista obiektów z kliknięciem do karty.
5. Przyciski: [Trasa tutaj] (`to_place={place.id}` albo `to_lon/to_lat`), [Zgłoś dostępność] (`POST /api/reports` z `feature_id=place.id`), [Popraw w OSM].
6. Dla budynku bez żadnych danych pokażcie wprost: "Nie mamy danych o udogodnieniach ani barierach tego budynku" – to jest poprawny, uczciwy wynik.
**Uwagi:** zgłoszenia do budynków spoza listy miejsc (bez wpisu w `pois.geojson`) wymagają, by `feature_id` było w bazie faktów; w razie wątpliwości użyjcie `osm_edit_url`. Klik poza obszarem demo daje 200 z `inside_area:false` (nie 422). W trybie prostym (§10) pokażcie tylko: adres, 3 najważniejsze udogodnienia/bariery i "Przeczytaj" (`spoken`).
