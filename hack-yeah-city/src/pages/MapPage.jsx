import React, { useState } from "react";
import Map from "../components/Map"; // Jeśli plik Map.jsx jest w innym folderze, dostosuj ścieżkę

export default function MapPage() {
  const [points, setPoints] = useState({ pointA: null, pointB: null });
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");

  const handlePlanRoute = async () => {
    if (!points.pointA || !points.pointB) return;

    setLoading(true);
    setStatusMessage("");

    // Podgląd danych w konsoli deweloperskiej (F12)
    console.log("Punkty gotowe do wysłania do API:", {
      start: points.pointA,
      end: points.pointB,
    });

    // --- SYMULACJA API (na czas tworzenia backendu) ---
    setTimeout(() => {
      setLoading(false);
      setStatusMessage("Punkty zostały zapisane! Otwórz konsolę (F12), aby zobaczyć obiekt.");
    }, 800);

    /*
    Gdy backend będzie gotowy, podmień powyższy setTimeout na:

    try {
      const res = await fetch("http://localhost:5000/api/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start: points.pointA,
          end: points.pointB,
        }),
      });
      const data = await res.json();
      console.log("Odpowiedź API:", data);
    } catch (err) {
      console.error("Błąd połączenia z API:", err);
    } finally {
      setLoading(false);
    }
    */
  };

  const isReady = points.pointA && points.pointB;

  return (
    <div style={{ padding: "16px" }}>
      {/* Pasek akcji i podpowiedzi */}
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
          {!points.pointA && "Kliknij na mapie punkt początkowy (A)."}
          {points.pointA && !points.pointB && "Kliknij na mapie punkt docelowy (B)."}
          {isReady && !loading && !statusMessage && "Oba punkty wybrane. Kliknij „Planuj trasę”."}
          {statusMessage && statusMessage}
        </span>
      </div>

      {/* Kontener mapy - musi mieć zdefiniowaną wysokość */}
      <div style={{ width: "100%", height: "600px" }}>
        <Map onPointsChange={setPoints} />
      </div>
    </div>
  );
}