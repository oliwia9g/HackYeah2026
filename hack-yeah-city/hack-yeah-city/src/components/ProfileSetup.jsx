import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import '../ProfileSetup.css';
import { api } from '../api';
import { setAutoRead, speak } from '../speech';
import {
  buildProfileFile,
  loadUi,
  preferencesFromValidated,
  readGroup,
  saveUi,
  saveUser,
} from '../prefs';

const profileDanych = {
  wozek: {
    nazwa: 'Osoba poruszająca się na wózku',
    ikona: '/disabled.png',
    ustawienia: {
      bezSchodow: true,
      maxNachylenie: 6,
      szerokoscPrzejscia: 0.9,
      niskieKrawedzniki: true,
      gladszaNawierzchnia: true,
      prowadzenieDotykowe: false,
      sygnalDzwiekowy: false,
      oswietlenie: false,
      lawkaCoXm: 500,
      szerokoscAktywna: true,
      lawkiAktywne: false,
      toaleta: true,
      winda: true,
      przewijak: false,
      petla: false,
    }
  },
  wozek_dzieciecy: {
    nazwa: 'Osoba z wózkiem dziecięcym',
    ikona: '/little-kid.png',
    ustawienia: {
      bezSchodow: true,
      maxNachylenie: 8,
      szerokoscPrzejscia: 0.7,
      niskieKrawedzniki: true,
      gladszaNawierzchnia: false,
      prowadzenieDotykowe: false,
      sygnalDzwiekowy: false,
      oswietlenie: false,
      lawkaCoXm: 500,
      szerokoscAktywna: true,
      lawkiAktywne: false,
      toaleta: true,
      winda: true,
      przewijak: true,
      petla: false,
    }
  },
  wzrok: {
    nazwa: 'Osoba niewidoma lub słabowidząca',
    ikona: '/eye.png',
    ustawienia: {
      bezSchodow: false,
      maxNachylenie: 12,
      szerokoscPrzejscia: 0.7,
      niskieKrawedzniki: false,
      gladszaNawierzchnia: false,
      prowadzenieDotykowe: true,
      sygnalDzwiekowy: true,
      oswietlenie: true,
      lawkaCoXm: 500,
      szerokoscAktywna: false,
      lawkiAktywne: false,
      toaleta: false,
      winda: false,
      przewijak: false,
      petla: false,
    }
  },
  sluch: {
    nazwa: 'Osoba głucha lub niedosłysząca',
    ikona: '/ear.png',
    ustawienia: {
      bezSchodow: false,
      maxNachylenie: 12,
      szerokoscPrzejscia: 0.7,
      niskieKrawedzniki: false,
      gladszaNawierzchnia: false,
      prowadzenieDotykowe: false,
      sygnalDzwiekowy: false,
      oswietlenie: false,
      lawkaCoXm: 500,
      szerokoscAktywna: false,
      lawkiAktywne: false,
      toaleta: false,
      winda: false,
      przewijak: false,
      petla: true,
    }
  },
  senior: {
    nazwa: 'Osoba starsza',
    ikona: '/old-man.png',
    ustawienia: {
      bezSchodow: false,
      maxNachylenie: 8,
      szerokoscPrzejscia: 0.8,
      niskieKrawedzniki: true,
      gladszaNawierzchnia: true,
      prowadzenieDotykowe: false,
      sygnalDzwiekowy: false,
      oswietlenie: false,
      lawkaCoXm: 300,
      szerokoscAktywna: false,
      lawkiAktywne: true,
      toaleta: true,
      winda: false,
      przewijak: false,
      petla: false,
    }
  },
  ciaza: {
    nazwa: 'Kobieta w ciąży',
    ikona: '/pregnant.png',
    ustawienia: {
      bezSchodow: false,
      maxNachylenie: 8,
      szerokoscPrzejscia: 0.8,
      niskieKrawedzniki: false,
      gladszaNawierzchnia: true,
      prowadzenieDotykowe: false,
      sygnalDzwiekowy: false,
      oswietlenie: false,
      lawkaCoXm: 300,
      szerokoscAktywna: false,
      lawkiAktywne: true,
      toaleta: true,
      winda: false,
      przewijak: false,
      petla: false,
    }
  }
};

const setupProfileByHomeProfile = {
  wozek_inwalidzki: 'wozek',
  wozek_dziecko: 'wozek_dzieciecy',
  niewidomy_slabowidzacy: 'wzrok',
  gluchy_niedoslyszacy: 'sluch',
  senior: 'senior',
  ciaza: 'ciaza',
};

const homeProfileBySetupProfile = Object.fromEntries(
  Object.entries(setupProfileByHomeProfile).map(([homeProfile, setupProfile]) => [
    setupProfile,
    homeProfile,
  ])
);

const defaultPreferences = {
  bezSchodow: false,
  maxNachylenie: 12,
  szerokoscPrzejscia: 0.9,
  niskieKrawedzniki: false,
  gladszaNawierzchnia: false,
  prowadzenieDotykowe: false,
  sygnalDzwiekowy: false,
  oswietlenie: false,
  lawkaCoXm: 500,
  szerokoscAktywna: false,
  lawkiAktywne: false,
  toaleta: false,
  winda: false,
  przewijak: false,
  petla: false,
  tempoMarszu: 'standard',
};

function readSavedProfile() {
  const saved = localStorage.getItem('userAccessibilityProfile');
  if (!saved) return null;

  try {
    const parsed = JSON.parse(saved);
    return typeof parsed === 'string' ? parsed : null;
  } catch {
    return saved;
  }
}

function getInitialSetupProfile() {
  const homeProfile = readSavedProfile();
  const matchingSetupProfile = setupProfileByHomeProfile[homeProfile];
  if (matchingSetupProfile) return matchingSetupProfile;

  const savedUser = localStorage.getItem('ponadBarieramiUser');
  if (savedUser) {
    try {
      const profile = JSON.parse(savedUser).profil;
      if (profileDanych[profile]) return profile;
    } catch {
      // Ignore invalid saved settings and fall back to the home-page profile.
    }
  }

  return null;
}

function getInitialPreferences() {
  const homeProfile = readSavedProfile();
  const matchingSetupProfile = setupProfileByHomeProfile[homeProfile];
  if (matchingSetupProfile) {
    return {
      ...defaultPreferences,
      ...profileDanych[matchingSetupProfile].ustawienia,
    };
  }

  const savedUser = localStorage.getItem('ponadBarieramiUser');
  if (savedUser) {
    try {
      const preferences = JSON.parse(savedUser).preferencje;
      if (preferences) return { ...defaultPreferences, ...preferences };
    } catch {
      // Ignore invalid saved settings and use the selected profile defaults.
    }
  }

  const setupProfile = getInitialSetupProfile();
  return {
    ...defaultPreferences,
    ...(profileDanych[setupProfile]?.ustawienia || {}),
  };
}

const NACHYLENIE = [
  { id: 3, tytul: 'Tylko płasko', opis: 'prawie bez podjazdów', patch: { maxNachylenie: 3 } },
  { id: 6, tytul: 'Łagodne podjazdy', opis: 'jak typowy podjazd dla wózka (ok. 6 cm w górę na każdy metr)', patch: { maxNachylenie: 6 } },
  { id: 8, tytul: 'Umiarkowane wzniesienia', opis: 'ok. 8 cm w górę na każdy metr', patch: { maxNachylenie: 8 } },
  { id: 12, tytul: 'Bez ograniczeń', opis: 'strome odcinki mi nie przeszkadzają', patch: { maxNachylenie: 12 } },
];

const LAWKI = [
  { id: 0, tytul: 'Nie potrzebuję ławek', opis: 'nie pokazuj braku ławek', patch: { lawkiAktywne: false } },
  { id: 150, tytul: 'Co ok. 2 minuty marszu', opis: 'ławka co ok. 150 m', patch: { lawkiAktywne: true, lawkaCoXm: 150 } },
  { id: 300, tytul: 'Co ok. 4 minuty marszu', opis: 'ławka co ok. 300 m', patch: { lawkiAktywne: true, lawkaCoXm: 300 } },
  { id: 500, tytul: 'Co ok. 6 minut marszu', opis: 'ławka co ok. 500 m', patch: { lawkiAktywne: true, lawkaCoXm: 500 } },
];

const SZEROKOSC = [
  { id: 0, tytul: 'Bez znaczenia', opis: 'nie sprawdzaj szerokości', patch: { szerokoscAktywna: false } },
  { id: 0.7, tytul: 'Co najmniej 0,7 m', opis: 'np. wózek dziecięcy', patch: { szerokoscAktywna: true, szerokoscPrzejscia: 0.7 } },
  { id: 0.9, tytul: 'Co najmniej 0,9 m', opis: 'np. wózek inwalidzki', patch: { szerokoscAktywna: true, szerokoscPrzejscia: 0.9 } },
  { id: 1.2, tytul: 'Co najmniej 1,2 m', opis: 'szerokie przejścia', patch: { szerokoscAktywna: true, szerokoscPrzejscia: 1.2 } },
];

function poziomNachylenia(v) {
  if (v <= 4) return 3;
  if (v <= 6) return 6;
  if (v <= 9) return 8;
  return 12;
}
function poziomLawek(p) {
  if (!p.lawkiAktywne) return 0;
  if (p.lawkaCoXm <= 225) return 150;
  if (p.lawkaCoXm <= 400) return 300;
  return 500;
}
function poziomSzerokosci(p) {
  if (!p.szerokoscAktywna) return 0;
  if (p.szerokoscPrzejscia <= 0.8) return 0.7;
  if (p.szerokoscPrzejscia <= 1.05) return 0.9;
  return 1.2;
}

function Wybor({ tytul, nazwa, opcje, wartosc, onWybierz }) {
  return (
    <fieldset className="choice-group">
      <legend>{tytul}</legend>
      <div className="choice-options">
        {opcje.map((o) => (
          <label key={o.id} className={`choice-option ${wartosc === o.id ? 'active' : ''}`}>
            <input
              type="radio"
              name={nazwa}
              checked={wartosc === o.id}
              onChange={() => onWybierz(o)}
            />
            <span>
              <strong>{o.tytul}</strong>
              <small>{o.opis}</small>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function ProfileSetup() {
  const navigate = useNavigate();

  // Stan formularza i preferencji
  const [imie, setImie] = useState('');
    const [wybranyProfil, setWybranyProfil] = useState(getInitialSetupProfile);
  // klucz grupy w API (np. "senior"); zostaje, gdy użytkownik ręcznie zmienia pojedyncze ustawienia
  const [grupa, setGrupa] = useState(readGroup);
  const [komunikat, setKomunikat] = useState('');
  const plikRef = useRef(null);

  // Poszczególne bariery i preferencje (checkboxy i suwaki)
  const [preferencje, setPreferencje] = useState(getInitialPreferences);

  // Obsługa kliknięcia w kafle profili – automatyczne zaznaczanie barier!
  const wybierzProfilKafel = (klucz) => {
    setWybranyProfil(klucz);
    setGrupa(homeProfileBySetupProfile[klucz]);
    // profil osoby niewidomej włącza czytanie wszystkiego na każdej stronie
    const niewidomy = klucz === 'wzrok';
    setAutoRead(niewidomy);
    setTimeout(() => speak(
      niewidomy
        ? `Wybrano: ${profileDanych[klucz].nazwa}. Od teraz czytam na głos wszystko na każdej stronie. Możesz to wyciszyć przyciskiem w prawym dolnym rogu.`
        : `Wybrano: ${profileDanych[klucz].nazwa}.`,
      { auto: true }
    ), 400);
    setPreferencje(prev => ({
      ...prev,
      ...profileDanych[klucz].ustawienia
    }));
    localStorage.setItem(
      'userAccessibilityProfile',
      JSON.stringify(homeProfileBySetupProfile[klucz])
    );
  };

  // Obsługa zmiany pojedynczych checkboxów
  const obsluzCheckbox = (e) => {
    const { name, checked } = e.target;
    setPreferencje(prev => ({ ...prev, [name]: checked }));
    setWybranyProfil('wlasne'); // Przełącz na profil "własne", gdy użytkownik coś zmodyfikuje ręcznie
    localStorage.removeItem('userAccessibilityProfile');
  };

  // Wybór z listy poziomów (nachylenie, ławki, szerokość)
  const ustaw = (patch) => {
    setPreferencje(prev => ({ ...prev, ...patch }));
    setWybranyProfil('wlasne');
    localStorage.removeItem('userAccessibilityProfile');
  };

  // Zapis i przejście dalej
  const zapiszIPrzejdz = () => {
    const daneUzytkownika = {
      imie,
      profil: wybranyProfil || 'ogolny',
      grupa,
      preferencje
    };
    // Zapisujemy opcjonalnie lokalnie w przeglądarce (na serwer nic nie trafia)
    saveUser(daneUzytkownika);

    // Przejście do mapy
    navigate('/mappage');
  };

  const pobierzProfil = async () => {
    try {
      setKomunikat('');
      // plik budujemy z aktualnych ustawień formularza
      saveUser({ imie, profil: wybranyProfil || 'ogolny', grupa, preferencje });
      const plik = await buildProfileFile({ name: imie || 'Mój profil', ui: loadUi() });
      const blob = new Blob([JSON.stringify(plik, null, 2)], { type: 'application/json' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'moj-profil.json';
      link.click();
      URL.revokeObjectURL(link.href);
      setKomunikat('Plik zapisany na Twoim urządzeniu. Serwer go nie przechowuje.');
    } catch (err) {
      setKomunikat(`Nie udało się przygotować pliku: ${err.message}`);
    }
  };

  const wczytajProfil = async (event) => {
    const plik = event.target.files?.[0];
    event.target.value = '';
    if (!plik) return;
    if (plik.size > 20000) {
      setKomunikat('Plik jest za duży (maksimum 20 kB).');
      return;
    }
    try {
      const tresc = JSON.parse(await plik.text());
      const wynik = await api.validateProfile(tresc);
      if (!wynik.ok) {
        setKomunikat(`Plik ma błędy: ${(wynik.errors || []).join('; ')}`);
        return;
      }
      const nowaGrupa = wynik.profile?.groups?.[0] || null;
      setGrupa(nowaGrupa);
      setWybranyProfil(nowaGrupa ? setupProfileByHomeProfile[nowaGrupa] : 'wlasne');
      setPreferencje(prev => preferencesFromValidated(wynik, prev));
      if (wynik.profile?.ui) saveUi({ ...loadUi(), ...wynik.profile.ui, mode: wynik.profile.ui.mode === 'standard' ? 'standard' : 'prosty' });
      const uwagi = (wynik.warnings || []).length ? ` Uwagi: ${wynik.warnings.join('; ')}` : '';
      setKomunikat(`Wczytano: ${wynik.etykieta}. Kliknij „Zapisz preferencje i otwórz mapę”, żeby zastosować.${uwagi}`);
    } catch (err) {
      setKomunikat(`Nie udało się wczytać pliku: ${err.message}`);
    }
  };

  return (
    <div className="profile-setup-container">
      <div className="profile-card">
        <h1>Skonfiguruj swoje preferencje</h1>
        <p className="subtitle">
          Wybierz gotowy profil, aby automatycznie dopasować bariery, lub dostosuj je ręcznie poniżej. Nic nie musisz wybierać: ustawienia są opcjonalne i zapisywane tylko na Twoim urządzeniu.
        </p>

        {/* Opcjonalna nazwa profilu (do nazwy pliku) */}
        <div className="section-block">
          <h3>1. Nazwa profilu (opcjonalnie)</h3>
          <div className="inputs-row">
            <input
              type="text"
              placeholder="Np. Mój profil"
              aria-label="Nazwa profilu"
              maxLength={60}
              value={imie}
              onChange={(e) => setImie(e.target.value)}
            />
          </div>
          <p className="subtitle form-note">Nie pytamy o imię ani o niepełnosprawność. Nazwa służy tylko do opisania pliku z ustawieniami.</p>
        </div>

        {/* Wybór 6 głównych profili */}
        <div className="section-block">
          <h3>2. Wybierz profil (automatyczna konfiguracja barier)</h3>
          <div className="tiles-grid">
            {Object.entries(profileDanych).map(([klucz, obj]) => (
              <div 
                key={klucz}
                className={`mini-tile ${wybranyProfil === klucz ? 'active' : ''}`}
                onClick={() => wybierzProfilKafel(klucz)}
              >
                <span className="tile-icon">
                  <img src={obj.ikona} alt="" />
                </span>
                <span className="tile-label">{obj.nazwa}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Szczegółowe preferencje barier (podatne na edycję) */}
        <div className="section-block">
          <h3>3. Czego chcesz unikać na trasie</h3>

          <div className="checkboxes-grid">
            <label className="check-label">
              <input type="checkbox" name="bezSchodow" checked={preferencje.bezSchodow} onChange={obsluzCheckbox} />
              <span>Bez schodów</span>
            </label>
            <label className="check-label">
              <input type="checkbox" name="niskieKrawedzniki" checked={preferencje.niskieKrawedzniki} onChange={obsluzCheckbox} />
              <span>Tylko obniżone lub równe krawężniki</span>
            </label>
            <label className="check-label">
              <input type="checkbox" name="gladszaNawierzchnia" checked={preferencje.gladszaNawierzchnia} onChange={obsluzCheckbox} />
              <span>Unikaj kostki brukowej i nierównej nawierzchni</span>
            </label>
            <label className="check-label">
              <input type="checkbox" name="prowadzenieDotykowe" checked={preferencje.prowadzenieDotykowe} onChange={obsluzCheckbox} />
              <span>Chcę ścieżek z prowadzeniem dotykowym (dla osób niewidomych)</span>
            </label>
            <label className="check-label">
              <input type="checkbox" name="sygnalDzwiekowy" checked={preferencje.sygnalDzwiekowy} onChange={obsluzCheckbox} />
              <span>Chcę sygnalizatorów z dźwiękiem na przejściach</span>
            </label>
            <label className="check-label">
              <input type="checkbox" name="oswietlenie" checked={preferencje.oswietlenie} onChange={obsluzCheckbox} />
              <span>Tylko oświetlone odcinki (np. wieczorem)</span>
            </label>
          </div>

          <Wybor
            tytul="Jak strome mogą być podejścia?"
            nazwa="nachylenie"
            opcje={NACHYLENIE}
            wartosc={poziomNachylenia(preferencje.maxNachylenie)}
            onWybierz={(o) => ustaw(o.patch)}
          />
          <Wybor
            tytul="Jak często chcesz mieć gdzie usiąść?"
            nazwa="lawki"
            opcje={LAWKI}
            wartosc={poziomLawek(preferencje)}
            onWybierz={(o) => ustaw(o.patch)}
          />
          <Wybor
            tytul="Jak szerokie muszą być przejścia?"
            nazwa="szerokosc"
            opcje={SZEROKOSC}
            wartosc={poziomSzerokosci(preferencje)}
            onWybierz={(o) => ustaw(o.patch)}
          />
        </div>

        <div className="section-block">
          <h3>4. Czego szukam w miejscach (budynkach, lokalach)</h3>
          <div className="checkboxes-grid">
            <label className="check-label">
              <input type="checkbox" name="toaleta" checked={preferencje.toaleta} onChange={obsluzCheckbox} />
              Dostępna toaleta
            </label>
            <label className="check-label">
              <input type="checkbox" name="winda" checked={preferencje.winda} onChange={obsluzCheckbox} />
              Winda
            </label>
            <label className="check-label">
              <input type="checkbox" name="przewijak" checked={preferencje.przewijak} onChange={obsluzCheckbox} />
              Przewijak
            </label>
            <label className="check-label">
              <input type="checkbox" name="petla" checked={preferencje.petla} onChange={obsluzCheckbox} />
              Pętla indukcyjna
            </label>
          </div>
        </div>

        <div className="section-block">
          <h3>5. Twój profil w pliku</h3>
          <p className="subtitle form-note">
            Ustawienia zostają na Twoim urządzeniu. Możesz je pobrać do pliku i wczytać ponownie.
            Serwer tylko sprawdza poprawność pliku, niczego nie zapisuje.
          </p>
          <div className="actions-row">
            <button type="button" className="btn-secondary" onClick={pobierzProfil}>Pobierz mój profil</button>
            <button type="button" className="btn-secondary" onClick={() => plikRef.current?.click()}>Wczytaj profil z pliku</button>
            <input ref={plikRef} type="file" accept="application/json" onChange={wczytajProfil} style={{ display: 'none' }} aria-label="Wybierz plik profilu" />
          </div>
          <p role="status" aria-live="polite" className="subtitle">{komunikat}</p>
        </div>

        {/* Przyciski akcji */}
        <div className="actions-row">
          <button className="btn-secondary" onClick={() => navigate('/mappage')}>
            Pomiń i przejdź do mapy
          </button>
          <button className="btn-primary" onClick={zapiszIPrzejdz}>
            Zapisz preferencje i otwórz mapę
          </button>
        </div>

      </div>
    </div>
  );
}