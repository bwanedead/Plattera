"""
Quick script to check column headers in PLSS FGDB layers
"""
import fiona
from pathlib import Path

def main():
    fgdb_dir = Path("plss/wyoming/fgdb")
    fgdb_paths = list(fgdb_dir.glob("**/*.gdb"))
    
    print(f"📋 PLSS Layer Schema Summary")
    print(f"════════════════════════════")
    
    for gdb_path in fgdb_paths:
        print(f"\n📁 {gdb_path.name}")
        
        try:
            layers = fiona.listlayers(str(gdb_path))
            
            for layer in layers:
                print(f"\n   🔍 {layer}")
                try:
                    with fiona.open(str(gdb_path), layer=layer) as src:
                        schema = src.schema
                        properties = schema['properties']
                        
                        print(f"      Geometry: {schema['geometry']}")
                        print(f"      Columns: {list(properties.keys())}")
                        
                        # Look for key PLSS identifiers
                        key_cols = []
                        for col in properties.keys():
                            col_lower = col.lower()
                            if any(x in col_lower for x in ['township', 'range', 'section', 'quarter', 'div']):
                                key_cols.append(col)
                        
                        if key_cols:
                            print(f"      PLSS Columns: {key_cols}")
                        
                except Exception as e:
                    print(f"      ❌ Error reading schema: {e}")
                    
        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    main()
