import React, { useState } from "react";
import Map from "../components/Map";

export default function MapPage() {
  const [points, setPoints] = useState({ pointA: null, pointB: null });
  const [routeData, setRouteData] = useState(null); // Tutaj zapisujemy trasę z API
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [theme, setTheme] = useState("light");

  const isDarkMode = theme === "dark";

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
    <div
      style={{
        padding: "24px 20px 32px",
        background: isDarkMode ? "#020817" : "#edf2f7",
        minHeight: "100vh",
        color: isDarkMode ? "#e2e8f0" : "#1f2937",
        transition: "all 0.2s ease",
      }}
    >
      <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            marginBottom: "16px",
            padding: "14px 18px",
            background: isDarkMode ? "rgba(15, 23, 42, 0.9)" : "rgba(255,255,255,0.9)",
            border: "1px solid rgba(148, 163, 184, 0.2)",
            borderRadius: "18px",
            boxShadow: isDarkMode ? "0 8px 24px rgba(2, 6, 23, 0.6)" : "0 8px 24px rgba(15, 23, 42, 0.08)",
            backdropFilter: "blur(8px)",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
            <button
              onClick={handlePlanRoute}
              disabled={!isReady || loading}
              style={{
                padding: "12px 18px",
                fontSize: "14px",
                fontWeight: 700,
                border: "none",
                borderRadius: "999px",
                background: isReady && !loading ? "linear-gradient(135deg, #2563eb, #1d4ed8)" : isDarkMode ? "#1e293b" : "#e5e7eb",
                color: isReady && !loading ? "#fff" : isDarkMode ? "#94a3b8" : "#6b7280",
                boxShadow: isReady && !loading ? "0 10px 20px rgba(37, 99, 235, 0.25)" : "none",
                cursor: isReady && !loading ? "pointer" : "not-allowed",
                transition: "all 0.2s ease",
              }}
            >
              {loading ? "Planowanie..." : "Planuj trasę"}
            </button>

            <button
              onClick={() => setTheme((prev) => (prev === "light" ? "dark" : "light"))}
              style={{
                padding: "10px 14px",
                borderRadius: "999px",
                border: isDarkMode ? "1px solid rgba(148, 163, 184, 0.35)" : "1px solid rgba(148, 163, 184, 0.2)",
                background: isDarkMode ? "#111827" : "#f8fafc",
                color: isDarkMode ? "#f8fafc" : "#111827",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              {isDarkMode ? "☀️ Light" : "🌙 Dark"}
            </button>
          </div>

          <span
            style={{
              fontSize: "14px",
              color: isDarkMode ? "#cbd5e1" : "#374151",
              fontWeight: 500,
              background: isDarkMode ? "rgba(15, 23, 42, 0.9)" : "#f8fafc",
              border: isDarkMode ? "1px solid rgba(148, 163, 184, 0.25)" : "1px solid #e2e8f0",
              borderRadius: "999px",
              padding: "8px 12px",
            }}
          >
            {!points.pointA && "Kliknij punkt startowy na mapie."}
            {points.pointA && !points.pointB && "Kliknij punkt docelowy na mapie."}
            {isReady && !loading && !statusMessage && "Oba punkty wybrane! Kliknij „Planuj trasę”."}
            {statusMessage && statusMessage}
          </span>
        </div>

        <div
          style={{
            width: "100%",
            height: "600px",
            borderRadius: "24px",
            overflow: "hidden",
            boxShadow: isDarkMode ? "0 16px 36px rgba(2, 6, 23, 0.6)" : "0 16px 36px rgba(15, 23, 42, 0.12)",
            border: "1px solid rgba(148, 163, 184, 0.25)",
            background: isDarkMode ? "#020817" : "#dfeaf5",
          }}
        >
          <Map onPointsChange={setPoints} routeData={routeData} theme={theme} />
        </div>

        <div
          style={{
            display: "flex",
            gap: "12px",
            marginTop: "16px",
            flexWrap: "wrap",
          }}
        >
          <div
            style={{
              flex: "1 1 220px",
              background: isDarkMode ? "rgba(15, 23, 42, 0.9)" : "rgba(255,255,255,0.9)",
              border: "1px solid rgba(148, 163, 184, 0.25)",
              borderRadius: "16px",
              padding: "12px 16px",
              boxShadow: isDarkMode ? "0 8px 24px rgba(2, 6, 23, 0.46)" : "0 8px 24px rgba(15, 23, 42, 0.05)",
            }}
          >
            {points.pointA ? (
              <div>
                <div style={{ fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase", color: isDarkMode ? "#94a3b8" : "#64748b", marginBottom: "4px" }}>
                  Punkt A
                </div>
                <div style={{ fontSize: "15px", fontWeight: 700, color: isDarkMode ? "#f8fafc" : "#111827" }}>
                  {points.pointA.lng.toFixed(5)}, {points.pointA.lat.toFixed(5)}
                </div>
              </div>
            ) : (
              <div style={{ color: isDarkMode ? "#94a3b8" : "#64748b" }}>Punkt A: nie wybrano</div>
            )}
          </div>

          <div
            style={{
              flex: "1 1 220px",
              background: isDarkMode ? "rgba(15, 23, 42, 0.9)" : "rgba(255,255,255,0.9)",
              border: "1px solid rgba(148, 163, 184, 0.25)",
              borderRadius: "16px",
              padding: "12px 16px",
              boxShadow: isDarkMode ? "0 8px 24px rgba(2, 6, 23, 0.46)" : "0 8px 24px rgba(15, 23, 42, 0.05)",
            }}
          >
            {points.pointB ? (
              <div>
                <div style={{ fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase", color: isDarkMode ? "#94a3b8" : "#64748b", marginBottom: "4px" }}>
                  Punkt B
                </div>
                <div style={{ fontSize: "15px", fontWeight: 700, color: isDarkMode ? "#f8fafc" : "#111827" }}>
                  {points.pointB.lng.toFixed(5)}, {points.pointB.lat.toFixed(5)}
                </div>
              </div>
            ) : (
              <div style={{ color: isDarkMode ? "#94a3b8" : "#64748b" }}>Punkt B: nie wybrano</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}