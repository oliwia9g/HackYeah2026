# Rejestr źródeł danych

Dla każdego źródła: pochodzenie, warunki wykorzystania, aktualność i sposób weryfikacji. Plik generowany z `sources.yaml`.

## Źródła użyte w rozwiązaniu

### OpenStreetMap (sieć piesza, obiekty, krawężniki, przejścia)
Adres: https://www.openstreetmap.org
Status licencji: **warunki sprawdzone**

- **Do czego używamy:** Sieć piesza (trasy), obiekty użytku publicznego i ich dostępność (tag wheelchair itd.), przejścia, krawężniki, adresy (geokodowanie)
- **Wydawca:** Społeczność OpenStreetMap
- **Licencja / warunki:** ODbL 1.0
- **Oznaczenie źródła:** © OpenStreetMap contributors
- **Użycie komercyjne:** Dozwolone z oznaczeniem źródła. ODbL wymaga, by publicznie udostępniona baza pochodna (np. nasze facts.csv/json, adresy) też była na ODbL (share-alike).
- **Aktualność:** Dane społecznościowe, różna świeżość. Mierzymy ją: data ostatniej edycji obiektu (Overpass) i, jeśli jest, check_date. Około 20% obiektów ma check_date.
- **Jak weryfikujemy:** Każdy fakt ma status (potwierdzone / prawdopodobne / niezweryfikowane / sprzeczne / brak). Sama data ostatniej edycji nie daje statusu „potwierdzone”. Sprzeczność ze zgłoszeniem użytkownika jest pokazywana wprost. Brak tagu = „brak danych”, nigdy „dostępne”.
- **Ograniczenia:** Niskie pokrycie tagów dostępności (wheelchair ma ok. 8% POI, szerokość drzwi 0%). Pobieranie przez Overpass API podlega polityce użycia serwera.

### Overpass API (metadane: data ostatniej edycji)
Adres: https://overpass-api.de
Status licencji: **warunki sprawdzone**

- **Do czego używamy:** Data ostatniej edycji obiektów OSM (out meta) jako słabszy dowód aktualności
- **Wydawca:** Overpass API / OpenStreetMap
- **Licencja / warunki:** ODbL 1.0 (te same dane OSM)
- **Oznaczenie źródła:** © OpenStreetMap contributors
- **Użycie komercyjne:** Jak OSM. Publiczne serwery Overpass mają limity - na wdrożeniu potrzebny własny lub komercyjny serwer.
- **Aktualność:** Pobierane przy każdym uruchomieniu pipeline.fetch_overpass_meta
- **Jak weryfikujemy:** Data edycji nie jest potwierdzeniem dostępności; oznaczamy ją osobno (observed_basis = last_edit).
- **Ograniczenia:** Edycja mogła dotyczyć innego atrybutu (np. nazwy).

### Numeryczny Model Terenu (NMT), GUGiK
Adres: https://www.geoportal.gov.pl/en/data/digital-elevation-model-dem/
Status licencji: **warunki sprawdzone**

- **Do czego używamy:** Nachylenia chodników (OSM prawie ich nie ma - ok. 3,7% krawędzi)
- **Wydawca:** Główny Urząd Geodezji i Kartografii, Geoportal
- **Licencja / warunki:** Dane NMT udostępniane bezpłatnie, do dowolnego celu (wg Geoportalu)
- **Oznaczenie źródła:** Źródło: Główny Urząd Geodezji i Kartografii (Geoportal)
- **Użycie komercyjne:** Wg informacji Geoportalu bez ograniczeń celu; dokładny tekst warunków do przepisania z oficjalnej strony przed wdrożeniem komercyjnym.
- **Aktualność:** Aktualizowany wg nalotów skanowania laserowego; konkretna data dla Krakowa do sprawdzenia w metadanych usługi.
- **Jak weryfikujemy:** NMT służy do OCENY nachyleń, nie do blokowania trasy bez pewności: blokujemy tylko, gdy źródłem jest OSM albo odcinek NMT ma co najmniej 25 m. Mosty i tunele zakładamy jako płaskie. Źródło nachylenia (OSM / NMT / krótka krawędź / brak) jest zapisane przy każdej krawędzi.
- **Ograniczenia:** NMT to teren, nie powierzchnia chodnika. Krótkie odcinki dają niepewny wynik.

### Rozkłady jazdy ZTP Kraków (GTFS: tramwaje i autobusy)
Adres: https://gtfs.ztp.krakow.pl/
Status licencji: **DO POTWIERDZENIA**

- **Do czego używamy:** Przystanki i odjazdy z rozkładu w pobliżu miejsca
- **Wydawca:** Zarząd Transportu Publicznego w Krakowie
- **Licencja / warunki:** Nie znaleźliśmy jednoznacznej licencji na stronie plików. ZTP publikuje je jako otwarte dane miasta.
- **Oznaczenie źródła:** Źródło: ZTP Kraków (GTFS)
- **Użycie komercyjne:** DO POTWIERDZENIA u ZTP lub w opisie zbioru na portalu Otwarte Dane Krakowa przed użyciem komercyjnym.
- **Aktualność:** Pliki aktualizowane codziennie (strona pokazuje daty aktualizacji).
- **Jak weryfikujemy:** Rozkład to nie rzeczywistość: odjazdy są oznaczone jako rozkład. Pola dostępności przystanków i kursów (wheelchair_boarding / wheelchair_accessible) mają w feedzie same zera = brak danych, więc NIE pokazujemy dostępności z rozkładu.
- **Ograniczenia:** Brak informacji o niskiej podłodze i dostępności przystanków w danych statycznych.

### GTFS-Realtime ZTP Kraków (prognozy przyjazdów, pozycje pojazdów)
Adres: https://gtfs.ztp.krakow.pl/
Status licencji: **DO POTWIERDZENIA**

- **Do czego używamy:** Przyjazdy na żywo i flaga dostępności POJAZDU (tramwaje)
- **Wydawca:** Zarząd Transportu Publicznego w Krakowie
- **Licencja / warunki:** Jak GTFS ZTP - do potwierdzenia
- **Oznaczenie źródła:** Źródło: ZTP Kraków (GTFS-Realtime)
- **Użycie komercyjne:** DO POTWIERDZENIA u ZTP.
- **Aktualność:** Odświeżane co kilkanaście sekund; u nas pamięć podręczna 20 s, po awarii najwyżej 10 min.
- **Jak weryfikujemy:** Flaga dostępności pochodzi od operatora i dotyczy pojazdu obsługującego kurs w tej chwili. Autobusy: brak danych (nie zgadujemy). Przy awarii źródła pokazujemy komunikat i sam rozkład.
- **Ograniczenia:** Brak pola opóźnienia w większości wpisów. Kursy dalej w przyszłości często bez przypisanego pojazdu.

### Deklaracja MPK Kraków: autobusy niskopodłogowe od 2018 r.
Adres: https://mpk.krakow.pl/artykul/13/dostepnosc-dla-osob-z-ograniczona-mobilnoscia
Status licencji: **DO POTWIERDZENIA**

- **Do czego używamy:** Autobusy: ocena „prawdopodobnie dostępny” (GTFS ZTP nie ma pola niskiej podłogi)
- **Wydawca:** Miejskie Przedsiębiorstwo Komunikacyjne S.A. w Krakowie
- **Licencja / warunki:** Informacja ze strony przewoźnika (nie zbiór danych); warunki ponownego wykorzystania do potwierdzenia
- **Oznaczenie źródła:** Źródło: MPK Kraków
- **Użycie komercyjne:** DO POTWIERDZENIA. Używamy faktu (deklaracji), nie kopiujemy tekstu.
- **Aktualność:** Strona bez daty publikacji, stan sprawdzony 2026-10-03.
- **Jak weryfikujemy:** Status „prawdopodobne”, nigdy „potwierdzone”: to deklaracja dla całej floty, nie sprawdzenie pojazdu. Flaga ZTP na żywo (jeśli jest) ma pierwszeństwo.
- **Ograniczenia:** Rampa może być niesprawna; część linii obsługują inni przewoźnicy (np. Mobilis); dostępność pojazdu to nie dostępność przystanku.

### Wykaz taboru tramwajowego (numer taborowy -> typ), TTSS
Adres: https://api.ttss.pl/vehicles/trams/
Status licencji: **DO POTWIERDZENIA**

- **Do czego używamy:** Sprawdzenie flagi ZTP dla tramwaju: typ taboru (niska/wysoka podłoga) vs flaga na żywo; wykrywanie sprzeczności
- **Wydawca:** Serwis społecznościowy api.ttss.pl (dane o taborze Krakowa)
- **Licencja / warunki:** Brak informacji o licencji; źródło nieoficjalne
- **Oznaczenie źródła:** Źródło: api.ttss.pl (wykaz taboru)
- **Użycie komercyjne:** DO POTWIERDZENIA. Wykaz mamy zapisany lokalnie (engine/data/tram_fleet.csv), strona nie jest odpytywana na żywo.
- **Aktualność:** Stan z 2026-10-03; tabor się zmienia - odświeżać okresowo.
- **Jak weryfikujemy:** Przypisanie typ -> podłoga (niska/wysoka) to nasza klasyfikacja do potwierdzenia u MPK. Rozbieżność z flagą ZTP pokazujemy jako „sprzeczne dane”.
- **Ograniczenia:** Źródło nieoficjalne; nie wszystkie pojazdy muszą być na liście.

### Granica obszaru demo (obręb Kraków-Śródmieście)
Adres: https://www.geoportal.gov.pl
Status licencji: **DO POTWIERDZENIA**

- **Do czego używamy:** Wielokąt, do którego przycinamy wszystkie dane (trasy, miejsca, adresy, przystanki)
- **Wydawca:** GUGiK / Państwowy Rejestr Granic (wg atrybutów pliku: PL.PZGIK.200, EGIB)
- **Licencja / warunki:** Plik przekazany przez zespół; warunki wykorzystania Państwowego Rejestru Granic do potwierdzenia
- **Oznaczenie źródła:** Źródło: GUGiK, Państwowy Rejestr Granic
- **Użycie komercyjne:** DO POTWIERDZENIA na stronie PRG / Geoportalu.
- **Aktualność:** Granica jednostki ewidencyjnej; data pliku do uzupełnienia.
- **Jak weryfikujemy:** Powierzchnia z geometrii (17,84 km²) zgadza się z atrybutem JPT_POWIER = 1787 ha.
- **Ograniczenia:** Granica administracyjna, a nie obszar chodzenia pieszego: trasy przy brzegu mogą urywać się na granicy.

### Zgłoszenia użytkowników
Status licencji: **warunki sprawdzone**

- **Do czego używamy:** Uzupełnienie i sprostowanie danych o dostępności miejsc
- **Wydawca:** Użytkownicy aplikacji (anonimowo, bez kont i danych osobowych)
- **Licencja / warunki:** Zgłoszenia dobrowolne, bez danych osobowych
- **Oznaczenie źródła:** Zgłoszenie użytkownika (niezweryfikowane)
- **Użycie komercyjne:** Własne dane projektu; regulamin zgłoszeń do przygotowania.
- **Aktualność:** Data zgłoszenia przy każdym wpisie.
- **Jak weryfikujemy:** Zawsze oznaczone jako niezweryfikowane (pewność 0,3), pokazywane osobno od innych źródeł. Ograniczenie liczby zgłoszeń (10 na godzinę z jednego adresu), czyszczenie treści. Sprzeczność ze źródłem = status „sprzeczne”.
- **Ograniczenia:** Możliwe nadużycia; weryfikacja (potwierdzenie przez właściciela lub kolejnych użytkowników) to kolejny etap.

### Naloty dronem i kontrole terenowe (własne dane projektu)
Status licencji: **DO POTWIERDZENIA**

- **Do czego używamy:** Data ostatniego sprawdzenia terenu oraz obserwacje z góry: zastawione chodniki, remonty, zniszczona nawierzchnia, wąski chodnik (surveys.yaml, data/raw/survey_observations.json)
- **Wydawca:** Zespół projektu / wykonawca nalotu
- **Licencja / warunki:** Własne dane projektu; zasady udostępniania do ustalenia z wykonawcą nalotu i zleceniodawcą.
- **Oznaczenie źródła:** Nalot dronem / kontrola terenowa: data w aplikacji
- **Użycie komercyjne:** Własne dane projektu. W repozytorium jest tylko wpis PRZYKŁADOWY (demo: true), oznaczony tak w aplikacji; prawdziwe loty wymagają sprawdzenia przepisów i zgód (BIZNES.md, sekcja 5).
- **Aktualność:** Cel: co 3 miesiące (interval_months). Dane starsze niż interwał są oznaczane jako nieświeże.
- **Jak weryfikujemy:** Obserwacja z lotu to stan z dnia nalotu (nie fakt o dostępności miejsca); nie zmienia wyboru trasy, tylko dodaje ostrzeżenie z datą. Aplikacja pokazuje, czego nalot nie obejmuje (szerokość drzwi, stopnie pod zadaszeniem, wnętrza).
- **Ograniczenia:** Dron nie widzi szerokości drzwi, stopni pod zadaszeniem, wnętrz ani niskich krawężników. Zdjęcia nie są publikowane (twarze, tablice rejestracyjne); w API są tylko punkty z typem.

## Źródła rozważone, jeszcze nieużyte

- **Portal Otwarte Dane Krakowa i ArcGIS Hub ZTP** (https://otwartedane.um.krakow.pl): ZTP publikuje m.in. lokalizacje wiat przystankowych, trasy dojścia do przystanków i punkty SIM. Nie sprawdziliśmy ich zawartości pod kątem dostępności ani licencji. Kandydat do kolejnego etapu.
- **Miejski System Informacji Przestrzennej (MSIP)** (https://msip.krakow.pl): Dane przestrzenne Krakowa (WMS/WFS). Zakres i warunki trzeba sprawdzić dla konkretnego zasobu. Kandydat do kolejnego etapu (np. krawężniki, przejścia).
- **dane.gov.pl** (https://dane.gov.pl): Ogólnopolski katalog - istotny przy skalowaniu na inne miasta (np. inne feedy GTFS, NMT dla całego kraju).
- **Nominatim i inne zewnętrzne geokodery** (https://nominatim.org): Świadomie nieużyte: limity publicznego serwera i ryzyko awarii na pokazie. Mamy lokalny geokoder na danych OSM.
