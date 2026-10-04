import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import proj4 from "proj4";
import { L, km } from "../format";

// Podkład mapy. Bez klucza API: Esri World Street Map (dane m.in. z OpenStreetMap).
// Inny dostawca: ustaw VITE_TILES w .env.local (adres z {z}/{x}/{y}) i VITE_TILES_ATTRIBUTION.
const TILE_URLS = [
  import.meta.env.VITE_TILES ||
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
];
const TILE_ATTRIBUTION =
  import.meta.env.VITE_TILES_ATTRIBUTION || "Tiles &copy; Esri, OpenStreetMap contributors";

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

const EMPTY_POINTS = { pointA: null, pointB: null };
const EMPTY_LIST = [];

const SEVERITY_TEXT = {
  blokada: "Przeszkoda nie do pokonania",
  ostrzezenie: "Utrudnienie",
  brak_danych: "Brak danych",
};

// Znacznik zagrożenia: kształt + symbol + podpis (nie sam kolor, WCAG 1.4.1)
function createHazardMarker(hazard) {
  const el = document.createElement("button");
  el.type = "button";
  el.className = `kbb-hazard kbb-hazard-${hazard.severity}`;
  const symbol = hazard.severity === "blokada" ? "✕" : hazard.severity === "brak_danych" ? "?" : "!";
  el.textContent = symbol;
  const where = hazard.at_m !== undefined ? `, po ${hazard.at_m} metrach` : "";
  el.setAttribute(
    "aria-label",
    `${SEVERITY_TEXT[hazard.severity] || "Uwaga"}: ${hazard.spoken || hazard.text}${where}`
  );
  el.title = `${SEVERITY_TEXT[hazard.severity] || "Uwaga"}: ${hazard.text}`;
  return el;
}

function hazardPopup(hazard) {
  const root = document.createElement("div");
  root.className = "kbb-popup";
  const title = document.createElement("strong");
  title.textContent = SEVERITY_TEXT[hazard.severity] || "Uwaga";
  root.appendChild(title);
  const lines = [
    L(hazard.text),
    hazard.at_m !== undefined ? `Po ${km(hazard.at_m)} od startu` : null,
    hazard.street ? `Ulica: ${hazard.street}` : null,
    hazard.source ? `Źródło: ${hazard.source}` : null,
  ].filter(Boolean);
  lines.forEach((line) => {
    const p = document.createElement("div");
    p.textContent = line; // textContent: nazwy z OSM nigdy nie są traktowane jako HTML
    root.appendChild(p);
  });
  return new maplibregl.Popup({ offset: 16, closeButton: true }).setDOMContent(root);
}

function createPinMarker(pin) {
  const el = document.createElement("button");
  el.type = "button";
  el.className = `kbb-pin kbb-pin-${pin.kind || "nearest"}`;
  el.textContent = pin.label ?? "";
  el.setAttribute("aria-label", pin.aria || pin.title || "Punkt na mapie");
  el.title = pin.title || "";
  return el;
}

// Maska "wszystko poza obszarem demo": prostokąt świata z dziurą w kształcie obszaru (przyciemnia to, czego nie obejmujemy).
function outsideMask(aoiData) {
  const geom = aoiData?.type === "FeatureCollection" ? aoiData.features?.[0]?.geometry : aoiData?.geometry || aoiData;
  if (!geom) return null;
  const polygons = geom.type === "Polygon" ? [geom.coordinates] : geom.type === "MultiPolygon" ? geom.coordinates : [];
  if (!polygons.length) return null;
  const world = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [world, ...polygons.map((p) => p[0])] } };
}

function stopPopup(props) {
  const root = document.createElement("div");
  root.className = "kbb-popup";
  const title = document.createElement("strong");
  title.textContent = `${props.mode === "tramwaj" ? "Przystanek tramwajowy" : "Przystanek autobusowy"}: ${props.name}`;
  root.appendChild(title);
  const lines = [
    props.lines?.length ? `Linie: ${props.lines.join(", ")}` : null,
    `Dostępność przystanku: ${props.wheelchair_boarding_text || "brak danych"}`,
    "Źródło: rozkład ZTP Kraków",
  ].filter(Boolean);
  lines.forEach((line) => {
    const d = document.createElement("div");
    d.textContent = line; // textContent: nazwy nigdy nie są traktowane jako HTML
    root.appendChild(d);
  });
  return new maplibregl.Popup({ offset: 14, closeButton: true }).setDOMContent(root);
}

function createStopMarker(props) {
  const el = document.createElement("div");
  el.className = `kbb-stop kbb-stop-${props.mode === "tramwaj" ? "tram" : "bus"}`;
  el.textContent = props.mode === "tramwaj" ? "T" : "A";
  el.title = `${props.mode === "tramwaj" ? "Tramwaj" : "Autobus"}: ${props.name}`;
  el.setAttribute("aria-hidden", "true"); // te same informacje są w liście „Przystanki w pobliżu”
  return el;
}

function createSignalMarker(props, active) {
  const el = document.createElement("button");
  el.type = "button";
  el.className = `kbb-signal${active ? " kbb-signal-active" : ""}${props.questioned ? " kbb-signal-questioned" : ""}`;
  el.textContent = "!";
  el.setAttribute("aria-label", `Zgłoszenie społeczności: ${props.category_label}. Otwórz szczegóły.`);
  el.title = `${props.category_label} (niezweryfikowane)`;
  return el;
}

function createDraftMarker() {
  const el = document.createElement("div");
  el.className = "kbb-signal-draft";
  el.setAttribute("aria-hidden", "true");
  return el;
}

function boundsOf(value) {
  const flat = [];
  const walk = (v) => {
    if (!v) return;
    if (Array.isArray(v)) {
      if (v.length >= 2 && typeof v[0] === "number" && typeof v[1] === "number") flat.push(v);
      else v.forEach(walk);
    } else if (v.type === "FeatureCollection") v.features.forEach(walk);
    else if (v.type === "Feature") walk(v.geometry);
    else if (v.coordinates) walk(v.coordinates);
  };
  walk(value);
  if (!flat.length) return null;
  return flat.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(flat[0], flat[0]));
}

const Map = forwardRef(function Map(
  {
    initialLng = 19.94,
    initialLat = 50.06,
    initialZoom = 11,
    onPointsChange,
    points = EMPTY_POINTS,
    routes = EMPTY_LIST, // tablica Feature z /api/routes
    selectedRoute = 0,
    hazards = EMPTY_LIST,
    pins = EMPTY_LIST,
    footprint = null,
    observations = null,
    showObservations = false,
    stops = null,
    area, // undefined = jeszcze się wczytuje, null = brak (używamy pliku zapasowego), obiekt = Feature z /api/area
    theme = "light",
    clickMode = "route",
    onInfoClick,
    onPinClick,
    clearSelectionVersion = 0,
    reduceMotion = false,
    insets = null, // {top,left,right,bottom} w px: część mapy zasłonięta przez pływające panele
    signals = null, // FeatureCollection zgłoszeń społeczności
    activeSignalId = null,
    onSignalClick,
    onReportClick, // tryb "report": klik na mapie wskazuje miejsce zgłoszenia
    draft = null, // {lng, lat} miejsce właśnie zgłaszane
  },
  ref
) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const loadedRef = useRef(false);
  const stateRef = useRef({ pointA: null, pointB: null, markerA: null, markerB: null });
  const clearSelectionVersionRef = useRef(clearSelectionVersion);
  const onPointsChangeRef = useRef(onPointsChange);
  const onInfoClickRef = useRef(onInfoClick);
  const onReportClickRef = useRef(onReportClick);
  const onSignalClickRef = useRef(onSignalClick);
  const signalMarkersRef = useRef([]);
  const draftMarkerRef = useRef(null);
  const onPinClickRef = useRef(onPinClick);
  const clickModeRef = useRef(clickMode);
  const reduceMotionRef = useRef(reduceMotion);
  const insetsRef = useRef(insets);
  const hazardMarkersRef = useRef([]);
  const pinMarkersRef = useRef([]);
  const stopMarkersRef = useRef([]);
  const lastRoutesRef = useRef(null);

  useEffect(() => {
    onPointsChangeRef.current = onPointsChange;
    onInfoClickRef.current = onInfoClick;
    onReportClickRef.current = onReportClick;
    onSignalClickRef.current = onSignalClick;
    onPinClickRef.current = onPinClick;
    clickModeRef.current = clickMode;
    reduceMotionRef.current = reduceMotion;
    insetsRef.current = insets;
  }, [onPointsChange, onInfoClick, onReportClick, onSignalClick, onPinClick, clickMode, reduceMotion, insets]);

  // odstęp od krawędzi, żeby trasa nie chowała się pod pływającymi kartami
  const pad = (base) => {
    const i = insetsRef.current || {};
    return {
      top: base + (i.top || 0),
      left: base + (i.left || 0),
      right: base + (i.right || 0),
      bottom: base + (i.bottom || 0),
    };
  };

  const whenLoaded = (fn) => {
    const map = mapRef.current;
    if (!map) return;
    if (loadedRef.current) fn(map);
    else map.once("load", () => fn(map));
  };

  const placeMarker = (which, coords) => {
    const map = mapRef.current;
    const current = stateRef.current;
    const markerKey = which === "A" ? "markerA" : "markerB";
    const pointKey = which === "A" ? "pointA" : "pointB";
    current[markerKey]?.remove();
    current[markerKey] = null;
    current[pointKey] = coords || null;
    if (!coords || !map) return;
    current[markerKey] = new maplibregl.Marker({
      element: createModernMarker(which === "A" ? "#58b6c6" : "#e15a4f", which),
      anchor: "bottom",
    })
      .setLngLat([coords.lng, coords.lat])
      .addTo(map);
  };

  useImperativeHandle(ref, () => ({
    // ustawia znaczniki A/B z zewnątrz (np. "Moja lokalizacja", "Trasa tutaj"); nie woła onPointsChange
    setPoints(a, b) {
      placeMarker("A", a);
      placeMarker("B", b);
    },
    getPoints() {
      const { pointA, pointB } = stateRef.current;
      return { pointA, pointB };
    },
    flyTo(lon, lat, zoom = 17) {
      const map = mapRef.current;
      if (!map) return;
      const padding = pad(0);
      if (reduceMotionRef.current) map.jumpTo({ center: [lon, lat], zoom, padding });
      else map.flyTo({ center: [lon, lat], zoom, padding });
    },
    resize() {
      mapRef.current?.resize();
    },
  }));

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
            tiles: TILE_URLS,
            tileSize: 256,
            attribution: TILE_ATTRIBUTION,
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
      pitch: 0,
      bearing: 0,
    });

    mapRef.current = map;
    map.on("load", () => {
      loadedRef.current = true;
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("click", (e) => {
      // klik w znacznik zagrożenia / wyniku nie jest klikiem w mapę
      if (e.originalEvent?.target?.closest?.(".kbb-hazard, .kbb-pin, .kbb-stop, .kbb-signal, .maplibregl-popup")) return;
      const coords = { lng: e.lngLat.lng, lat: e.lngLat.lat };

      // tryb "zgłoś problem": klik wskazuje miejsce zgłoszenia, nie zmienia trasy
      if (clickModeRef.current === "report") {
        onReportClickRef.current?.(coords);
        return;
      }

      // tryb "sprawdź miejsce": klik trafia do /api/at, nie zmienia trasy
      if (clickModeRef.current === "info") {
        onInfoClickRef.current?.(coords);
        return;
      }

      const current = stateRef.current;
      if (!current.pointA || (current.pointA && current.pointB)) {
        placeMarker("B", null);
        placeMarker("A", coords);
      } else if (current.pointA && !current.pointB) {
        placeMarker("B", coords);
      }
      onPointsChangeRef.current?.({ pointA: current.pointA, pointB: current.pointB });
    });

    const markerState = stateRef.current;
    const hazardMarkers = hazardMarkersRef;
    const pinMarkers = pinMarkersRef;
    return () => {
      markerState.markerA?.remove();
      markerState.markerB?.remove();
      hazardMarkers.current.forEach((m) => m.remove());
      pinMarkers.current.forEach((m) => m.remove());
      stopMarkersRef.current.forEach((m) => m.remove());
      signalMarkersRef.current.forEach((m) => m.remove());
      draftMarkerRef.current?.remove();
      map.remove();
      mapRef.current = null;
      loadedRef.current = false;
    };
  }, [initialLng, initialLat, initialZoom]);

  useEffect(() => {
    const map = mapRef.current;
    if (map) map.getCanvas().style.cursor = clickMode === "info" ? "help" : clickMode === "report" ? "crosshair" : "";
  }, [clickMode]);

  useEffect(() => {
    if (clearSelectionVersionRef.current === clearSelectionVersion) return;
    clearSelectionVersionRef.current = clearSelectionVersion;
    placeMarker("A", null);
    placeMarker("B", null);
  }, [clearSelectionVersion]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const canvas = map.getCanvas();
    if (canvas) {
      canvas.style.filter = theme === "dark" ? "brightness(0.72) saturate(1.2) contrast(1.15)" : "none";
      canvas.style.transition = reduceMotion ? "none" : "filter 0.2s ease";
    }

    const container = map.getContainer();
    if (container) {
      container.style.background = theme === "dark" ? "#211e2d" : "#e6f6f8";
    }
  }, [theme, reduceMotion]);

  // Obszar z danymi: z /api/area (to samo, co widzi backend); plik zapasowy tylko gdy API nie odpowiada
  useEffect(() => {
    if (area === undefined) return;
    let cancelled = false;

    const drawAoi = (aoiData, fit) => {
      whenLoaded((map) => {
        if (cancelled) return;
        if (map.getSource("aoi-source")) {
          map.getSource("aoi-source").setData(aoiData);
          map.getSource("aoi-mask-source")?.setData(outsideMask(aoiData) || { type: "FeatureCollection", features: [] });
        } else {
          map.addSource("aoi-source", { type: "geojson", data: aoiData });
          map.addSource("aoi-mask-source", { type: "geojson", data: outsideMask(aoiData) || { type: "FeatureCollection", features: [] } });
          // pod trasami i znacznikami: przyciemnienie świata poza obszarem, półprzezroczyste wypełnienie i obrys
          const below = map.getLayer("routes-alt") ? "routes-alt" : undefined;
          map.addLayer({ id: "aoi-mask", type: "fill", source: "aoi-mask-source", paint: { "fill-color": "#1a1530", "fill-opacity": 0.32 } }, below);
          map.addLayer({ id: "aoi-fill", type: "fill", source: "aoi-source", paint: { "fill-color": "#7a6cb1", "fill-opacity": 0.14 } }, below);
          map.addLayer({ id: "aoi-casing", type: "line", source: "aoi-source", paint: { "line-color": "#ffffff", "line-width": 6, "line-opacity": 0.9 } }, below);
          map.addLayer({ id: "aoi-outline", type: "line", source: "aoi-source", paint: { "line-color": "#4b3f8f", "line-width": 3 } }, below);
        }
        const bounds = boundsOf(aoiData);
        if (bounds) {
          const ne = bounds.getNorthEast();
          const sw = bounds.getSouthWest();
          // można oddalić mapę daleko poza obszar demo (widać całe miasto i okolice), ale nie na cały świat
          map.setMinZoom(8);
          map.setMaxBounds([
            [sw.lng - 1.0, sw.lat - 0.7],
            [ne.lng + 1.0, ne.lat + 0.7],
          ]);
          if (fit) map.fitBounds(bounds, { padding: pad(140), maxZoom: 12, animate: !reduceMotionRef.current });
        }
      });
    };

    if (area) {
      drawAoi(area, true);
    } else {
      fetch(new URL("../assets/AOI_krk.geojson", import.meta.url))
        .then((r) => r.json())
        .then((raw) => {
          if (!cancelled) drawAoi(transformAoiToWgs84(raw), true);
        })
        .catch((error) => console.error("Failed to load AOI layer:", error));
    }
    return () => {
      cancelled = true;
    };
  }, [area]);

  // Warianty trasy: wybrany = gruba ciągła linia z obwódką, pozostałe = cienka przerywana (różnica nie tylko kolorem)
  useEffect(() => {
    whenLoaded((map) => {
      const features = (routes || [])
        .filter((r) => r && r.geometry)
        .map((r, i) => {
          const withEnds = addPointConnectors(r, points);
          return {
            type: "Feature",
            geometry: withEnds.geometry,
            properties: { sel: i === selectedRoute ? 1 : 0, idx: i },
          };
        });
      const data = { type: "FeatureCollection", features };
      if (map.getSource("routes-source")) {
        map.getSource("routes-source").setData(data);
      } else {
        map.addSource("routes-source", { type: "geojson", data });
        map.addLayer({
          id: "routes-alt",
          type: "line",
          source: "routes-source",
          filter: ["==", ["get", "sel"], 0],
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": "#6b5fa5", "line-width": 3, "line-opacity": 0.8, "line-dasharray": [2, 2] },
        });
        map.addLayer({
          id: "routes-casing",
          type: "line",
          source: "routes-source",
          filter: ["==", ["get", "sel"], 1],
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.95 },
        });
        map.addLayer({
          id: "routes-main",
          type: "line",
          source: "routes-source",
          filter: ["==", ["get", "sel"], 1],
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": "#c2362b", "line-width": 5, "line-opacity": 1 },
        });
      }
      if (routes !== lastRoutesRef.current) {
        lastRoutesRef.current = routes;
        const selected = features.find((f) => f.properties.sel === 1) || features[0];
        const bounds = selected && boundsOf(selected);
        if (bounds) map.fitBounds(bounds, { padding: pad(60), maxZoom: 17, animate: !reduceMotionRef.current });
      }
    });
  }, [routes, selectedRoute, points]);

  // Zagrożenia wybranej trasy
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    hazardMarkersRef.current.forEach((m) => m.remove());
    hazardMarkersRef.current = [];
    (hazards || []).forEach((hazard) => {
      if (typeof hazard.lon !== "number" || typeof hazard.lat !== "number") return;
      const marker = new maplibregl.Marker({ element: createHazardMarker(hazard) })
        .setLngLat([hazard.lon, hazard.lat])
        .setPopup(hazardPopup(hazard))
        .addTo(map);
      hazardMarkersRef.current.push(marker);
    });
  }, [hazards]);

  // Punkty: wyniki "najbliżej mnie", kliknięty obiekt
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    pinMarkersRef.current.forEach((m) => m.remove());
    pinMarkersRef.current = [];
    (pins || []).forEach((pin) => {
      const el = createPinMarker(pin);
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        onPinClickRef.current?.(pin);
      });
      const marker = new maplibregl.Marker({ element: el }).setLngLat([pin.lon, pin.lat]).addTo(map);
      pinMarkersRef.current.push(marker);
    });
  }, [pins]);

  // Wszystkie przystanki (T = tramwaj, A = autobus): litera, nie tylko kolor
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    stopMarkersRef.current.forEach((m) => m.remove());
    stopMarkersRef.current = [];
    (stops?.features || []).slice(0, 1500).forEach((f) => {
      const props = f.properties || {};
      const [lng, lat] = f.geometry?.coordinates || [];
      if (typeof lng !== "number") return;
      const el = createStopMarker(props);
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        stopPopup(props).setLngLat([lng, lat]).addTo(map);
      });
      stopMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([lng, lat]).addTo(map));
    });
  }, [stops]);

  // Zgłoszenia społeczności (pinezki "!") i miejsce właśnie zgłaszane
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    signalMarkersRef.current.forEach((m) => m.remove());
    signalMarkersRef.current = [];
    (signals?.features || []).slice(0, 400).forEach((f) => {
      const props = f.properties || {};
      const [lng, lat] = f.geometry?.coordinates || [];
      if (typeof lng !== "number") return;
      const el = createSignalMarker(props, props.id === activeSignalId);
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        onSignalClickRef.current?.(props.id);
      });
      signalMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([lng, lat]).addTo(map));
    });
  }, [signals, activeSignalId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    draftMarkerRef.current?.remove();
    draftMarkerRef.current = null;
    if (draft) draftMarkerRef.current = new maplibregl.Marker({ element: createDraftMarker() }).setLngLat([draft.lng, draft.lat]).addTo(map);
  }, [draft]);

  // Obrys klikniętego budynku
  useEffect(() => {
    whenLoaded((map) => {
      const data = footprint
        ? { type: "Feature", geometry: footprint, properties: {} }
        : { type: "FeatureCollection", features: [] };
      if (map.getSource("footprint-source")) {
        map.getSource("footprint-source").setData(data);
      } else {
        map.addSource("footprint-source", { type: "geojson", data });
        map.addLayer({
          id: "footprint-fill",
          type: "fill",
          source: "footprint-source",
          paint: { "fill-color": "#f4cc5c", "fill-opacity": 0.45 },
        });
        map.addLayer({
          id: "footprint-outline",
          type: "line",
          source: "footprint-source",
          paint: { "line-color": "#7a5a00", "line-width": 3 },
        });
      }
    });
  }, [footprint]);

  // Obserwacje z nalotu (warstwa opcjonalna)
  useEffect(() => {
    whenLoaded((map) => {
      const data = showObservations && observations ? observations : { type: "FeatureCollection", features: [] };
      if (map.getSource("obs-source")) {
        map.getSource("obs-source").setData(data);
      } else {
        map.addSource("obs-source", { type: "geojson", data });
        map.addLayer({
          id: "obs-layer",
          type: "circle",
          source: "obs-source",
          paint: {
            "circle-radius": 7,
            "circle-color": "#f4cc5c",
            "circle-stroke-color": "#3b2f00",
            "circle-stroke-width": 2,
          },
        });
      }
    });
  }, [observations, showObservations]);

  return <div ref={mapContainerRef} style={{ width: "100%", height: "100%" }} />;
});

export default Map;
