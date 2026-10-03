import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import MapPage from "./pages/MapPage";
import Home from "./pages/Home";
import ProfileSetup from "./components/ProfileSetup";

function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("siteTheme") || "light");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("siteTheme", theme);
  }, [theme]);

  return (
    <BrowserRouter>
      <Navbar
        theme={theme}
        onToggleTheme={() => setTheme((current) => current === "light" ? "dark" : "light")}
      />

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/mappage" element={<MapPage theme={theme} />} />
        <Route path="/profil" element={<ProfileSetup />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
