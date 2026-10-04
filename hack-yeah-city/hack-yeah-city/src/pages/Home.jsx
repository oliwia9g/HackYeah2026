import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Tile from "../components/Tile";
import { saveGroupOnly } from "../prefs";
import { setAutoRead, speak } from "../speech";
import "../Home.css";

const profiles = [
  {
    id: "wozek_inwalidzki",
    title: "Osoba poruszająca się na wózku",
    icon: "/disabled.png",
  },
  {
    id: "wozek_dziecko",
    title: "Osoba z wózkiem dziecięcym",
    icon: "/little-kid.png",
  },
  {
    id: "niewidomy_slabowidzacy",
    title: "Osoba niewidoma lub słabowidząca",
    icon: "/eye.png",
  },
  {
    id: "gluchy_niedoslyszacy",
    title: "Osoba głucha lub niedosłysząca",
    icon: "/ear.png",
  },
  {
    id: "senior",
    title: "Osoba starsza",
    icon: "/old-man.png",
  },
  {
    id: "ciaza",
    title: "Kobieta w ciąży",
    icon: "/pregnant.png",
  },
];

export default function Home() {
  const [selectedProfile, setSelectedProfile] = useState(() => {
    const saved = localStorage.getItem("userAccessibilityProfile");
    if (!saved) return null;

    try {
      return JSON.parse(saved);
    } catch {
      return saved;
    }
  });
  const navigate = useNavigate();

  const handleSelect = (profileId) => {
    setSelectedProfile(profileId);

    // zapamiętujemy grupę na urządzeniu; szczegółowe ustawienia wracają do domyślnych tej grupy
    saveGroupOnly(profileId);

    // wybór profilu osoby niewidomej włącza czytanie wszystkiego na każdej stronie (można wyciszyć przyciskiem w rogu)
    const blind = profileId === "niewidomy_slabowidzacy";
    setAutoRead(blind);
    const title = profiles.find((p) => p.id === profileId)?.title || "";
    // lekkie opóźnienie, żeby czytnik elementów (fokus na kafelku) nie przerwał potwierdzenia
    setTimeout(
      () =>
        speak(
          blind
            ? `Wybrano: ${title}. Od teraz czytam na głos wszystko na każdej stronie. Możesz to wyciszyć przyciskiem w prawym dolnym rogu.`
            : `Wybrano: ${title}.`,
          { auto: true }
        ),
      400
    );
  };

  const handleGoToMap = () => {
    // wybór profilu jest tylko skrótem; do mapy można przejść bez niego
    navigate("/mappage");
  };

  return (
    <main className="home">
      <div className="home-content">
        <section className="hero-section">
          <p className="eyebrow">Kraków Bez Barier</p>
          <h1>Wybierz, czego potrzebujesz na trasie, a pokażemy warianty z przeszkodami i brakami danych.</h1>
          <p className="hero-description">
            Kraków Bez Barier. Wybierz gotowy zestaw wymagań, a my zaproponujemy trasy omijające
            schody, strome podjazdy i wysokie krawężniki tam, gdzie mamy o nich dane, i uczciwie
            powiemy, gdzie danych brakuje.
          </p>
        </section>

        <p className="subtitle">Wybierz profil, aby dopasować trasę do Twoich potrzeb. Nie musisz niczego wybierać: profil to tylko gotowy zestaw ustawień, który zmienisz w dowolnej chwili.</p>

        <div className="tiles">
          {profiles.map((profile) => (
            <Tile
              key={profile.id}
              icon={profile.icon}
              title={profile.title}
              selected={selectedProfile === profile.id}
              onClick={() => handleSelect(profile.id)}
            />
          ))}
        </div>

        <div className="action-section">
          <button
            type="button"
            className="secondary-button"
            onClick={() => navigate("/profil")}
          >
            Dostosuj profil i bariery
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={handleGoToMap}
          >
            Przejdź do planowania trasy
          </button>
        </div>

        <section className="how-it-works">
          <h3>Jak to działa?</h3>
          <div className="steps">
            <div className="step">
              <span>1</span>
              <p>Wybierz profil i dopasuj algorytm do swoich potrzeb.</p>
            </div>
            <div className="step">
              <span>2</span>
              <p>Wskaż punkt startowy i cel na mapie lub w adresie.</p>
            </div>
            <div className="step">
              <span>3</span>
              <p>Porównaj warianty trasy, zobacz przeszkody i miejsca, o których brakuje danych.</p>
            </div>
          </div>
        </section>

        <section className="mission-section">
          <h3>Nasza misja</h3>
          <p>
            Projekt powstał, aby ułatwić codzienną mobilność w mieście dzięki danym z
            OpenStreetMap i miejskim źródłom infrastrukturalnym. Chcemy wspierać osoby z
            różnymi potrzebami, aby każda trasa była nie tylko szybka, ale też bezpieczna i
            dostępna.
          </p>
        </section>
      </div>
    </main>
  );
}