"""
Simple script to list all PLSS layers available in our FGDB files
"""
import fiona
from pathlib import Path
import geopandas as gpd

def main():
    # Get FGDB directory
    fgdb_dir = Path("plss/wyoming/fgdb")
    
    if not fgdb_dir.exists():
        print(f"❌ FGDB directory not found: {fgdb_dir}")
        return
    
    # Find all FGDB files
    fgdb_paths = list(fgdb_dir.glob("**/*.gdb"))
    print(f"📁 Found {len(fgdb_paths)} FGDB files")
    
    all_layers = []
    
    for gdb_path in fgdb_paths:
        print(f"\n🔍 Inspecting: {gdb_path.name}")
        
        try:
            layers = fiona.listlayers(str(gdb_path))
            print(f"   Layers: {layers}")
            
            for layer in layers:
                try:
                    # Quick check - just get feature count and geometry type
                    gdf = gpd.read_file(str(gdb_path), layer=layer, rows=1)
                    full_count = len(gpd.read_file(str(gdb_path), layer=layer))
                    
                    geom_type = "None"
                    if len(gdf) > 0 and gdf.geometry.iloc[0] is not None:
                        geom_type = gdf.geometry.iloc[0].geom_type
                    
                    layer_info = {
                        "gdb": gdb_path.name,
                        "layer": layer, 
                        "features": full_count,
                        "geometry": geom_type
                    }
                    
                    all_layers.append(layer_info)
                    print(f"   • {layer}: {full_count} {geom_type} features")
                    
                except Exception as e:
                    print(f"   ❌ {layer}: Error - {e}")
                    
        except Exception as e:
            print(f"   ❌ Failed to read {gdb_path.name}: {e}")
    
    print(f"\n📋 SUMMARY - All PLSS Layers:")
    print(f"═══════════════════════════════")
    for layer_info in all_layers:
        print(f"{layer_info['layer']} ({layer_info['gdb']}) - {layer_info['features']} {layer_info['geometry']} features")
    
    # Identify polygon layers suitable for overlays
    polygon_layers = [l for l in all_layers if l['geometry'] in ['Polygon', 'MultiPolygon']]
    print(f"\n🗺️  POLYGON LAYERS (suitable for overlays):")
    for layer in polygon_layers:
        print(f"   • {layer['layer']}: {layer['features']} features")
    
    print(f"\n📊 TOTAL: {len(all_layers)} layers, {len(polygon_layers)} polygon layers")

if __name__ == "__main__":
    main()
