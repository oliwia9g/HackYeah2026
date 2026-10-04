import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { loadUi } from "../prefs";
import "../kbb.css";

// Strona „O danych”: skąd są dane, jak często, co gdy źródło padnie, jak dodać źródło/miasto,
// dostępność (WCAG), hosting, prywatność, licencje. Wartości „na żywo” pochodzą z API,
// reszta to opis naszego rozwiązania (patrz ARCHITEKTURA.md w repozytorium backendu).

const LICENCJA = {
  potwierdzona: "licencja potwierdzona",
  do_potwierdzenia: "licencja do potwierdzenia",
};

const ODSWIEZANIE = [
  ["OpenStreetMap (Overpass)", "sieć piesza, obiekty, przejścia, krawężniki, tagi dostępności", "raz na dobę lub tydzień (zakładamy)", "Aplikacja działa na ostatnio zapisanych plikach; przy każdym fakcie widać datę pobrania; pokazujemy baner o danych zapisanych."],
  ["GUGiK – model terenu (NMT)", "nachylenie chodników", "rzadko, zakładamy raz w roku", "Zostaje nachylenie z ostatniego pliku, źródło jest zapisane przy każdym odcinku."],
  ["ZTP Kraków – rozkład (GTFS)", "przystanki i odjazdy z rozkładu", "codziennie", "Ostatni zapisany rozkład; data jest w stanie systemu."],
  ["ZTP Kraków – dane na żywo (GTFS-Realtime)", "prognozy przyjazdów, pojazd", "na żądanie, pamięć podręczna 20 s", "Do 10 minut pokazujemy dane oznaczone jako nieświeże, potem tylko rozkład. Trasy działają bez danych na żywo."],
  ["MPK / wykaz taboru", "czy tramwaj lub autobus ma niską podłogę", "ręcznie, gdy zmieni się flota (zakładamy: co kwartał)", "Brak informacji oznacza „nie wiadomo”, nigdy „dostępny”."],
  ["Naloty dronem i kontrole terenowe", "zastawione chodniki, remonty, zniszczona nawierzchnia", "cel: co 3 miesiące", "Brak nalotu to „brak nalotu”. Starsze dane oznaczamy jako nieświeże."],
  ["Zgłoszenia użytkowników", "poprawki i uzupełnienia dostępności miejsc", "na bieżąco", "Zawsze „niezweryfikowane”, pokazywane obok danych ze źródła, nigdy ich nie nadpisują."],
];

const WCAG_ZROBIONE = [
  "Cała strona działa z klawiatury (Tab, Enter, Spacja, strzałki w suwaku), fokus jest zawsze widoczny.",
  "Tekstowa alternatywa dla mapy: kroki trasy, zagrożenia, wyniki wyszukiwania i „najbliższe miejsca” są też w listach obok mapy.",
  "Informacje nie opierają się tylko na kolorze: status i waga zagrożenia mają nazwę tekstową i ikonę.",
  "Regiony czytane przez czytnik ekranu (aria-live) przy wynikach i błędach, opisane przyciski i pola.",
  "Wysoki kontrast, jasny i ciemny motyw, cztery wielkości liter (100–175%).",
  "Tryb prosty: duże przyciski, krótkie zdania, mniej opcji.",
  "Czytanie na głos po najechaniu lub wejściu fokusem, przycisk wyciszenia; polecenia głosowe i pole tekstowe jako alternatywa.",
  "Wskazywanie punktów bez przeciągania mapy: adres, kliknięcie albo przycisk „Moja pozycja”.",
  "Poszanowanie ustawienia systemu „ogranicz animacje”.",
];

const WCAG_DO_ZROBIENIA = [
  "Test z prawdziwym czytnikiem ekranu (NVDA, VoiceOver, TalkBack) – jeszcze nie wykonany.",
  "Pełny audyt narzędziowy i ręczny (Lighthouse, axe, lista WCAG 2.2 AA) na wszystkich ekranach.",
  "Testy z użytkownikami z niepełnosprawnościami (wózek, niewidomi, osoby starsze) – jeszcze ich nie robiliśmy.",
  "Dostępność samej mapy graficznej (MapLibre) jest ograniczona; dlatego wszystko jest też w listach.",
  "Przycisk „Moja pozycja” i mikrofon zależą od przeglądarki; w niektórych przeglądarkach głos nie działa.",
  "Polityka prywatności i regulamin zgłoszeń – do napisania.",
];

function Sekcja({ id, title, children }) {
  return (
    <section className="kbb-card kbb-data-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

function Zrodlo({ s }) {
  const status = LICENCJA[s.license_status] || s.license_status;
  return (
    <li className="kbb-data-source">
      <h3>
        {s.url ? (
          <a href={s.url} target="_blank" rel="noreferrer">
            {s.name}
          </a>
        ) : (
          s.name
        )}
      </h3>
      <p className="kbb-small kbb-muted">
        Wydawca: {s.publisher}. <span className="kbb-badge">{status}</span>
      </p>
      <dl className="kbb-dl">
        <dt>Do czego używamy</dt>
        <dd>{s.used_for}</dd>
        <dt>Licencja</dt>
        <dd>{s.license}</dd>
        <dt>Aktualność</dt>
        <dd>{s.currency}</dd>
        <dt>Jak sprawdzamy wiarygodność</dt>
        <dd>{s.verification}</dd>
        <dt>Ograniczenia</dt>
        <dd>{s.limitations}</dd>
        {s.data_retrieved_at && (
          <>
            <dt>Ostatnie pobranie</dt>
            <dd>{s.data_retrieved_at}</dd>
          </>
        )}
      </dl>
    </li>
  );
}

export default function DataPage({ theme }) {
  const [ui] = useState(loadUi);
  const [sources, setSources] = useState(null);
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    document.title = "O danych – Kraków Bez Barier";
    api.sources().then(setSources).catch((e) => setError(e.message));
    api.stats().then(setStats).catch(() => {});
    api.health().then(setHealth).catch(() => {});
  }, []);

  const dark = theme === "dark";
  const pokrycie = stats?.miejsca?.pokrycie_atrybutow ? Object.values(stats.miejsca.pokrycie_atrybutow) : [];

  return (
    <div
      className="kbb"
      data-theme={dark ? "dark" : "light"}
      data-contrast={ui.contrast}
      data-mode={ui.mode === "prosty" ? "prosty" : "standard"}
      style={{ "--font-scale": ui.font_scale }}
    >
      <div className="kbb-wrap kbb-data">
        <header className="kbb-header">
          <div>
            <p className="eyebrow">Kraków Bez Barier</p>
            <h1>O danych i o tym, jak to działa</h1>
            <p className="kbb-muted kbb-lead">
              Skąd bierzemy informacje, jak często je odświeżamy, co robimy, gdy coś zawiedzie, i jak ktoś inny
              może to wdrożyć u siebie. Piszemy też wprost, czego jeszcze nie sprawdziliśmy.
            </p>
          </div>
          <p>
            <Link className="kbb-btn" to="/mappage">
              Wróć do mapy
            </Link>
          </p>
        </header>

        <nav className="kbb-card" aria-label="Spis treści">
          <ol className="kbb-toc">
            <li><a href="#zasada">Zasada: brak danych to nie „dostępne”</a></li>
            <li><a href="#stan">Stan danych teraz</a></li>
            <li><a href="#zrodla">Źródła danych i licencje</a></li>
            <li><a href="#odswiezanie">Jak często i co przy awarii</a></li>
            <li><a href="#architektura">Jak to jest zbudowane</a></li>
            <li><a href="#rozbudowa">Jak dodać źródło, kategorię, obszar, miasto</a></li>
            <li><a href="#wiarygodnosc">Wiarygodność i poprawianie błędów</a></li>
            <li><a href="#wcag">Dostępność (WCAG 2.2 AA)</a></li>
            <li><a href="#prywatnosc">Prywatność i bezpieczeństwo</a></li>
            <li><a href="#hosting">Hosting, utrzymanie i koszty</a></li>
            <li><a href="#licencje">Zależności i ponowne użycie</a></li>
          </ol>
        </nav>

        <Sekcja id="zasada" title="Zasada: brak danych to nie „dostępne”">
          <p>
            Każda informacja ma źródło, datę pobrania, pewność i status: <strong>potwierdzone</strong>,{" "}
            <strong>prawdopodobne</strong>, <strong>niezweryfikowane</strong>, <strong>sprzeczne</strong> albo{" "}
            <strong>brak danych</strong>. Jeśli w źródle nie ma informacji o dostępności, pokazujemy „brak danych”, nigdy
            „dostępne”. Zgłoszenia mieszkańców są zawsze oznaczone jako niezweryfikowane i widoczne obok danych ze
            źródła.
          </p>
          <p className="kbb-muted kbb-small">
            Nie korzystamy z żadnych wewnętrznych systemów Urzędu Miasta. Wszystkie dane są publiczne.
          </p>
        </Sekcja>

        <Sekcja id="stan" title="Stan danych teraz">
          {health ? (
            <p>
              Stan systemu: <strong>{health.status === "ok" ? "wszystko działa" : health.status === "czesciowo" ? "część źródeł niedostępna" : health.status}</strong>
              {health.niedostepne?.length ? (
                <>
                  . Niedostępne teraz: {health.niedostepne.join(", ").replace(/_/g, " ")}. Aplikacja pokazuje wtedy to,
                  co ma zapisane, i mówi o tym wprost.
                </>
              ) : (
                "."
              )}
            </p>
          ) : (
            <p className="kbb-muted">Sprawdzam stan serwera…</p>
          )}
          {stats && (
            <>
              <p>
                W obszarze demo mamy <strong>{stats.miejsca?.razem}</strong> miejsc (w tym{" "}
                {stats.miejsca?.z_nazwa} z nazwą) i <strong>{stats.siec_piesza?.dlugosc_km} km</strong> sieci pieszej (
                {stats.siec_piesza?.odcinkow} odcinków).
              </p>
              {pokrycie.length > 0 && (
                <div className="kbb-table-wrap">
                <table className="kbb-table">
                  <caption>Ile miejsc ma daną informację (pozostałe: brak danych)</caption>
                  <thead>
                    <tr>
                      <th scope="col">Informacja</th>
                      <th scope="col">Miejsc</th>
                      <th scope="col">Udział</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pokrycie.map((p) => (
                      <tr key={p.label}>
                        <th scope="row">{p.label}</th>
                        <td>{p.miejsc}</td>
                        <td>{p.pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              )}
              {stats.uwaga && <p className="kbb-muted kbb-small">{stats.uwaga}</p>}
            </>
          )}
        </Sekcja>

        <Sekcja id="zrodla" title="Źródła danych i licencje">
          {error && <p role="alert">Nie udało się pobrać listy źródeł: {error}</p>}
          {!sources && !error && <p className="kbb-muted">Wczytuję źródła…</p>}
          {sources && (
            <>
              <p>{sources.rule}</p>
              <ul className="kbb-data-sources">
                {sources.used.map((s) => (
                  <Zrodlo key={s.id} s={s} />
                ))}
              </ul>
              {sources.considered_not_used?.length > 0 && (
                <>
                  <h3>Rozważane, jeszcze nieużyte</h3>
                  <ul>
                    {sources.considered_not_used.map((s) => (
                      <li key={s.name}>
                        <a href={s.url} target="_blank" rel="noreferrer">
                          {s.name}
                        </a>
                        : {s.note}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </Sekcja>

        <Sekcja id="odswiezanie" title="Jak często odświeżamy i co przy awarii">
          <div className="kbb-table-wrap">
            <table className="kbb-table">
              <caption>Źródła, częstotliwość i zachowanie przy awarii (wartości oznaczone „zakładamy” to plan, nie pomiar)</caption>
              <thead>
                <tr>
                  <th scope="col">Źródło</th>
                  <th scope="col">Co bierzemy</th>
                  <th scope="col">Jak często</th>
                  <th scope="col">Gdy źródło nie działa</th>
                </tr>
              </thead>
              <tbody>
                {ODSWIEZANIE.map(([a, b, c, d]) => (
                  <tr key={a}>
                    <th scope="row">{a}</th>
                    <td>{b}</td>
                    <td>{c}</td>
                    <td>{d}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Sekcja>

        <Sekcja id="architektura" title="Jak to jest zbudowane">
          <p>Pobieranie danych jest oddzielone od tego, co widzi użytkownik. Dzięki temu awaria źródła nie wyłącza aplikacji.</p>
          <ol>
            <li><strong>Pobieranie</strong> (offline, np. raz na dobę): skrypty zapisują dane do plików w jednym wspólnym formacie faktów (obiekt, cecha, wartość, źródło, data, pewność, status).</li>
            <li><strong>Dane</strong>: pliki GeoJSON/CSV/JSON, standardowy GTFS. Bez baz zależnych od jednego dostawcy.</li>
            <li><strong>Serwer (API)</strong>: wczytuje pliki, liczy trasy z uwzględnieniem wymagań i zwraca gotowe teksty. Poza danymi na żywo z ZTP nie woła żadnych usług zewnętrznych.</li>
            <li><strong>Aplikacja (ta strona)</strong>: wyświetla odpowiedzi API. Nie zna żadnego źródła danych.</li>
          </ol>
          <p className="kbb-muted kbb-small">
            Przepływ: źródła zewnętrzne → pobieranie → pliki z faktami → API → ta aplikacja i widżet do osadzania na
            innych stronach.
          </p>
        </Sekcja>

        <Sekcja id="rozbudowa" title="Jak dodać źródło, kategorię, obszar, miasto">
          <ul>
            <li><strong>Nowe źródło:</strong> wpis w rejestrze źródeł (licencja, aktualność, ograniczenia) + skrypt zapisujący fakty w tym samym formacie + jeden krok na liście pobierania. API i aplikacja zmieniać nie trzeba.</li>
            <li><strong>Nowa kategoria obiektów lub cecha:</strong> dopisanie znacznika w konfiguracji pobierania i etykiety w API.</li>
            <li><strong>Nowy obszar w tym samym mieście:</strong> podmiana pliku z granicą obszaru i ponowne pobranie danych.</li>
            <li><strong>Nowe miasto:</strong> kopia pliku konfiguracyjnego miasta (granica, adresy rozkładów) i uruchomienie pobierania. Część piesza (OpenStreetMap i model terenu) działa w całej Polsce; część komunikacji zależy od lokalnego przewoźnika i wymaga własnego adaptera (bez niego pojazdy mają status „nie wiadomo”). Na drugim mieście jeszcze tego nie sprawdziliśmy.</li>
          </ul>
        </Sekcja>

        <Sekcja id="wiarygodnosc" title="Wiarygodność i poprawianie błędów">
          <ul>
            <li>Przy każdej informacji widać źródło, datę i status. Data ostatniej edycji w OpenStreetMap daje słabszy status niż data sprawdzenia.</li>
            <li>Zgłoszenie z aplikacji jest „niezweryfikowane”. Jeśli przeczy źródłu, status to „sprzeczne” i pokazujemy obie wersje.</li>
            <li>Moderator może zgłoszenie zaakceptować lub odrzucić. Zgłoszenia nigdy nie nadpisują danych źródłowych.</li>
            <li>Błąd w danych można też poprawić u źródła: przy miejscach są linki do edycji w OpenStreetMap, a poprawka trafia do wszystkich jego użytkowników.</li>
            <li>Mapa „luk” wskazuje, gdzie poprawka jest najbardziej potrzebna.</li>
          </ul>
        </Sekcja>

        <Sekcja id="wcag" title="Dostępność (cel: WCAG 2.2, poziom AA)">
          <p>Dążymy do zgodności z WCAG 2.2 AA. Poniżej uczciwy stan: to, co zrobione, i to, czego jeszcze nie sprawdziliśmy.</p>
          <h3>Zrobione</h3>
          <ul>{WCAG_ZROBIONE.map((t) => <li key={t}>{t}</li>)}</ul>
          <h3>Do zrobienia</h3>
          <ul>{WCAG_DO_ZROBIENIA.map((t) => <li key={t}>{t}</li>)}</ul>
        </Sekcja>

        <Sekcja id="prywatnosc" title="Prywatność i bezpieczeństwo">
          <ul>
            <li>Nie ma kont ani rejestracji. Nie pytamy o niepełnosprawność: podajesz parametry trasy (np. bez schodów), a nazwy grup są tylko skrótami do gotowych zestawów.</li>
            <li>Ustawienia zostają w Twojej przeglądarce. Możesz zapisać je do pliku i wczytać na innym urządzeniu. Serwer tylko sprawdza poprawność pliku i niczego nie zapisuje.</li>
            <li>Pozycja z urządzenia jest pobierana dopiero po kliknięciu i nie jest zapisywana na serwerze.</li>
            <li>Rozpoznawanie i czytanie mowy robi przeglądarka; do serwera trafia tylko tekst polecenia. Przeglądarka może korzystać z usługi swojego dostawcy.</li>
            <li>Zgłoszenia nie zawierają danych osobowych. Limit zgłoszeń na adres chroni przed nadużyciami; adresów IP nie zapisujemy.</li>
            <li>Zabezpieczenia: walidacja wejścia, czyszczenie znaczników, nagłówki bezpieczeństwa, ograniczony CORS, moderacja chroniona tokenem.</li>
            <li>Do zrobienia: limity na serwerze pośredniczącym, HTTPS na produkcji, audyt zależności, kopie zapasowe zgłoszeń, polityka prywatności.</li>
          </ul>
        </Sekcja>

        <Sekcja id="hosting" title="Hosting, utrzymanie i koszty (propozycja)">
          <ul>
            <li><strong>Gdzie:</strong> mały serwer w UE (VPS lub PaaS) na koncie podmiotu prowadzącego projekt (np. stowarzyszenie lub spółka), poza infrastrukturą UMK. Aplikacja to statyczne pliki na dowolnym hostingu.</li>
            <li><strong>Kto odpowiada:</strong> podmiot prowadzący projekt: aktualizacje danych, moderacja zgłoszeń, kontakt. Miasto może przejąć hosting bez migracji, bo kod i dane są otwarte i przenośne.</li>
            <li><strong>Koszt (szacunek, do sprawdzenia w cennikach):</strong> serwer ok. 5–15 € miesięcznie, domena kilkadziesiąt zł rocznie, hosting statyczny 0 €. Największy koszt to praca ludzka: moderacja i kontrole terenowe, nie serwery.</li>
            <li><strong>Skala:</strong> dla Śródmieścia dane mieszczą się w pamięci. Dla całego Krakowa trzeba to jeszcze zmierzyć.</li>
          </ul>
        </Sekcja>

        <Sekcja id="licencje" title="Zależności, licencje i ponowne użycie">
          <ul>
            <li>Serwer: Python, FastAPI i biblioteki open source (m.in. OSMnx, GeoPandas, NetworkX). Aplikacja: React, Vite, MapLibre.</li>
            <li>Dane z OpenStreetMap są na licencji ODbL (trzeba podać autorów i udostępniać pochodne bazy na tej samej licencji). Licencje części źródeł (ZTP, MPK, granica obszaru) są jeszcze do potwierdzenia, co widać przy źródłach wyżej.</li>
            <li>Podkład mapy pochodzi z zewnętrznego serwera kafelków. Przed użyciem komercyjnym trzeba sprawdzić jego warunki lub użyć własnego.</li>
            <li>Zależności i ich licencje wymagają jeszcze formalnego przeglądu.</li>
            <li>Rozwiązanie nie jest związane z jednym dostawcą chmury: wystarczy zwykły proces serwera i pliki.</li>
          </ul>
        </Sekcja>

        <p className="kbb-muted kbb-small">
          Podkład mapy: zewnętrzny dostawca kafelków. Dane o dostępności: © współtwórcy OpenStreetMap i inne źródła
          wymienione wyżej.
        </p>
      </div>
    </div>
  );
}
