import React, { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

export default function Map({
  initialLng = 21.0122,
  initialLat = 52.2297,
  initialZoom = 12,
  onPointsChange,
}) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const stateRef = useRef({ pointA: null, pointB: null, markerA: null, markerB: null });

  useEffect(() => {
    if (mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          "osm-tiles": {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "&copy; OpenStreetMap contributors",
          },
        },
        layers: [
          {
            id: "osm-tiles-layer",
            type: "raster",
            source: "osm-tiles",
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: [initialLng, initialLat],
      zoom: initialZoom,
    });

    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("click", (e) => {
      const coords = { lng: e.lngLat.lng, lat: e.lngLat.lat };
      const current = stateRef.current;

      // 1. Pierwsze kliknięcie (lub resetowanie po wcześniejszej parze)
      if (!current.pointA || (current.pointA && current.pointB)) {
        current.markerA?.remove();
        current.markerB?.remove();
        current.markerB = null;

        current.markerA = new maplibregl.Marker({ color: "#10b981" }) // zielony marker (start)
          .setLngLat([coords.lng, coords.lat])
          .addTo(map);

        current.pointA = coords;
        current.pointB = null;
      } 
      // 2. Drugie kliknięcie (zapis celu)
      else if (current.pointA && !current.pointB) {
        current.markerB = new maplibregl.Marker({ color: "#ef4444" }) // czerwony marker (koniec)
          .setLngLat([coords.lng, coords.lat])
          .addTo(map);

        current.pointB = coords;
      }

      // Przekazanie punktów do rodzica
      if (onPointsChange) {
        onPointsChange({ pointA: current.pointA, pointB: current.pointB });
      }
    });

    return () => {
      stateRef.current.markerA?.remove();
      stateRef.current.markerB?.remove();
      map.remove();
      mapRef.current = null;
    };
  }, [initialLng, initialLat, initialZoom, onPointsChange]);

  return <div ref={mapContainerRef} style={{ width: "100%", height: "100%" }} />;
}