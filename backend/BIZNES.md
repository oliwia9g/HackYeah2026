# Model biznesowy i droga od prototypu do usługi

> Szkic do dopracowania przed prezentacją. Wszystko oznaczone **[założenie]** to hipoteza do zweryfikowania rozmowami z klientami,
> a nie wynik badań. Nie podajemy liczb rynkowych, których nie mamy ze źródła; miejsca na nie są oznaczone **[do uzupełnienia: źródło]**.
> Powiązane: `ODBIORCY_I_ADOPCJA.md` (dla kogo jest aplikacja i jak zachęcać do jej używania), `STORYTELLING.md` (opowieść do pokazu), `ARCHITEKTURA.md`.

## 1. Zasada nadrzędna
**Dla osób, którym aplikacja pomaga (wózek, wózek dziecięcy, niewidomi i słabowidzący, głusi, seniorzy, kobiety w ciąży) jest bezpłatna, bez konta i bez reklam.**
Płacą ci, którzy zyskują na tym, że dane o dostępności są kompletne, aktualne i wiarygodne. Dzięki temu: (1) nie zbieramy danych o użytkownikach (to dane o zdrowiu),
(2) nasz zysk rośnie wraz z jakością i świeżością danych, a nie z ich sprzedażą.

**Jedno zdanie:** sprzedajemy *zaufanie do danych o dostępności* (źródło, data, weryfikacja w terenie), a nie dostęp do użytkowników.

## 2. Dwie strony: kto korzysta, kto płaci
| Strona | Kto | Co dostaje | Płaci? |
|---|---|---|---|
| Użytkownicy | osoby z ograniczeniami, opiekunowie, seniorzy, rodzice z wózkiem, turyści (szczegóły: `ODBIORCY_I_ADOPCJA.md`) | trasy, najbliższe udogodnienia, karty miejsc, głos, tryb prosty | **nie** |
| Obiekty | hotele, restauracje, muzea, galerie, organizatorzy wydarzeń, zarządcy budynków | uczciwa karta dostępności do osadzenia, audyt, panel luk | tak |
| Instytucje | miasto, jednostki drogowe i transportowe, biura ds. osób z niepełnosprawnościami | stan chodników z lotu co kwartał, ranking barier, jakość danych | tak (umowa, grant) |
| Firmy cyfrowe | rezerwacje, turystyka, mapy | API z proweniencją danych | tak |
| Inne miasta | miasta w Polsce | wdrożenie białej etykiety | tak |

## 3. Problem po stronie płacących
| Kto | Problem | Co dostaje od nas |
|---|---|---|
| Hotele, restauracje, kina, muzea, organizatorzy wydarzeń | Goście pytają „czy da się wjechać wózkiem?”, a odpowiedź to ogólnik „obiekt dostępny”. Ryzyko rozczarowania, reklamacji, utraconych rezerwacji. | Karta dostępności do wstawienia na własną stronę (`/embed/place/{id}`, iframe bez JS) z uczciwym statusem i źródłem; panel „czego brakuje w moich danych” (`/api/gaps`) |
| Zarządcy nieruchomości, deweloperzy, centra handlowe, szpitale i urzędy | Muszą wykazywać zgodność z ustawą o zapewnianiu dostępności i oceniać stan obiektów (winda, toaleta, rampa, wejście) | Karta budynku z cechami (winda, rampa, toaleta, szerokość wejścia), raporty z audytów i znacznik „zweryfikowane w terenie” (status `potwierdzone`) |
| Platformy rezerwacyjne, aplikacje turystyczne i mapowe | Brak wiarygodnych, ustrukturyzowanych danych o dostępności z podaną proweniencją | API (trasy z przeszkodami, karty miejsc, eksport z proweniencją) |
| Miasto, jednostki drogowe i transportowe, biura ds. osób niepełnosprawnych | Nie wiedzą na bieżąco, gdzie chodnik jest zastawiony, rozkopany lub zniszczony, i gdzie dane są dziurawe | Kwartalny przegląd z lotu (obserwacje z datą), panel jakości danych (`/api/stats`), ranking barier (`/api/barriers`) |
| Inne miasta | Ten sam problem, brak narzędzia | Wdrożenie białej etykiety (`CITY_CONFIG`, `cities/TEMPLATE.yaml`) |

## 4. Strumienie przychodów (od najbardziej realnego)
1. **Audyty terenowe + znacznik „zweryfikowane”** – obiekt zamawia sprawdzenie (pomiar progu, szerokości drzwi, toalety, windy), wynik wchodzi jako fakt `potwierdzone` z datą i audytorem. To jedyny sposób, by przejść z „niezweryfikowane” do „potwierdzone” na dużą skalę; płaci ten, kto na tym zyskuje. Cena za audyt: **[założenie: zakres kilkuset zł za obiekt; zweryfikować z audytorami]**.
2. **Kwartalny przegląd z lotu („Odświeżenie danych”)** – umowa z miastem, jednostką drogową lub zarządcą dużego obszaru (kampus, osiedle, centrum handlowe): nalot co 3 miesiące, lista obserwacji (zastawiony chodnik, remont, zniszczona nawierzchnia, wąski chodnik), raport „co się zmieniło od poprzedniego razu”. Dla użytkowników widać w aplikacji, kiedy był ostatni nalot (sekcja 5). **[założenie: cena za km² lub za nalot; wyceniamy z operatorem drona, bez liczb w tej wersji]**.
3. **Subskrypcja na widżet dostępności** dla obiektów i organizatorów wydarzeń (karta osadzana na stronie, aktualizowana automatycznie z danych). Wersja podstawowa dla małych obiektów – bezpłatna z atrybucją, płatna bez atrybucji i z panelem. **[założenie: abonament miesięczny rzędu kilkudziesięciu zł; zweryfikować]**.
4. **API dla firm trzecich** (rezerwacje, turystyka, mapy): plan darmowy z limitem i atrybucją; płatny z umową SLA i licencją na eksport. Uwaga licencyjna: dane OSM mają share-alike (ODbL), więc **sprzedajemy usługę, aktualność, weryfikację i SLA, a nie „zamknięte dane”**; nasze własne audyty i zgłoszenia moderowane można licencjonować osobno.
5. **Wdrożenie w innym mieście / dla miasta**: jednorazowe wdrożenie (konfiguracja, adaptery GTFS i taboru) + roczna opłata utrzymaniowa i moderacja. Źródło: budżety miejskie, fundusze unijne i krajowe na dostępność **[do uzupełnienia: konkretne programy i terminy naborów]**.
6. **Granty i partnerstwa z organizacjami osób z niepełnosprawnościami** – finansują zbieranie danych (mapathony, audyty społecznościowe, nalot pilotażowy), nie rozwój produktu.

**Czego nie robimy:** nie sprzedajemy danych o użytkownikach, nie pokazujemy reklam, nie stawiamy płatnej ściany przed funkcją potrzebną do bezpiecznego przejścia trasy.

## 5. Program nalotów dronem: regularne odświeżanie danych
**Po co.** Przeszkody na chodnikach (zastawienia, remonty, zniszczona nawierzchnia) zmieniają się szybciej niż wpisy w OpenStreetMap, a wolontariusze nie obejdą całego obszaru co kwartał.
Dron daje przegląd całego obszaru w jeden dzień. Użytkownik widzi w aplikacji **kiedy dane z jego okolicy były ostatnio sprawdzone w terenie** i czy są jeszcze „świeże”.

**Rytm.** Domyślnie co 3 miesiące (`interval_months` w `surveys.yaml`). Dane starsze niż interwał oznaczamy jako nieświeże. Nalot doraźny (po zimie, dużym remoncie, przed wydarzeniem) = **[pomysł]**.

| Co nalot widzi | Czego nie widzi (i skąd to wiemy) |
|---|---|
| nawierzchnię, zastawione chodniki, remonty i wykopy, szerokość chodnika | szerokości drzwi, stopni pod zadaszeniem, wnętrz budynków, niskich krawężników (pomiar w cm) → OSM, audyty terenowe, zgłoszenia |
Pole `does_not_cover` jest widoczne w aplikacji (`/api/surveys`), żeby nikt nie odczytał „nalot był” jako „wszystko sprawdzone”.

**Jak dane trafiają do aplikacji (już działa w backendzie):**
1. Po nalocie dopisujemy wpis do `surveys.yaml` (data, typ, obszar, metoda, `covers`, `does_not_cover`, `next_planned`).
2. Obserwacje (punkty z typem: `zastawiony_chodnik`, `remont`, `nawierzchnia_zniszczona`, `waski_chodnik`, `przeszkoda`, `chodnik_zablokowany`) wpisuje się w szablon `surveys/TEMPLATE_obserwacje.csv` i importuje: `python -m pipeline.import_survey obserwacje.csv --survey nalot-2026-12`.
3. Aplikacja pokazuje: „Ostatni nalot: data, ile dni temu, świeże do …” (`/api/surveys`, `/api/surveys/at`, `meta.ostatni_nalot`), % trasy w obszarze ze świeżym nalotem (`routes[].properties.nalot`), warstwę obserwacji (`/api/surveys/observations`) i obserwacje wzdłuż trasy.

**Zasady uczciwości:** obserwacja z lotu to *obserwacja z datą*, nie fakt o dostępności miejsca; nie zmienia automatycznie wyboru trasy (decyzję podejmuje człowiek: moderator/audytor);
wpis oznaczony `demo: true` jest w aplikacji podpisany „PRZYKŁADOWE – dane demo” i **nie wolno go przedstawiać jako prawdziwego nalotu** (w repo jest taki jeden wpis demo).

**Do zweryfikowania, zanim obiecamy to publicznie (nie sprawdziliśmy tego podczas hackathonu):**
- uprawnienia operatora i kategoria operacji według unijnych i krajowych przepisów o dronach **[zweryfikować: aktualne przepisy, rejestracja operatora]**;
- strefy i ograniczenia lotnicze w centrum Krakowa (blisko lotniska), zgoda zarządcy przestrzeni powietrznej i miasta **[zweryfikować na oficjalnej mapie stref]**;
- loty w gęstej zabudowie i nad ludźmi, ubezpieczenie OC operatora **[zweryfikować]**;
- prywatność: zdjęcia mogą zawierać twarze i tablice rejestracyjne → nie publikujemy zdjęć, tylko wektorowe obserwacje; surowe materiały trzymamy krótko i poza repozytorium **[do uzgodnienia: RODO, okres przechowywania]**.

**Plan B, gdy dron jest niemożliwy lub za drogi:** ten sam rejestr obsługuje `spacer_terenowy` i `audyt` (typy w `surveys.yaml`). Spacer z telefonem i mapathon dają ten sam efekt w aplikacji (data ostatniej kontroli, obserwacje), tylko wolniej i na mniejszym obszarze.

**Koszty nalotu (bez liczb, do wyceny):** operator z uprawnieniami (dzień pracy), przygotowanie i wynik (adnotacja przeszkód ręcznie lub półautomatycznie), moderacja, ewentualne opłaty za zgody. **[do uzupełnienia: wycena z operatorem]**.

## 6. Konkurencja i przewaga (do zweryfikowania przed prezentacją)
Przegląd istniejących rozwiązań (mapy ogólne, serwisy ocen miejsc, aplikacje typu „mapa dostępności”) **[do uzupełnienia: sprawdzić 3–5 konkretnych produktów i opisać, czego im brakuje]**.
Nasze realne różnice, które da się pokazać w demo:
- **uczciwość danych**: `brak danych` ≠ `dostępne`, każdy fakt ma źródło, datę i status, sprzeczności są pokazywane, zgłoszenia oznaczone;
- **świeżość widoczna dla użytkownika**: „ostatni nalot / kontrola w terenie: data”, a nie tylko „dane z OSM”;
- **przeszkody ze współrzędnymi i głosem** (zapowiedź „za 30 m: schody”) oraz kilka wariantów trasy z ceną objazdu;
- **budynki i ich cechy** (winda, rampa, toaleta, szerokość wejścia) oraz **toalety jako udogodnienie** liczone chodnikami wg wymagań;
- **dostępność pojazdu z podstawą** (flaga operatora + typ taboru), a nie samo „niskopodłogowy”;
- **preferencje zamiast deklaracji** – bez nazywania własnej niepełnosprawności; 6 gotowych grup, które można dowolnie zmienić;
- **profil na urządzeniu użytkownika** zamiast konta na serwerze (dane o zdrowiu zostają u użytkownika);
- **interfejs dopasowany do osoby**: tryb prosty („dla babci”), tryb skupienia (np. ADHD), asystent głosowy, „gdzie jestem”;
- **otwarta architektura**: nowe źródło, kategoria, obszar i miasto bez przepisywania kodu;
- **pętla poprawiania** do źródła (OSM) i ranking, gdzie dane są najbardziej potrzebne.

## 7. Struktura kosztów (szacunek)
| Pozycja | Skala | Uwagi |
|---|---|---|
| Serwery, domena, monitoring | niskie, rzędu kilkunastu € miesięcznie na start **[założenie]** | `ARCHITEKTURA.md` §4 |
| Moderacja zgłoszeń | czas ludzi: np. kilka godzin tygodniowo na pilotaż **[założenie]** | zgłoszenia zostają `niezweryfikowane` do czasu decyzji |
| Audyty terenowe | zmienne, głównie praca; opłacane przez zamawiającego | to koszt przenoszony na klienta |
| Nalot dronem co kwartał | do wyceny z operatorem **[do uzupełnienia]** | finansowany umową z miastem/zarządcą lub grantem; plan B: spacer terenowy |
| Rozwój i utrzymanie | zespół; po pilotażu opłacany z przychodów i grantów | |
| Własny serwer Overpass | dopiero przy większej skali | publiczne serwery mają limity |

## 8. Plan: od prototypu do usługi
| Etap | Czas **[założenie]** | Cel | Gotowe, gdy |
|---|---|---|---|
| 0. Domknięcie prototypu | po hackathonie, ok. 2–4 tyg. | potwierdzone licencje (ZTP, MPK, TTSS, PRG), audyt WCAG narzędziem i czytnikiem, wdrożenie demo na własnym serwerze, test tekstów z osobami z grup docelowych | `sources.yaml` bez `do_potwierdzenia`; raport axe/Lighthouse; adres publiczny |
| 1. Pilotaż w Krakowie | ok. 1–3 mies. | cały Kraków (nie tylko Śródmieście), baza zgłoszeń (PostgreSQL), moderacja, pierwsze mapathony, **pierwszy prawdziwy nalot lub spacer terenowy** w wybranym rejonie (po sprawdzeniu przepisów) | pomiar RAM/czasu startu; ≥ 1 organizacja prowadzi moderację; wpis w `surveys.yaml` bez `demo` |
| 2. Pierwsze przychody | ok. 3–6 mies. | 3–5 obiektów z widżetem i płatnym audytem; **drugi nalot po 3 miesiącach (sprawdzenie rytmu)**; testy z użytkownikami z grup docelowych | umowy pilotażowe; wskaźniki użycia (bez danych osobowych) |
| 3. API dla partnerów | ok. 6–9 mies. | wersjonowanie API, klucze, SLA, dokumentacja | pierwszy partner na umowie |
| 4. Drugie miasto | ok. 9–12 mies. | wdrożenie z `CITY_CONFIG`, adapter operatora transportu | działający pilot w drugim mieście |

## 9. Ryzyka i jak je ograniczamy
- **Jakość danych OSM jest niska** (np. krawężniki prawie bez tagów) → pokazujemy luki wprost, `/api/gaps` kieruje wysiłek tam, gdzie najbardziej pomoże; audyty płatne przez zainteresowanych.
- **Dron: przepisy, strefy, prywatność, koszt** → lista „do zweryfikowania” w sekcji 5, plan B (spacer terenowy), brak zdjęć w publicznym API, wpisy demo wyraźnie oznaczone.
- **Fałszywe poczucie pewności po nalocie** („był dron, więc jest dobrze”) → w aplikacji zawsze widać, czego nalot nie obejmuje (`does_not_cover`) i do kiedy dane są świeże.
- **Licencje źródeł (ZTP, MPK)** → rejestr źródeł z oznaczonym statusem, potwierdzenie przed komercyjnym użyciem.
- **Odpowiedzialność za błędną informację** („dostępne”, a nie jest) → domyślnie „brak danych”, daty i źródła, komunikat „sprawdź przed wizytą”, wyraźny podział `potwierdzone` / `niezweryfikowane`; regulamin i polityka prywatności **[do zrobienia]**.
- **Dane wrażliwe** (wymagania dostępnościowe to dane o zdrowiu) → brak kont na serwerze, profil w pliku na urządzeniu, GPS nie jest zapisywany.
- **Spam i nadużycia w zgłoszeniach** → limity, moderacja, zgłoszenia nigdy nie nadpisują źródła.
- **Zależność od jednego operatora transportu** → adaptery per miasto, bezpieczne wartości domyślne (`unknown`).
- **Wypalenie społeczności** → rzeczywisty efekt: poprawka w OSM trafia do wszystkich, a nie tylko do nas.

## 10. Wskaźniki sukcesu (mierzone bez danych osobowych)
Pokrycie danych (`/api/stats`: % miejsc z atrybutem `wheelchair`, % przejść z danymi o krawężniku), świeżość (% faktów < 12 mies.), **% obszaru ze świeżym nalotem lub kontrolą w terenie** (`/api/surveys`),
liczba poprawek w OSM wywołanych z aplikacji (linki `osm_edit_url`), liczba obiektów ze znacznikiem „zweryfikowane”, liczba wdrożonych widżetów, liczba wywołań API partnerów,
liczba osób w testach użyteczności z grup docelowych i ich ocena zrozumiałości trybu prostego **[do zmierzenia]**. Użycie liczymy zbiorczo (liczniki zapytań), bez identyfikatorów i bez adresów IP.
