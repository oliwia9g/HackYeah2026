import React, { useState } from "react";
import Map from "../components/Map";

export default function MapPage() {
  const [points, setPoints] = useState({ pointA: null, pointB: null });
  const [routeData, setRouteData] = useState(null); // Tutaj zapisujemy trasę z API
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");

  const handlePlanRoute = async () => {
    if (!points.pointA || !points.pointB) return;

    // 1. Odczytanie profilu z localStorage
    let profile = "wozek_inwalidzki";
    const savedProfile = localStorage.getItem("userAccessibilityProfile");
    if (savedProfile) {
      try {
        profile = JSON.parse(savedProfile);
      } catch (err) {
        profile = savedProfile;
      }
    }

    // 2. Zapytanie do backendu
    const params = new URLSearchParams({
      from_lon: points.pointA.lng,
      from_lat: points.pointA.lat,
      to_lon: points.pointB.lng,
      to_lat: points.pointB.lat,
      profiles: profile,
      mode: "warn",
    });

    const apiUrl = `https://cuddly-space-journey-g49vpw47wqwhw7rp-8000.app.github.dev/api/route?${params.toString()}`;

    setLoading(true);
    setStatusMessage("Wyznaczanie trasy...");

    try {
      const response = await fetch(apiUrl);
      if (!response.ok) {
        throw new Error(`Błąd HTTP: ${response.status}`);
      }

      const data = await response.json();
      console.log("Odpowiedź API:", data);

      // 3. Wyciągnięcie geometrii z odpowiedzi API
      const routeGeometry =
        data.route?.geometry ||
        data.route ||
        data.routes?.[0]?.geometry ||
        data.routes?.[0] ||
        data.geometry ||
        data.geojson ||
        data.features?.[0]?.geometry ||
        data;

      setRouteData(routeGeometry);
      setStatusMessage("Trasa wyznaczona!");
    } catch (error) {
      console.error("Błąd trasy:", error);
      setStatusMessage(`Wystąpił błąd: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const isReady = points.pointA && points.pointB;

  return (
    <div style={{ padding: "16px" }}>
      <div style={{ marginBottom: "12px", display: "flex", alignItems: "center", gap: "12px" }}>
        <button
          onClick={handlePlanRoute}
          disabled={!isReady || loading}
          style={{
            padding: "8px 16px",
            fontSize: "14px",
            cursor: isReady && !loading ? "pointer" : "not-allowed",
            opacity: isReady && !loading ? 1 : 0.6,
          }}
        >
          {loading ? "Planowanie..." : "Planuj trasę"}
        </button>

        <span style={{ fontSize: "14px" }}>
          {!points.pointA && "Kliknij punkt startowy na mapie."}
          {points.pointA && !points.pointB && "Kliknij punkt docelowy na mapie."}
          {isReady && !loading && !statusMessage && "Oba punkty wybrane! Kliknij „Planuj trasę”."}
          {statusMessage && statusMessage}
        </span>
      </div>

      <div style={{ width: "100%", height: "600px" }}>
        <Map onPointsChange={setPoints} routeData={routeData} />
      </div>
    </div>
  );
}