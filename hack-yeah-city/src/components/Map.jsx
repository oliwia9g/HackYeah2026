import React, { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

export default function Map({
  initialLng = 19.94,
  initialLat = 50.06,
  initialZoom = 13,
  onPointsChange,
  routeData = null, // GeoJSON z trasą z API
}) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const loadedRef = useRef(false);
  const stateRef = useRef({ pointA: null, pointB: null, markerA: null, markerB: null });
  
  // POPRAWKA 1: Utrzymanie aktualnej referencji do onPointsChange bez wyzwalania re-renderów mapy
  const onPointsChangeRef = useRef(onPointsChange);

  useEffect(() => {
    onPointsChangeRef.current = onPointsChange;
  }, [onPointsChange]);

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
      // obszar demo backendu (backend/config.yaml), z lekkim zapasem
      maxBounds: [[19.9, 50.03], [19.99, 50.09]],
    });

    mapRef.current = map;
    map.on("load", () => {
      loadedRef.current = true;
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("click", (e) => {
      const coords = { lng: e.lngLat.lng, lat: e.lngLat.lat };
      const current = stateRef.current;

      // 1. Pierwsze kliknięcie (lub reset po poprzedniej parze)
      if (!current.pointA || (current.pointA && current.pointB)) {
        current.markerA?.remove();
        current.markerB?.remove();
        current.markerB = null;

        if (map.getLayer("route-layer")) {
          map.removeLayer("route-layer");
        }
        if (map.getSource("route-source")) {
          map.removeSource("route-source");
        }

        current.markerA = new maplibregl.Marker({ color: "#10b981" })
          .setLngLat([coords.lng, coords.lat])
          .addTo(map);

        current.pointA = coords;
        current.pointB = null;
      }
      // 2. Drugie kliknięcie
      else if (current.pointA && !current.pointB) {
        current.markerB = new maplibregl.Marker({ color: "#ef4444" })
          .setLngLat([coords.lng, coords.lat])
          .addTo(map);

        current.pointB = coords;
      }

      // Wykorzystanie bezpiecznej referencji
      if (onPointsChangeRef.current) {
        onPointsChangeRef.current({ pointA: current.pointA, pointB: current.pointB });
      }
    });

    return () => {
      stateRef.current.markerA?.remove();
      stateRef.current.markerB?.remove();
      map.remove();
      mapRef.current = null;
      loadedRef.current = false;
    };
  }, [initialLng, initialLat, initialZoom]); // POPRAWKA 1: Usunięcie onPointsChange z dependencies

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !routeData) return;

    const normalizeRouteData = (value) => {
      if (!value) return null;

      if (
        value.type === "Feature" ||
        value.type === "FeatureCollection" ||
        value.type === "LineString" ||
        value.type === "MultiLineString" ||
        value.type === "GeometryCollection"
      ) {
        return value;
      }

      if (value.geometry) {
        return {
          type: "Feature",
          geometry: value.geometry,
        };
      }

      if (Array.isArray(value)) {
        return {
          type: "Feature",
          geometry: {
            type: "LineString",
            coordinates: value,
          },
        };
      }

      if (value.coordinates && Array.isArray(value.coordinates)) {
        return {
          type: "Feature",
          geometry: {
            type: value.type || "LineString",
            coordinates: value.coordinates,
          },
        };
      }

      if (value.route) {
        return normalizeRouteData(value.route);
      }

      if (Array.isArray(value.routes) && value.routes.length > 0) {
        return normalizeRouteData(value.routes[0]);
      }

      if (Array.isArray(value.features) && value.features.length > 0) {
        const feature = value.features.find((item) => item && item.geometry);
        return feature ? normalizeRouteData(feature) : value;
      }

      if (value.geojson) {
        return normalizeRouteData(value.geojson);
      }

      return null;
    };

    const geojsonFeature = normalizeRouteData(routeData);
    if (!geojsonFeature) return;

    const drawRoute = () => {
      const routeSource = map.getSource("route-source");
      if (routeSource) {
        routeSource.setData(geojsonFeature);
      } else {
        map.addSource("route-source", {
          type: "geojson",
          data: geojsonFeature,
        });

        map.addLayer({
          id: "route-layer",
          type: "line",
          source: "route-source",
          layout: {
            "line-join": "round",
            "line-cap": "round",
          },
          paint: {
            "line-color": "#2563eb",
            "line-width": 5,
            "line-opacity": 0.85,
          },
        });
      }

      // POPRAWKA 2: Bezpieczne pobieranie tablicy współrzędnych niezależnie od typu GeoJSON
      let coords = null;
      
      if (geojsonFeature.geometry?.coordinates) {
        coords = geojsonFeature.geometry.coordinates;
      } else if (geojsonFeature.type === "LineString" || geojsonFeature.type === "MultiLineString") {
        coords = geojsonFeature.coordinates;
      } else if (geojsonFeature.type === "FeatureCollection" && geojsonFeature.features.length > 0) {
        coords = geojsonFeature.features[0].geometry?.coordinates;
      }

      if (coords && coords.length > 0) {
        // Ubezpieczenie w przypadku MultiLineString (tablica w tablicy)
        const flatCoords = Array.isArray(coords[0]) && Array.isArray(coords[0][0]) 
          ? coords.flat() 
          : coords;

        if (flatCoords.length > 0) {
          const bounds = flatCoords.reduce(
            (b, coord) => b.extend(coord),
            new maplibregl.LngLatBounds(flatCoords[0], flatCoords[0])
          );
          map.fitBounds(bounds, { padding: 60, maxZoom: 16 });
        }
      }
    };

    // isStyleLoaded() bywa false, gdy trwa ładowanie kafelków, a "load" odpala się tylko raz,
    // więc opieramy się na własnej fladze.
    if (loadedRef.current) {
      drawRoute();
    } else {
      map.once("load", drawRoute);
    }
  }, [routeData]);

  return <div ref={mapContainerRef} style={{ width: "100%", height: "100%" }} />;
}