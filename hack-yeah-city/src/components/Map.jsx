import React, { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css'; // Wymagany podstawowy styl MapLibre (do poprawnego działania kontrolek i kafelków)

export default function MapComponent({ 
  initialLng = 21.0122, 
  initialLat = 52.2297, 
  initialZoom = 12 
}) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);

  useEffect(() => {
    if (mapRef.current) return; // Zapobiega podwójnej inicjalizacji w React 18 StrictMode

    // Inicjalizacja instancji mapy
    mapRef.current = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          'osm-tiles': {
            type: 'raster',
            tiles: [
              'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
            ],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap contributors'
          }
        },
        layers: [
          {
            id: 'osm-tiles-layer',
            type: 'raster',
            source: 'osm-tiles',
            minzoom: 0,
            maxzoom: 19
          }
        ]
      },
      center: [initialLng, initialLat], // [Długość, Szerokość]
      zoom: initialZoom
    });

    // Kontrolki nawigacji (+/- i kompas)
    mapRef.current.addControl(new maplibregl.NavigationControl(), 'top-right');

    // Sprzątanie po odmontowaniu komponentu
    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [initialLng, initialLat, initialZoom]);

  // Kontener mapy musi mieć zdefiniowaną szerokość i wysokość (100% dopasowuje się do rodzica)
  return (
    <div 
      ref={mapContainerRef} 
      style={{ width: '800px', height: '400px' }} 
    />
  );
}