import React, { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import proj4 from "proj4";

const EPSG2180 = "+proj=tmerc +lat_0=0 +lon_0=19 +k=0.9993 +x_0=500000 +y_0=-5300000 +ellps=GRS80 +units=m +no_defs";

function transformGeometryToWgs84(geometry) {
  if (!geometry || !geometry.coordinates) return geometry;

  const transformCoords = (coords) => {
    if (!Array.isArray(coords)) return coords;

    if (coords.length === 2 && typeof coords[0] === "number" && typeof coords[1] === "number") {
      const [x, y] = proj4(EPSG2180, "WGS84", [coords[0], coords[1]]);
      return [x, y];
    }

    return coords.map((item) => transformCoords(item));
  };

  return {
    ...geometry,
    coordinates: transformCoords(geometry.coordinates),
  };
}

function transformAoiToWgs84(data) {
  if (!data) return data;

  if (data.type === "FeatureCollection") {
    return {
      ...data,
      features: data.features.map((feature) => ({
        ...feature,
        geometry: transformGeometryToWgs84(feature.geometry),
      })),
    };
  }

  if (data.type === "Feature") {
    return {
      ...data,
      geometry: transformGeometryToWgs84(data.geometry),
    };
  }

  return transformGeometryToWgs84(data);
}

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
    if (!map) return;

    const loadAoi = async () => {
      try {
        const response = await fetch(new URL("../assets/AOI_krk.geojson", import.meta.url));
        const rawAoi = await response.json();
        const aoiData = transformAoiToWgs84(rawAoi);

        if (!map.getSource("aoi-source")) {
          map.addSource("aoi-source", {
            type: "geojson",
            data: aoiData,
          });

          map.addLayer({
            id: "aoi-fill",
            type: "fill",
            source: "aoi-source",
            paint: {
              "fill-color": "#22c55e",
              "fill-opacity": 0.2,
            },
          });

          map.addLayer({
            id: "aoi-outline",
            type: "line",
            source: "aoi-source",
            paint: {
              "line-color": "#16a34a",
              "line-width": 2,
              "line-opacity": 0.9,
            },
          });
        }

        const aoiCoords = aoiData.features?.[0]?.geometry?.coordinates;
        if (aoiCoords) {
          const flat = aoiCoords.flat(Infinity);
          const points = [];
          for (let i = 0; i < flat.length; i += 2) {
            points.push([flat[i], flat[i + 1]]);
          }

          if (points.length > 0) {
            const bounds = points.reduce(
              (b, coord) => b.extend(coord),
              new maplibregl.LngLatBounds(points[0], points[0])
            );
            map.fitBounds(bounds, { padding: 40, maxZoom: 14 });
          }
        }
      } catch (error) {
        console.error("Failed to load AOI layer:", error);
      }
    };

    if (map.isStyleLoaded()) {
      loadAoi();
    } else {
      map.once("load", loadAoi);
    }
  }, []);

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