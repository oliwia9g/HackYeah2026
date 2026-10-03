import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Tile from "../components/Tile";
import "../Home.css";

const profiles = [
  {
    id: "wozek_inwalidzki",
    title: "Wózek inwalidzki",
    icon: "♿",
  },
  {
    id: "wozek_dziecko",
    title: "Wózek dziecięcy",
    icon: "👶",
  },
  {
    id: "niewidomy_slabowidzacy",
    title: "Niewidomy / słabowidzący",
    icon: "👁️",
  },
  {
    id: "gluchy_niedoslyszacy",
    title: "Głuchy / niedosłyszący",
    icon: "🦻",
  },
  {
    id: "senior",
    title: "Senior",
    icon: "🧓",
  },
  {
    id: "ciaza",
    title: "Ciąża",
    icon: "🤰",
  },
];

export default function Home() {
  const [selectedProfile, setSelectedProfile] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const saved = localStorage.getItem("userAccessibilityProfile");

    if (saved) {
      setSelectedProfile(JSON.parse(saved));
    }
  }, []);

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
            className="primary-button"
            onClick={handleGoToMap}
            disabled={!selectedProfile}
          >
            {selectedProfile ? "Przejdź do mapy" : "Wybierz profil, aby kontynuować"}
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