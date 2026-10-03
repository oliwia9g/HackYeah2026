# Dla kogo jest aplikacja i jak zachęcić ludzi do jej używania

> Postacie poniżej to **scenariusze ilustracyjne**, nie wyniki badań. Wszystko oznaczone **[założenie]** wymaga sprawdzenia w rozmowach i testach z prawdziwymi osobami.
> Powiązane: `BIZNES.md` (kto płaci), `FRONTEND.md` §10–13 (tryb prosty, skupienie, głos, lokalizacja), `STORYTELLING.md`.

## 1. Odpowiedź w jednym zdaniu
Aplikacja jest dla **każdego, kto na pieszej trasie albo przy wejściu do budynku musi wiedzieć, czy się da przejść**: osób na wózku, rodziców z wózkiem dziecięcym,
osób niewidomych i słabowidzących, głuchych i niedosłyszących, seniorów i kobiet w ciąży. Do tego dochodzą ich opiekunowie, osoby z tymczasowym ograniczeniem (gips, kule, ciężka walizka) i goście miasta.

Zasada projektowa: *jeśli działa dla osoby z największymi ograniczeniami, działa dla wszystkich.* Dlatego nie pytamy „jaką masz niepełnosprawność”, tylko „czego potrzebujesz na trasie”.

## 2. Kto z niej korzysta (scenariusze)
| Scenariusz | Co robi w aplikacji | Co jest dla niej kluczowe | Interfejs |
|---|---|---|---|
| **Osoba na wózku**, dojazd do urzędu | wybiera „wózek”, trasa z 3 wariantami, sprawdza kartę budynku (wejście, winda, toaleta) | trasa bez schodów i wysokich krawężników, szczerze „brak danych” zamiast „dostępne” | standardowy |
| **Rodzic z wózkiem dziecięcym** | trasa bez schodów, „najbliższy przewijak/toaleta”, tramwaj niskopodłogowy | przewijak, winda, nachylenie | standardowy |
| **Osoba niewidoma** | mówi do telefonu: „jak dojść do apteki”, słucha zapowiedzi „za 30 m: schody” | głos w obie strony, prowadzenie dotykowe, sygnał dźwiękowy na przejściu, „gdzie jestem” | głos + czytnik ekranu |
| **Osoba głucha / niedosłysząca** | sprawdza w miejscu, czy jest pętla indukcyjna, czyta komunikaty tekstowe | informacja tekstowa, pętla w urzędach i kasach | standardowy; to **najsłabiej pokryta grupa** w danych (patrz niżej) |
| **Senior („babcia Hela”)** | włączony tryb prosty: duże kafelki, kilka kroków, ławki na trasie, „gdzie jestem” | czytelność, mało kroków, ławki, toalety | prosty (§4) |
| **Kobieta w ciąży** | trasa z ławkami, najbliższa toaleta, tramwaj niskopodłogowy | ławki, toalety, brak stromych podejść | standardowy lub prosty |
| **Opiekun / dorosłe dziecko seniora** | ustawia profil babci i wysyła jej plik z ustawieniami | prosta konfiguracja za kogoś, plik profilu (sekcja 6) | standardowy → prosty u babci |
| **Osoba z ADHD lub trudnościami z koncentracją** | tryb skupienia: jeden krok naraz, bez animacji, krótkie zdania | brak przeciążenia, jedna rzecz na ekranie | skupienie (§4) |
| **Gość miasta z walizką** | „bez schodów”, najbliższa winda, przystanki | proste preferencje bez deklarowania niczego | standardowy |

**Uczciwie o danych:** dla osób głuchych i niedosłyszących mamy dziś najmniej (pętla indukcyjna, ewentualnie tekstowa informacja w obiektach). To obszar do rozbudowy z organizacjami tych osób, nie coś, co już „mamy załatwione”.

## 3. Kto płaci a kto korzysta
Użytkownicy nie płacą nigdy za funkcje potrzebne do bezpiecznego przejścia trasy. Płacą obiekty, instytucje i firmy, które potrzebują wiarygodnych, świeżych danych (szczegóły: `BIZNES.md`).

## 4. Interfejs, który dopasowuje się do osoby
Backend wspiera trzy tryby, które front przełącza jednym przyciskiem („Wygląd”) i zapamiętuje na urządzeniu:

| Tryb | Dla kogo | Zasady (pełna specyfikacja: `FRONTEND.md` §10) |
|---|---|---|
| **Standardowy** | większość osób | mapa + panele, wszystkie opcje |
| **Prosty („dla babci”)** | seniorzy, osoby niepewne technologii | duże kafelki z jedną akcją, tekst ≥ 20 px, wysoki kontrast, maks. kilka kroków trasy (jedno zdanie na krok), przyciski zamiast gestów, czytanie na głos, brak ukrytych menu |
| **Skupienie** (np. ADHD) | osoby, którym przeszkadza nadmiar bodźców | jeden krok naraz, bez animacji i migotania, spokojne kolory, bez limitów czasu, przypomnienie „następny krok”, krótkie zdania |

Backend dostarcza do tego gotowe dane: `properties.simple` (kroki trasy po jednym zdaniu, z kierunkiem skrętu, ostrzeżeniem jako osobnym polem), `properties.spoken_summary` (podsumowanie do przeczytania), parametr `simple_steps` (3–9 kroków; dla trybu skupienia polecamy 4–5).

**ADHD jako kierunek rozwoju.** Nie twierdzimy, że aplikacja „leczy” czy „diagnozuje”; tryb skupienia to **ułatwienie interfejsu**. Pomysły na dalszy rozwój po konsultacjach z osobami z ADHD **[do zweryfikowania w badaniach]**:
przypomnienia o wyjściu na przystanek (lokalnie, bez konta), „lista kontrolna przed wyjściem” (bilet, leki), trasa z mniejszą liczbą zakrętów, tryb bez dźwięków. Ten sam mechanizm (profil + tryb interfejsu) obsłuży też inne potrzeby poznawcze.

## 5. Jak zachęcić ludzi do używania (adopcja)
**Zasada:** wartość w 10 sekund, bez instalacji, bez konta, bez wstydu. Pierwszy kontakt = link lub kod QR, jedno pytanie („czego potrzebujesz na trasie?”) i od razu wynik.

### 5.1. Kanały (kogo prosimy o pomoc) — wszystkie do nawiązania **[założenie]**
| Kanał | Dlaczego | Co oferujemy |
|---|---|---|
| Organizacje osób z niepełnosprawnościami (np. związki osób niewidomych i głuchych, lokalne stowarzyszenia) **[zweryfikować kontakty]** | zaufanie i dostęp do grup, które znają problem | współtworzenie testów, mapathony, moderacja zgłoszeń |
| Rady seniorów, uniwersytety trzeciego wieku, biblioteki, domy kultury | seniorzy uczą się razem, w grupie | warsztat „jak dojść bez schodów” z trybem prostym |
| Szkoły rodzenia, żłobki, grupy rodziców | wózek dziecięcy i ciąża to codzienne trasy | ulotka z kodem QR, widżet w placówkach |
| Hotele, muzea, urzędy, szpitale | goście i klienci pytają o dostępność | karta dostępności do wstawienia na stronę (`/embed/place/{id}`), kod QR przy wejściu |
| Miasto i jednostki transportu | przystanki, wiaty, tablice informacyjne | kod QR na przystanku → najbliższe udogodnienia i odjazdy |
| Uczelnie (koła naukowe, studenci kierunków informatycznych i projektowych) | ręce do mapowania, pomysły | mapathony dostępności, konkursy na poprawę danych |
| Informacja turystyczna, przewodnicy | goście miasta | karta z kodem QR „Kraków bez barier” |

### 5.2. Pętle, które napędzają używanie
1. **Użyteczność na co dzień** – nie tylko „planuję wycieczkę”, ale „gdzie jest najbliższa toaleta/ławka/winda” i „gdzie jestem”. Codzienna wartość = powrót.
2. **„Poprawiłem — widzę efekt”** – zgłoszenie od użytkownika (niezweryfikowane) prowadzi do poprawki w OSM (`osm_edit_url`), a po odświeżeniu danych zmiana jest widoczna na mapie. Użytkownik widzi, że jego głos coś zmienia.
3. **Zaufanie przez uczciwość** – „brak danych” zamiast „dostępne”, data i źródło przy każdym fakcie, „ostatni nalot: data”. Ludzie, którym raz zabrakło informacji o schodach, wracają do źródła, które nie zmyśla.
4. **Pętla obiektów** – obiekt wstawia kartę → goście z niej korzystają → obiekt widzi w panelu luk (`/api/gaps`), co uzupełnić → dane się poprawiają → karta jest więcej warta.
5. **Pętla opiekuna** – dorosłe dziecko ustawia profil babci i wysyła jej plik ustawień (sekcja 6): jedna osoba konfiguruje, druga korzysta w trybie prostym.
6. **Wydarzenia** – mapathony i „dni dostępności” z organizacjami; po każdym widać skokowo lepsze dane (`/api/stats`), więc jest co świętować.

### 5.3. Czego nie robimy
Bez powiadomień push z reklamą, bez rankingów imiennych (bo wymagałyby kont i śledzenia), bez sprzedaży danych, bez wymuszania rejestracji. Postęp „ile moich poprawek” może być liczony **lokalnie na urządzeniu**.

### 5.4. Plan na pierwsze miesiące **[założenie]**
| Okres | Cel | Miara (bez danych osobowych) |
|---|---|---|
| 0–30 dni | testy z kilkoma osobami z każdej grupy (głównie tryb prosty i głos), poprawa tekstów | liczba osób w teście, odsetek, którzy samodzielnie wyznaczyli trasę |
| 30–60 dni | 1–2 organizacje i 1 grupa seniorów jako partnerzy, pierwszy mapathon | liczba poprawek w OSM wywołanych z aplikacji |
| 60–90 dni | 3–5 obiektów z kartą i kodem QR, pierwszy prawdziwy nalot/spacer terenowy z datą w aplikacji | liczba osadzeń karty, % obszaru ze świeżą kontrolą |

## 6. „Konto” bez konta: profil na urządzeniu
Użytkownik może **zapisać swoje ustawienia** (wybrana grupa, włączone i wyłączone udogodnienia, tryb interfejsu, ulubione miejsca), ale **plik zostaje u niego**: w pamięci przeglądarki, z opcją pobrania i wczytania na innym urządzeniu.
Domyślnie aplikacja działa **anonimowo** i nic nie zapisuje; profil to opcja.
Serwer tylko sprawdza poprawność pliku (`POST /api/profile/validate`) i niczego nie przechowuje. Dlaczego tak: wymagania dostępnościowe to dane o zdrowiu, więc najbezpieczniej ich w ogóle nie zbierać. Szczegóły techniczne: `FRONTEND.md` §13, `ARCHITEKTURA.md` §5.

## 7. Wrażliwe dane: sztywne grupy, elastyczne ustawienia
Zostajemy przy **sześciu stałych grupach** jako gotowych punktach wyjścia (nie tworzymy nowych „kategorii ludzi”). Użytkownik może **dobrać lub usunąć** poszczególne bariery i udogodnienia (np. senior bez wymogu ławek, wózek z windą jako warunkiem, dodatkowo „toaleta”, „przewijak”, „pętla indukcyjna”):
`GET /api/catalog` (co jest w grupach i co można dodać) i `GET /api/catalog/resolve` (zamiana wyboru na parametry). Nigdzie nie wymagamy deklaracji, że ktoś ma konkretną niepełnosprawność.
