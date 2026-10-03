import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import '../ProfileSetup.css';

const profileDanych = {
  wozek: {
    nazwa: 'Wózek inwalidzki',
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
    }
  },
  wozek_dzieciecy: {
    nazwa: 'Wózek dziecięcy',
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
    }
  },
  wzrok: {
    nazwa: 'Słabowidzący / Niewidomy',
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
    }
  },
  sluch: {
    nazwa: 'Niedosłyszący',
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
    }
  },
  senior: {
    nazwa: 'Senior',
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
    }
  },
  ciaza: {
    nazwa: 'Kobieta w ciąży',
    ikona: '/pregnant.png',
    ustawienia: {
      bezSchodow: false,
      maxNachylenie: 10,
      szerokoscPrzejscia: 0.8,
      niskieKrawedzniki: false,
      gladszaNawierzchnia: true,
      prowadzenieDotykowe: false,
      sygnalDzwiekowy: false,
      oswietlenie: false,
      lawkaCoXm: 400,
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

export default function ProfileSetup() {
  const navigate = useNavigate();

  // Stan formularza i preferencji
  const [imie, setImie] = useState('');
  const [nazwisko, setNazwisko] = useState('');
  const [wybranyProfil, setWybranyProfil] = useState(getInitialSetupProfile);

  // Poszczególne bariery i preferencje (checkboxy i suwaki)
  const [preferencje, setPreferencje] = useState(getInitialPreferences);

  // Obsługa kliknięcia w kafle profili – automatyczne zaznaczanie barier!
  const wybierzProfilKafel = (klucz) => {
    setWybranyProfil(klucz);
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

  // Obsługa suwaków
  const obsluzSuwak = (e) => {
    const { name, value } = e.target;
    setPreferencje(prev => ({ ...prev, [name]: Number(value) }));
    setWybranyProfil('wlasne');
    localStorage.removeItem('userAccessibilityProfile');
  };

  // Zapis i przejście dalej
  const zapiszIPrzejdz = () => {
    const daneUzytkownika = {
      imie,
      nazwisko,
      profil: wybranyProfil || 'ogolny',
      preferencje
    };
    // Zapisujemy opcjonalnie lokalnie w przeglądarce
    localStorage.setItem('ponadBarieramiUser', JSON.stringify(daneUzytkownika));
    
    // Przejście do mapy
    navigate('/mappage');
  };

  return (
    <div className="profile-setup-container">
      <div className="profile-card">
        <h1>Skonfiguruj swoje preferencje</h1>
        <p className="subtitle">
          Wybierz gotowy profil, aby automatycznie dopasować bariery, lub dostosuj je ręcznie poniżej. Konto i dane są opcjonalne i zapisywane tylko na Twoim urządzeniu.
        </p>

        {/* Opcjonalne dane osobowe */}
        <div className="section-block">
          <h3>1. Dane użytkownika (opcjonalnie)</h3>
          <div className="inputs-row">
            <input 
              type="text" 
              placeholder="Imię" 
              value={imie} 
              onChange={(e) => setImie(e.target.value)} 
            />
            <input 
              type="text" 
              placeholder="Nazwisko" 
              value={nazwisko} 
              onChange={(e) => setNazwisko(e.target.value)} 
            />
          </div>
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
          <h3>3. Szczegółowe parametry trasy i bariery</h3>
          
          <div className="checkboxes-grid">
            <label className="check-label">
              <input 
                type="checkbox" 
                name="bezSchodow" 
                checked={preferencje.bezSchodow} 
                onChange={obsluzCheckbox} 
              />
              Całkowity brak schodów (wykluczenie)
            </label>

            <label className="check-label">
              <input 
                type="checkbox" 
                name="niskieKrawedzniki" 
                checked={preferencje.niskieKrawedzniki} 
                onChange={obsluzCheckbox} 
              />
              Wymagane obniżone / zrównane krawężniki
            </label>

            <label className="check-label">
              <input 
                type="checkbox" 
                name="gladszaNawierzchnia" 
                checked={preferencje.gladszaNawierzchnia} 
                onChange={obsluzCheckbox} 
              / >
              Unikanie nierównej nawierzchni / kostki
            </label>

            <label className="check-label">
              <input 
                type="checkbox" 
                name="prowadzenieDotykowe" 
                checked={preferencje.prowadzenieDotykowe} 
                onChange={obsluzCheckbox} 
              />
              Wymagane prowadzenie dotykowe (dla niewidomych)
            </label>

            <label className="check-label">
              <input 
                type="checkbox" 
                name="sygnalDzwiekowy" 
                checked={preferencje.sygnalDzwiekowy} 
                onChange={obsluzCheckbox} 
              />
              Sygnalizatory z dźwiękiem na przejściach
            </label>

            <label className="check-label">
              <input 
                type="checkbox" 
                name="oswietlenie" 
                checked={preferencje.oswietlenie} 
                onChange={obsluzCheckbox} 
              />
              Tylko oświetlone odcinki trasy
            </label>
          </div>

          {/* Suwaki zaawansowane */}
          <div className="sliders-section">
            <div className="slider-group">
              <label>Maksymalne nachylenie terenu: <strong>{preferencje.maxNachylenie}%</strong></label>
              <input 
                type="range" 
                name="maxNachylenie" 
                min="4" 
                max="15" 
                step="1"
                value={preferencje.maxNachylenie} 
                onChange={obsluzSuwak} 
              />
            </div>

            <div className="slider-group">
              <label>Maksymalny dystans bez ławki: <strong>{preferencje.lawkaCoXm} m</strong></label>
              <input 
                type="range" 
                name="lawkaCoXm" 
                min="100" 
                max="1000" 
                step="50"
                value={preferencje.lawkaCoXm} 
                onChange={obsluzSuwak} 
              />
            </div>
          </div>
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