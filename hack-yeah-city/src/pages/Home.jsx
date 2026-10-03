import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Tile from "../components/Tile";
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

    localStorage.setItem(
      "userAccessibilityProfile",
      JSON.stringify(profileId)
    );
  };

  const handleGoToMap = () => {
    if (!selectedProfile) {
      alert("Najpierw wybierz profil użytkownika.");
      return;
    }

    navigate("/mappage");
  };

  return (
    <main className="home">
      <div className="home-content">
        <section className="hero-section">
          <p className="eyebrow">Kraków Bez Barier</p>
          <h1>Wybierz swój profil, a my wyznaczymy najbezpieczniejszą trasę.</h1>
          <p className="hero-description">
            Kraków Bez Barier. Wybierz swój profil, a my wyznaczymy najbezpieczniejszą
            trasę omijającą schody, strome podjazdy i wysokie krawężniki.
          </p>
        </section>

        <p className="subtitle">Wybierz profil, aby dopasować trasę do Twoich potrzeb.</p>

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
            disabled={!selectedProfile}
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
              <p>Ruszaj w drogę po bezpiecznej trasie z pominięciem barier.</p>
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