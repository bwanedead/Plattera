#!/usr/bin/env python3
"""Final test of the fixed transformer with separate caches"""

from pipelines.mapping.projection.transformer import CoordinateTransformer

def test_transformer():
    t = CoordinateTransformer()

    print("=== ROUND-TRIP TEST ===")
    utm_coords = (433873.421, 4562910.166)
    print(f"Original UTM: {utm_coords}")

    # UTM -> Geographic
    geo_result = t.utm_to_geographic(*utm_coords, '13N')
    print(f"UTM->Geo: ({geo_result['lat']:.8f}, {geo_result['lon']:.8f})")

    # Geographic -> UTM
    utm_result = t.geographic_to_utm(geo_result['lat'], geo_result['lon'], '13N')
    print(f"Geo->UTM: ({utm_result['utm_x']:.3f}, {utm_result['utm_y']:.3f})")

    # Check round-trip accuracy
    easting_diff = abs(utm_result["utm_x"] - utm_coords[0])
    northing_diff = abs(utm_result["utm_y"] - utm_coords[1])
    round_trip_success = easting_diff < 0.001 and northing_diff < 0.001

    print(f"Round-trip accuracy: easting_diff={easting_diff:.6f}, northing_diff={northing_diff:.6f}")
    print("✅ Round-trip test PASSED!" if round_trip_success else "❌ Round-trip test FAILED!")

    # Test cache separation
    print("\n=== CACHE SEPARATION TEST ===")
    cache_info = {
        "geo_to_utm_cache": len(t._geo_to_utm_transformers),
        "utm_to_geo_cache": len(t._utm_to_geo_transformers),
        "legacy_cache": len(t._utm_transformers) if hasattr(t, '_utm_transformers') else 0
    }
    print(f"Cache sizes: {cache_info}")

    return round_trip_success

if __name__ == "__main__":
    test_transformer()
