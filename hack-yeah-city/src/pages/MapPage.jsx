import { useState } from "react";
import Map from "../components/Map";
import RouteForm from "../components/RouteForm";

export default function MapPage({ theme }) {
  const [points, setPoints] = useState({ pointA: null, pointB: null });
  const [routeData, setRouteData] = useState(null); // Tutaj zapisujemy trasę z API
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [addresses, setAddresses] = useState({ from: "", to: "" });
  const [clearSelectionVersion, setClearSelectionVersion] = useState(0);

  const isDarkMode = theme === "dark";
  const hasAddressInput = Boolean(addresses.from.trim() || addresses.to.trim());

  const handlePlanRoute = async () => {
    const useAddresses = hasAddressInput;
    if (useAddresses && (!addresses.from.trim() || !addresses.to.trim())) {
      setStatusMessage("Podaj adres początkowy i końcowy.");
      return;
    }
    if (!useAddresses && (!points.pointA || !points.pointB)) return;

    let profile = "wozek_inwalidzki";
    const savedProfile = localStorage.getItem("userAccessibilityProfile");
    if (savedProfile) {
      try {
        profile = JSON.parse(savedProfile);
      } catch {
        profile = savedProfile;
      }
    }

    setLoading(true);
    setStatusMessage("Wyznaczanie trasy...");

    try {
      const apiBase = "https://cuddly-space-journey-g49vpw47wqwhw7rp-8000.app.github.dev";
      let origin;
      let destination;

      if (useAddresses) {
        const geocode = async (address) => {
          const response = await fetch(
            `${apiBase}/api/geocode?q=${encodeURIComponent(address)}&limit=1`
          );
          if (!response.ok) {
            throw new Error(`Nie udało się znaleźć adresu: ${address}`);
          }
          const data = await response.json();
          if (!data.results?.length) {
            throw new Error(`Nie znaleziono adresu: ${address}`);
          }
          return data.results[0];
        };

        [origin, destination] = await Promise.all([
          geocode(addresses.from.trim()),
          geocode(addresses.to.trim()),
        ]);
      } else {
        origin = points.pointA;
        destination = points.pointB;
      }

      const params = new URLSearchParams({
        from_lon: origin.lon ?? origin.lng,
        from_lat: origin.lat,
        to_lon: destination.lon ?? destination.lng,
        to_lat: destination.lat,
        profiles: profile,
        mode: "warn",
      });
      const response = await fetch(`${apiBase}/api/route?${params.toString()}`);
      if (!response.ok) {
        throw new Error("Nie udało się wyznaczyć trasy.");
      }

      const data = await response.json();
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

  const isReady = hasAddressInput
    ? Boolean(addresses.from.trim() && addresses.to.trim())
    : Boolean(points.pointA && points.pointB);

  const handleAddressesChange = (nextAddresses) => {
    setAddresses(nextAddresses);
    setPoints({ pointA: null, pointB: null });
    setRouteData(null);
    setStatusMessage("");
    setClearSelectionVersion((version) => version + 1);
  };

  const handlePointsChange = (nextPoints) => {
    setPoints(nextPoints);
    setAddresses({ from: "", to: "" });
    setRouteData(null);
    setStatusMessage("");
  };

  return (
    <div
      style={{
        padding: "24px 20px 32px",
        background: isDarkMode ? "#211e2d" : "#f0edf7",
        minHeight: "100vh",
        color: isDarkMode ? "#ffffff" : "#000000",
        transition: "all 0.2s ease",
      }}
    >
      <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-start",
            gap: "12px",
            marginBottom: "16px",
            padding: "14px 18px",
            background: isDarkMode ? "#302b40" : "rgba(255,255,255,0.96)",
            border: isDarkMode ? "1px solid rgba(244, 204, 92, 0.35)" : "1px solid #d8d3e5",
            borderRadius: "18px",
            boxShadow: isDarkMode ? "0 8px 24px rgba(0, 0, 0, 0.35)" : "0 8px 24px rgba(122, 108, 177, 0.12)",
            backdropFilter: "blur(8px)",
            flexWrap: "wrap",
          }}
        >
          <RouteForm
            addresses={addresses}
            onAddressesChange={handleAddressesChange}
            isDarkMode={isDarkMode}
          />

          <button
            onClick={handlePlanRoute}
            disabled={!isReady || loading}
            style={{
              flex: "0 0 auto",
              padding: "12px 18px",
              fontSize: "14px",
              fontWeight: 700,
              border: "none",
              borderRadius: "999px",
              background: isReady && !loading ? "linear-gradient(110deg, #f4cc5c, #e15a4f)" : isDarkMode ? "#4a435d" : "#e6f6f8",
              color: "#000000",
              boxShadow: isReady && !loading ? "0 10px 20px rgba(225, 90, 79, 0.25)" : "none",
              cursor: isReady && !loading ? "pointer" : "not-allowed",
              transition: "all 0.2s ease",
            }}
          >
            {loading ? "Wyznaczanie trasy..." : "Wyznacz trasę"}
          </button>

          <span
            style={{
              marginLeft: "auto",
              fontSize: "14px",
              color: isDarkMode ? "#ffffff" : "#000000",
              fontWeight: 500,
              background: isDarkMode ? "#302b40" : "#e6f6f8",
              border: isDarkMode ? "1px solid rgba(88, 182, 198, 0.5)" : "1px solid #58b6c6",
              borderRadius: "999px",
              padding: "8px 12px",
            }}
          >
            {hasAddressInput && (!addresses.from.trim() || !addresses.to.trim()) &&
              "Podaj adres początkowy i końcowy."}
            {!hasAddressInput && !points.pointA && "Kliknij punkt startowy na mapie."}
            {!hasAddressInput && points.pointA && !points.pointB && "Kliknij punkt docelowy na mapie."}
            {isReady && !loading && !statusMessage && "Ustaw trasę i kliknij „Wyznacz trasę”."}
            {statusMessage && statusMessage}
          </span>
        </div>

        <div
          style={{
            width: "100%",
            height: "600px",
            borderRadius: "24px",
            overflow: "hidden",
            boxShadow: isDarkMode ? "0 16px 36px rgba(0, 0, 0, 0.4)" : "0 16px 36px rgba(122, 108, 177, 0.2)",
            border: "2px solid #7a6cb1",
            background: isDarkMode ? "#211e2d" : "#e6f6f8",
          }}
        >
          <Map
            onPointsChange={handlePointsChange}
            routeData={routeData}
            theme={theme}
            clearSelectionVersion={clearSelectionVersion}
          />
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
              background: isDarkMode ? "#302b40" : "#ffffff",
              border: isDarkMode ? "1px solid rgba(244, 204, 92, 0.35)" : "1px solid #d8d3e5",
              borderRadius: "16px",
              padding: "12px 16px",
              boxShadow: isDarkMode ? "0 8px 24px rgba(0, 0, 0, 0.3)" : "0 8px 24px rgba(122, 108, 177, 0.08)",
            }}
          >
            {points.pointA ? (
              <div>
                <div style={{ fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase", color: isDarkMode ? "#58b6c6" : "#7a6cb1", marginBottom: "4px" }}>
                  Punkt A
                </div>
                <div style={{ fontSize: "15px", fontWeight: 700, color: isDarkMode ? "#ffffff" : "#000000" }}>
                  {points.pointA.lng.toFixed(5)}, {points.pointA.lat.toFixed(5)}
                </div>
              </div>
            ) : (
              <div style={{ color: isDarkMode ? "#ffffff" : "#4e4a56" }}>Punkt początkowy: nie wybrano</div>
            )}
          </div>

          <div
            style={{
              flex: "1 1 220px",
              background: isDarkMode ? "#302b40" : "#ffffff",
              border: isDarkMode ? "1px solid rgba(244, 204, 92, 0.35)" : "1px solid #d8d3e5",
              borderRadius: "16px",
              padding: "12px 16px",
              boxShadow: isDarkMode ? "0 8px 24px rgba(0, 0, 0, 0.3)" : "0 8px 24px rgba(122, 108, 177, 0.08)",
            }}
          >
            {points.pointB ? (
              <div>
                <div style={{ fontSize: "11px", letterSpacing: "0.08em", textTransform: "uppercase", color: isDarkMode ? "#58b6c6" : "#7a6cb1", marginBottom: "4px" }}>
                  Punkt B
                </div>
                <div style={{ fontSize: "15px", fontWeight: 700, color: isDarkMode ? "#ffffff" : "#000000" }}>
                  {points.pointB.lng.toFixed(5)}, {points.pointB.lat.toFixed(5)}
                </div>
              </div>
            ) : (
              <div style={{ color: isDarkMode ? "#ffffff" : "#4e4a56" }}>Punkt końcowy: nie wybrano</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}