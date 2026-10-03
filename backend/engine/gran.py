import json
from pathlib import Path
from shapely.geometry import box
import geopandas as gpd

def create_bounding_box_shp(input_file: str, output_shp: str):
    # 1. Wczytaj dane ze współrzędnymi (np. plik JSON z punktami/węzłami)
    # Format zakłada np. słownik: {"nazwa": [lon, lat], ...} lub listę punktów
    path = Path(input_file)
    if not path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku: {input_file}")
        
    with open(path, "r", encoding="utf-8") as f:
        nodes_data = json.load(f)

    # 2. Wyciągnij współrzędne X (lon) oraz Y (lat)
    # Dostosuj tę pętlę do struktury swojego nowego pliku (np. jeśli to lista słowników, dict itp.)
    if isinstance(nodes_data, dict):
        xs = [coords[0] for coords in nodes_data.values()]
        ys = [coords[1] for coords in nodes_data.values()]
    elif isinstance(nodes_data, list):
        xs = [item["lon"] for item in nodes_data] # zmień klucze według uznania
        ys = [item["lat"] for item in nodes_data]
    else:
        raise ValueError("Nieobsługiwany format danych w pliku.")

    if not xs or not ys:
        print("Brak współrzędnych do przetworzenia.")
        return

    # 3. Wyznacz granice (bounding box)
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # 4. Utwórz geometrię prostokąta i GeoDataFrame
    bounding_box = box(min_x, min_y, max_x, max_y)
    gdf = gpd.GeoDataFrame(
        [{"id": 1, "opis": "Granice obszaru"}], 
        geometry=[bounding_box], 
        crs="EPSG:4326"
    )

    # 5. Zapisz do pliku Shapefile
    out_path = Path(output_shp)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path)
    
    print(f"Sukces! Zapisano granice obszaru do: {out_path.absolute()}")

if __name__ == "__main__":
    # Przykład użycia w nowym projekcie:
    # Upewnij się, że masz plik z punktami (np. wezly.json)
    create_bounding_box_shp("wezly.json", "wyniki/obszar_projektu.shp")