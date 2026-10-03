import React, { useState } from "react";

const API_BASE =
  "https://cuddly-space-journey-g49vpw47wqwhw7rp-8000.app.github.dev";

export default function RouteForm({ onRoute }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const geocode = async (address) => {
    const response = await fetch(
      `${API_BASE}/api/geocode?q=${encodeURIComponent(address)}&limit=1`
    );

    if (!response.ok) {
      throw new Error("Nie udało się znaleźć adresu.");
    }

    const data = await response.json();

    if (!data.results || data.results.length === 0) {
      throw new Error(`Nie znaleziono adresu: ${address}`);
    }

    return data.results[0];
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!from.trim() || !to.trim()) {
      setError("Podaj adres początkowy i końcowy.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      // 1. Znajdź adres początkowy
      const fromResult = await geocode(from);

      // 2. Znajdź adres końcowy
      const toResult = await geocode(to);

      // 3. Pobierz zapisany profil użytkownika
      const savedProfile = localStorage.getItem(
        "userAccessibilityProfile"
      );

      const profile = savedProfile
        ? JSON.parse(savedProfile)
        : "wozek_inwalidzki";

      // 4. Wywołanie API trasy
      const routeUrl = new URL(`${API_BASE}/api/route`);

      routeUrl.searchParams.set("from_lon", fromResult.lon);
      routeUrl.searchParams.set("from_lat", fromResult.lat);
      routeUrl.searchParams.set("to_lon", toResult.lon);
      routeUrl.searchParams.set("to_lat", toResult.lat);
      routeUrl.searchParams.set("profiles", profile);
      routeUrl.searchParams.set("mode", "warn");

      const routeResponse = await fetch(routeUrl);

      if (!routeResponse.ok) {
        throw new Error("Nie udało się wyznaczyć trasy.");
      }

      const route = await routeResponse.json();

      // 5. Przekazujemy GeoJSON do MapPage
      onRoute(route);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="route-form">
      <div className="route-input">
        <label htmlFor="from">Od</label>

        <input
          id="from"
          type="text"
          placeholder="np. Pawia 4, Kraków"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
      </div>

      <div className="route-input">
        <label htmlFor="to">Do</label>

        <input
          id="to"
          type="text"
          placeholder="np. Rynek Główny 1, Kraków"
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
      </div>

      <button type="submit" disabled={loading}>
        {loading ? "Wyznaczanie trasy..." : "Wyznacz trasę"}
      </button>

      {error && <p className="route-error">{error}</p>}
    </form>
  );
}