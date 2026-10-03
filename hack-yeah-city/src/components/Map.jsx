import React, { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import proj4 from "proj4";

const EPSG2180 = "+proj=tmerc +lat_0=0 +lon_0=19 +k=0.9993 +x_0=500000 +y_0=-5300000 +ellps=GRS80 +units=m +no_defs";

function createModernMarker(color, label) {
  const el = document.createElement("div");
  el.style.width = "22px";
  el.style.height = "28px";
  el.style.position = "relative";
  el.style.zIndex = "1";

  const bubble = document.createElement("div");
  bubble.style.position = "absolute";
  bubble.style.top = "0";
  bubble.style.left = "0";
  bubble.style.width = "22px";
  bubble.style.height = "22px";
  bubble.style.boxSizing = "border-box";
  bubble.style.borderRadius = "50%";
  bubble.style.background = color;
  bubble.style.border = "3px solid #ffffff";
  bubble.style.boxShadow = "0 8px 18px rgba(15, 23, 42, 0.28)";
  bubble.style.display = "flex";
  bubble.style.alignItems = "center";
  bubble.style.justifyContent = "center";
  bubble.style.fontSize = "10px";
  bubble.style.fontWeight = "700";
  bubble.style.color = "#ffffff";
  bubble.style.lineHeight = "1";
  bubble.textContent = label;

  const tail = document.createElement("div");
  tail.style.position = "absolute";
  tail.style.bottom = "4px";
  tail.style.left = "50%";
  tail.style.transform = "translateX(-50%) rotate(45deg)";
  tail.style.width = "10px";
  tail.style.height = "10px";
  tail.style.background = color;
  tail.style.borderRight = "3px solid #ffffff";
  tail.style.borderBottom = "3px solid #ffffff";
  tail.style.borderRadius = "2px";
  tail.style.zIndex = "0";
  el.appendChild(tail);
  el.appendChild(bubble);

  return el;
}

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

function getLocalCoordinates(coordinate, referenceLatitude) {
  const longitudeScale = 111_320 * Math.cos((referenceLatitude * Math.PI) / 180);
  return [
    coordinate[0] * longitudeScale,
    coordinate[1] * 110_540,
  ];
}

function getSegmentProjection(point, start, end) {
  const referenceLatitude = (point[1] + start[1] + end[1]) / 3;
  const projectedPoint = getLocalCoordinates(point, referenceLatitude);
  const projectedStart = getLocalCoordinates(start, referenceLatitude);
  const projectedEnd = getLocalCoordinates(end, referenceLatitude);
  const segment = [
    projectedEnd[0] - projectedStart[0],
    projectedEnd[1] - projectedStart[1],
  ];
  const segmentLengthSquared = segment[0] ** 2 + segment[1] ** 2;
  if (segmentLengthSquared === 0) return null;

  const rawFraction =
    ((projectedPoint[0] - projectedStart[0]) * segment[0] +
      (projectedPoint[1] - projectedStart[1]) * segment[1]) /
    segmentLengthSquared;
  const fraction = Math.max(0, Math.min(1, rawFraction));

  const projectedFoot = [
    projectedStart[0] + fraction * segment[0],
    projectedStart[1] + fraction * segment[1],
  ];
  const longitudeScale = 111_320 * Math.cos((referenceLatitude * Math.PI) / 180);

  return {
    fraction,
    isPerpendicular: rawFraction >= 0 && rawFraction <= 1,
    coordinate: [projectedFoot[0] / longitudeScale, projectedFoot[1] / 110_540],
    distance: Math.hypot(
      projectedPoint[0] - projectedFoot[0],
      projectedPoint[1] - projectedFoot[1]
    ),
  };
}

function coordinateDistance(start, end) {
  const referenceLatitude = (start[1] + end[1]) / 2;
  const projectedStart = getLocalCoordinates(start, referenceLatitude);
  const projectedEnd = getLocalCoordinates(end, referenceLatitude);
  return Math.hypot(
    projectedEnd[0] - projectedStart[0],
    projectedEnd[1] - projectedStart[1]
  );
}

function findEndpointProjection(coordinates, point, fromStart) {
  const searchDistanceMeters = 50;
  let distanceAlongRoute = 0;
  let nearestProjection = null;
  let nearestPerpendicularProjection = null;

  for (let offset = 0; offset < coordinates.length - 1; offset += 1) {
    const index = fromStart ? offset : coordinates.length - 2 - offset;
    const start = coordinates[index];
    const end = coordinates[index + 1];
    const segmentLength = coordinateDistance(start, end);
    if (distanceAlongRoute > searchDistanceMeters) break;

    const projection = getSegmentProjection(point, start, end);
    if (projection) {
      const candidate = {
        ...projection,
        index,
      };
      if (!nearestProjection || candidate.distance < nearestProjection.distance) {
        nearestProjection = candidate;
      }
      if (
        candidate.isPerpendicular &&
        (!nearestPerpendicularProjection ||
          candidate.distance < nearestPerpendicularProjection.distance)
      ) {
        nearestPerpendicularProjection = candidate;
      }
    }
    distanceAlongRoute += segmentLength;
  }

  return nearestPerpendicularProjection || nearestProjection;
}

function spliceRouteEndpoint(coordinates, point, projection, fromStart) {
  const { coordinate, fraction, index } = projection;
  if (fromStart) {
    const remainder = fraction > 0.999999
      ? coordinates.slice(index + 2)
      : coordinates.slice(index + 1);
    return [point, coordinate, ...remainder];
  }

  const prefix = fraction < 0.000001
    ? coordinates.slice(0, index)
    : coordinates.slice(0, index + 1);
  return [...prefix, coordinate, point];
}

function addPointConnectors(routeFeature, points) {
  const isFeatureCollection = routeFeature.type === "FeatureCollection";
  const features = isFeatureCollection
    ? routeFeature.features.map((feature) => ({
        ...feature,
        geometry: feature.geometry && {
          ...feature.geometry,
          coordinates: structuredClone(feature.geometry.coordinates),
        },
      }))
    : [
        routeFeature.type === "Feature"
          ? {
              ...routeFeature,
              geometry: {
                ...routeFeature.geometry,
                coordinates: structuredClone(routeFeature.geometry.coordinates),
              },
            }
          : {
              type: "Feature",
              properties: {},
              geometry: {
                ...routeFeature,
                coordinates: structuredClone(routeFeature.coordinates),
              },
            },
      ];
  const routeLines = [];

  features.forEach((feature, featureIndex) => {
    const geometry = feature.geometry;
    if (geometry?.type === "LineString") {
      routeLines.push({ featureIndex, lineIndex: null, coordinates: geometry.coordinates });
    } else if (geometry?.type === "MultiLineString") {
      geometry.coordinates.forEach((coordinates, lineIndex) => {
        routeLines.push({ featureIndex, lineIndex, coordinates });
      });
    }
  });
  if (routeLines.length === 0) return routeFeature;

  const startLine = routeLines[0];
  const endLine = routeLines[routeLines.length - 1];
  const startPoint = points.pointA && [points.pointA.lng, points.pointA.lat];
  const endPoint = points.pointB && [points.pointB.lng, points.pointB.lat];

  if (startPoint && startLine.coordinates.length > 1) {
    const projection = findEndpointProjection(startLine.coordinates, startPoint, true);
    if (projection) {
      startLine.coordinates = spliceRouteEndpoint(
        startLine.coordinates,
        startPoint,
        projection,
        true
      );
      if (startLine.featureIndex === endLine.featureIndex &&
          startLine.lineIndex === endLine.lineIndex) {
        endLine.coordinates = startLine.coordinates;
      }
    }
  }

  if (endPoint && endLine.coordinates.length > 1) {
    const projection = findEndpointProjection(endLine.coordinates, endPoint, false);
    if (projection) {
      endLine.coordinates = spliceRouteEndpoint(
        endLine.coordinates,
        endPoint,
        projection,
        false
      );
    }
  }

  routeLines.forEach(({ featureIndex, lineIndex, coordinates }) => {
    if (lineIndex === null) {
      features[featureIndex].geometry.coordinates = coordinates;
    } else {
      features[featureIndex].geometry.coordinates[lineIndex] = coordinates;
    }
  });

  return isFeatureCollection ? { ...routeFeature, features } : features[0];
}

export default function Map({
  initialLng = 19.94,
  initialLat = 50.06,
  initialZoom = 13,
  onPointsChange,
  points = { pointA: null, pointB: null },
  routeData = null, // GeoJSON z trasą z API
  theme = "light",
  clearSelectionVersion = 0,
}) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const loadedRef = useRef(false);
  const stateRef = useRef({ pointA: null, pointB: null, markerA: null, markerB: null });
  const clearSelectionVersionRef = useRef(clearSelectionVersion);
  
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
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
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
      maxBounds: [[19.9, 50.03], [19.99, 50.09]],
      pitch: 0,
      bearing: 0,
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

        current.markerA = new maplibregl.Marker({
          element: createModernMarker("#58b6c6", "A"),
          anchor: "bottom",
        })
          .setLngLat([coords.lng, coords.lat])
          .addTo(map);

        current.pointA = coords;
        current.pointB = null;
      }
      // 2. Drugie kliknięcie
      else if (current.pointA && !current.pointB) {
        current.markerB = new maplibregl.Marker({
          element: createModernMarker("#e15a4f", "B"),
          anchor: "bottom",
        })
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
    if (clearSelectionVersionRef.current === clearSelectionVersion) return;
    clearSelectionVersionRef.current = clearSelectionVersion;

    const map = mapRef.current;
    if (!map) return;

    const current = stateRef.current;
    current.markerA?.remove();
    current.markerB?.remove();
    current.markerA = null;
    current.markerB = null;
    current.pointA = null;
    current.pointB = null;

    if (map.getLayer("route-layer")) {
      map.removeLayer("route-layer");
    }
    if (map.getSource("route-source")) {
      map.removeSource("route-source");
    }
  }, [clearSelectionVersion]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const canvas = map.getCanvas();
    if (canvas) {
      canvas.style.filter = theme === "dark" ? "brightness(0.72) saturate(1.2) contrast(1.15)" : "none";
      canvas.style.transition = "filter 0.2s ease";
    }

    const container = map.getContainer();
    if (container) {
      container.style.background = theme === "dark" ? "#211e2d" : "#e6f6f8";
    }
  }, [theme]);

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
              "fill-color": "#58b6c6",
              "fill-opacity": 0.16,
            },
          });

          map.addLayer({
            id: "aoi-outline",
            type: "line",
            source: "aoi-source",
            paint: {
              "line-color": "#7a6cb1",
              "line-width": 3,
              "line-opacity": 0.95,
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

    const normalizedRoute = normalizeRouteData(routeData);
    if (!normalizedRoute) return;
    const geojsonFeature = addPointConnectors(normalizedRoute, points);

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
            "line-color": "#e15a4f",
            "line-width": 5,
            "line-opacity": 0.9,
            "line-gap-width": 0,
          },
        });
      }

      const flatCoords = [];
      const collectCoordinates = (value) => {
        if (!value) return;
        if (Array.isArray(value)) {
          if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") {
            flatCoords.push(value);
          } else {
            value.forEach(collectCoordinates);
          }
          return;
        }
        if (value.type === "FeatureCollection") {
          value.features.forEach(collectCoordinates);
        } else if (value.type === "Feature") {
          collectCoordinates(value.geometry);
        } else if (value.type === "GeometryCollection") {
          value.geometries.forEach(collectCoordinates);
        } else if (value.coordinates) {
          collectCoordinates(value.coordinates);
        }
      };
      collectCoordinates(geojsonFeature);

      if (flatCoords.length > 0) {
        const bounds = flatCoords.reduce(
          (b, coord) => b.extend(coord),
          new maplibregl.LngLatBounds(flatCoords[0], flatCoords[0])
        );
        map.fitBounds(bounds, { padding: 60, maxZoom: 16 });
      }
    };

    // isStyleLoaded() bywa false, gdy trwa ładowanie kafelków, a "load" odpala się tylko raz,
    // więc opieramy się na własnej fladze.
    if (loadedRef.current) {
      drawRoute();
    } else {
      map.once("load", drawRoute);
    }
  }, [routeData, points]);

  return <div ref={mapContainerRef} style={{ width: "100%", height: "100%" }} />;
}