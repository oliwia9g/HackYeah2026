# Opowieść do pokazu (storytelling i scenariusz demo)

> Prezentację robimy na końcu, ale opowieść wynika z tego, co **naprawdę** działa, więc ten plik jest szkieletem: co mówić, w jakiej kolejności i co pokazać.
> Każdy punkt demo jest oznaczony: **[backend ✓]** = działa i jest przetestowane, **[front ?]** = zależy od tego, co zbuduje front, sprawdzić przed nagraniem.
> Nie pokazujemy niczego, czego nie ma. Dane przykładowe zawsze podpisane „PRZYKŁADOWE – dane demo”.

## 1. Jedno zdanie (hasło)
**„Mapa, która mówi, czego jeszcze nie wie.”**
Alternatywy: „Nie mówimy »dostępne«, dopóki tego nie wiemy.” / „Każdy fakt ma źródło i datę. Każdy brak jest widoczny.”

## 2. Bohaterowie (postacie ilustracyjne, nie prawdziwe osoby)
- **Hela, 72 lata** – chodzi z laską, boi się schodów i skomplikowanych aplikacji. Pokazuje tryb prosty.
- **Marek, na wózku** – jedzie do urzędu; potrzebuje wiedzieć, czy jest winda i toaleta. Pokazuje uczciwość danych.
- **Ola, niewidoma** – pyta głosem. Pokazuje asystenta i zapowiedzi na trasie.
- **Ktoś z urzędu miasta lub właściciel kawiarni** – płaci za wiarygodne dane. Pokazuje model biznesowy.

Wybierzcie **jednego głównego bohatera** (najlepiej Marka lub Helę) i prowadźcie przez niego całą historię; pozostałych pokażcie krótko jako dowód, że to samo działa dla innych.

## 3. Łuk opowieści (7 aktów)
| # | Akt | Co mówimy (sens, nie dosłownie) | Co pokazujemy | Kryterium jury |
|---|---|---|---|---|
| 1 | **Problem** | Ta sama ulica to dla jednych 5 minut, dla innych przeszkoda nie do przejścia. Aplikacje mówią „dostępne”, bo nie wiedzą, jak to sprawdzić. | zdjęcie lub mapa z jednym schodkiem / kostką (własne zdjęcie, nie z internetu bez licencji) | użyteczność dla grupy docelowej |
| 2 | **Zwrot: brak danych to nie „tak”** | W naszej aplikacji brak informacji wygląda jak brak informacji. | karta miejsca **z brakiem danych**: „Nie zakładamy, że miejsce jest dostępne” **[backend ✓: scenariusz `brak_danych`]** | wiarygodność danych |
| 3 | **Rozwiązanie: trasa pod ciebie** | Wybierasz, czego potrzebujesz (nie diagnozę). Dostajesz trzy warianty z ceną objazdu i miejscami ostrzeżeń. | trasa Floriańska 10 → Dworzec Główny dla wózka; znaczniki zagrożeń, lista kroków **[backend ✓ `/api/routes`; front ?]** | jakość prototypu, użyteczność |
| 4 | **Uczciwość: sprzeczne dane** | Gdy źródło mówi „tak”, a użytkownik „nie”, nie wybieramy za ciebie. Pokazujemy obie wersje, źródła, daty. | karta ze statusem `sprzeczne` po `POST /api/dev/seed` **[backend ✓ scenariusz `sprzeczne`]** | wiarygodność, wymóg briefu (przypadek sprzecznych danych) |
| 5 | **Świeżość: dron co 3 miesiące** | Dane o chodnikach starzeją się szybciej niż mapa. Co kwartał przelatujemy teren i w aplikacji widać, kiedy to było i czego nalot nie widzi. | ekran „Ostatni nalot: data, świeże do …, nie obejmuje: szerokości drzwi, wnętrz” **[backend ✓ `/api/surveys`; front ?]**. **Uwaga:** wpis demo, nie udawać prawdziwego lotu | wiarygodność i aktualizacja danych, potencjał wdrożenia |
| 6 | **Dla każdego: prosty tryb, głos, lokalizacja** | Hela przełącza na duże kafelki: kilka kroków, jedno zdanie na krok. Ola pyta głosem „jak dojść do apteki”. | `properties.simple` w trybie prostym; polecenie głosowe + „gdzie jestem” **[backend ✓; front ?]** | użyteczność dla grupy docelowej (25%) |
| 7 | **Skala i pieniądze** | Użytkownik nie płaci i nie ma konta (dane o zdrowiu zostają u niego). Płacą obiekty (karta dostępności), miasto (przegląd z lotu), firmy (API). Inne miasto = plik konfiguracji. | iframe karty dla hotelu (`/embed/place/{id}`) **[backend ✓]**; plik `cities/TEMPLATE.yaml` | potencjał wdrożenia, model biznesowy |

**Zakończenie (wezwanie do działania):** „Pomóż nam uzupełnić dane: jedno zgłoszenie, jedna poprawka w OSM — widać ją dla wszystkich.” **[backend ✓ `osm_edit_url`, `/api/gaps`]**

## 4. Scenariusz filmu (maks. 3 min)
| Czas | Ujęcie | Lektor (szkic) | Źródło/wymaga |
|---|---|---|---|
| 0:00–0:15 | Hela przed schodami / mapa z przeszkodą | „Dla jednych to pięć minut spaceru. Dla innych — przeszkoda, o której żadna mapa nie uprzedza.” | własne ujęcie |
| 0:15–0:40 | Wybór wymagań (kilka przełączników, nie „diagnoza”) → trzy warianty trasy | „Nie pytamy, kim jesteś. Pytamy, czego potrzebujesz na trasie.” | `/api/routes` [front ?] |
| 0:40–1:05 | Zagrożenia na trasie + zapowiedź głosowa „za 30 metrów: schody” | „Wiemy, gdzie jest przeszkoda i ile kosztuje objazd.” | `narration` [front ?] |
| 1:05–1:30 | Karta z brakiem danych → karta ze sprzecznymi danymi | „Gdy nie wiemy — mówimy to. Gdy źródła się różnią — pokazujemy obie wersje.” | scenariusze `brak_danych`, `sprzeczne` |
| 1:30–1:50 | Ekran „Ostatni nalot” + mapa obserwacji | „Co trzy miesiące sprawdzamy teren z lotu. Widzisz kiedy, i czego nalot nie obejmuje.” | `/api/surveys` (PRZYKŁADOWE) |
| 1:50–2:15 | Tryb prosty (Hela) + asystent głosowy (Ola) | „Ten sam system. Inny sposób, żeby z niego korzystać.” | `simple`, `/api/voice/command` [front ?] |
| 2:15–2:40 | „Najbliższa toaleta” chodnikami, karta budynku (winda, rampa) | „Nie w linii prostej, tylko tam, gdzie da się dojść.” | `/api/nearest`, karta budynku |
| 2:40–3:00 | iframe w hotelu + plik konfiguracji miasta + hasło | „Użytkownik nie płaci. Płacą ci, którzy chcą, żeby ich dane były wiarygodne. »Mapa, która mówi, czego jeszcze nie wie.«” | `/embed/place/{id}`, `cities/TEMPLATE.yaml` |

Wskazówki: nagrywajcie na zdrowych, wcześniej sprawdzonych danych (`python -m pipeline.run_all` przed nagraniem), endpointy `/api/dev/*` (seed, outage) są domyślnie włączone, a na wdrożeniu publicznym wyłączcie je (`HACKYEAH_DEV=0`); do sprzecznych danych możecie też uruchomić serwer z `HACKYEAH_SEED=1`; napisy do filmu (dostępność!) i audiodeskrypcja kluczowych ujęć w opisie.

## 5. Szkielet prezentacji (maks. 10 slajdów)
| Slajd | Tytuł | Treść | Kryterium |
|---|---|---|---|
| 1 | Problem | jedna historia + jedno zdanie o skali **[do uzupełnienia: źródło]** | użyteczność |
| 2 | Dla kogo | 6 grup + opiekunowie; „nie pytamy o niepełnosprawność” (`ODBIORCY_I_ADOPCJA.md` §1–2) | użyteczność |
| 3 | Rozwiązanie | zrzuty: trasa z przeszkodami, karta miejsca, nearest | prototyp |
| 4 | Zaufanie do danych | źródło + data + status; brak danych ≠ dostępne; przypadek sprzeczny | dane |
| 5 | Aktualizacja danych | pipeline vs prezentacja, awaria źródła, **nalot co 3 miesiące**, „ostatni nalot” w aplikacji | dane, wdrożenie |
| 6 | Dla każdego | tryb prosty, skupienie, głos, lokalizacja, profil na urządzeniu | użyteczność |
| 7 | WCAG 2.2 AA | lista „zrobione / zaplanowane” (uczciwie, z `ARCHITEKTURA.md` §7 i `FRONTEND.md` §4) | formalne |
| 8 | Model biznesowy | kto płaci i za co; czego nie robimy | biznes |
| 9 | Skala i hosting | `CITY_CONFIG`, koszty, prywatność, licencje | wdrożenie |
| 10 | Plan i wezwanie | prototyp → pilotaż → pierwsze przychody; jak pomóc | biznes, wdrożenie |

## 6. Zdania, które warto powtórzyć
- „Brak danych to nie »dostępne«.”
- „Każdy fakt ma źródło, datę i status.”
- „Nie pytamy, kim jesteś. Pytamy, czego potrzebujesz.”
- „Twój profil jest u ciebie, nie u nas.”
- „Widzisz, kiedy ostatnio sprawdziliśmy teren, i czego nie sprawdziliśmy.”

## 7. Trudne pytania jury (i uczciwe odpowiedzi)
| Pytanie | Odpowiedź |
|---|---|
| Skąd macie dane? | OpenStreetMap (ODbL), model terenu GUGiK, rozkłady i dane na żywo ZTP, zgłoszenia użytkowników; rejestr z licencją i statusem: `SOURCES.md`, `/api/sources`. Część licencji czeka na potwierdzenie (`do_potwierdzenia`). |
| Czy ten nalot dronem naprawdę się odbył? | W prototypie wpis jest **przykładowy** i tak oznaczony. Mechanizm jest gotowy; pierwszy prawdziwy nalot wymaga sprawdzenia przepisów i zgód (lista w `BIZNES.md` §5). |
| Co dron widzi, a czego nie? | Powierzchnię, zastawione chodniki, remonty, szerokość chodnika. Nie widzi szerokości drzwi, stopni pod zadaszeniem, wnętrz. Aplikacja pokazuje to użytkownikowi. |
| Co z prywatnością i RODO? | Brak kont; wymagania są parametrami, nie deklaracją zdrowia; profil w pliku na urządzeniu; GPS nie jest zapisywany; serwer bez logów dostępu (`--no-access-log`). Polityka prywatności do napisania. |
| Czy to działa poza Śródmieściem / w innym mieście? | Konfiguracja (`CITY_CONFIG`) zmienia obszar i miasto; część transportowa potrzebuje adaptera operatora. Nie sprawdzaliśmy na drugim mieście. |
| Kto to utrzyma i za co? | Przychody z audytów, przeglądu z lotu, kart dla obiektów i API; granty na zbieranie danych (`BIZNES.md`). |
| Co jeśli dane OSM są złe? | Pokazujemy to (`/api/stats`, `/api/gaps`), a poprawka w OSM trafia do wszystkich. Zgłoszenia nigdy nie nadpisują źródła. |
| Czy testowaliście z prawdziwymi użytkownikami? | **[uzupełnić zgodnie z prawdą]**. Jeśli nie, mówimy: „zaplanowane w etapie 0, `BIZNES.md` §8”. |

## 8. Czego nie obiecujemy w nagraniu
Pełnej dostępności całego Krakowa; że „brak ostrzeżenia = brak przeszkody”; że nalot sprawdza wnętrza; że aplikacja zastępuje audyt; działania na żywych danych tam, gdzie ich nie sprawdziliśmy (pełny `run_all` na nowym obszarze, drugie miasto).
