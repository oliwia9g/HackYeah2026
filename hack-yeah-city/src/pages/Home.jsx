import React, { useEffect, useState } from "react";
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

  return (
    <main className="home">
      <div className="home-content">
        <h1>Jak możemy Ci pomóc?</h1>

        <p className="subtitle">
          Wybierz profil, aby dopasować trasę do Twoich potrzeb.
        </p>

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
      </div>
    </main>
  );
}