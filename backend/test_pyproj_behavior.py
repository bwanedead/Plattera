#!/usr/bin/env python3
"""
Standalone test to verify PyProj transformer behavior
"""
import sys
sys.path.append('.')

from pyproj import CRS, Transformer
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_pyproj_behavior():
    """Test PyProj transformer creation and behavior"""

    logger.info("🔬 PYPROJ BEHAVIOR TEST")
    logger.info("=" * 50)

    # Create CRS objects
    logger.info("📐 Creating CRS objects...")
    wgs84 = CRS.from_epsg(4326)
    utm_13n = CRS.from_epsg(32613)

    logger.info(f"WGS84 CRS: {wgs84}")
    logger.info(f"UTM 13N CRS: {utm_13n}")

    # Test transformer creation both ways
    logger.info("\n🔄 Testing transformer creation...")

    # Method 1: UTM -> WGS84
    logger.info("Method 1: Transformer.from_crs(utm_crs, wgs84_crs)")
    transformer_utm_to_wgs84 = Transformer.from_crs(utm_13n, wgs84, always_xy=False)
    logger.info(f"  Source CRS: {transformer_utm_to_wgs84.source_crs}")
    logger.info(f"  Target CRS: {transformer_utm_to_wgs84.target_crs}")

    # Method 2: WGS84 -> UTM
    logger.info("Method 2: Transformer.from_crs(wgs84_crs, utm_crs)")
    transformer_wgs84_to_utm = Transformer.from_crs(wgs84, utm_13n, always_xy=False)
    logger.info(f"  Source CRS: {transformer_wgs84_to_utm.source_crs}")
    logger.info(f"  Target CRS: {transformer_wgs84_to_utm.target_crs}")

    # Test transformations with known coordinates
    logger.info("\n🧮 Testing transformations...")

    # Test coordinates
    wyoming_lat, wyoming_lon = 41.0, -105.0  # Wyoming coordinates
    wyoming_easting, wyoming_northing = 500000, 4500000  # Approximate UTM for Wyoming

    logger.info(f"Test coordinates:")
    logger.info(f"  Geographic: ({wyoming_lat}, {wyoming_lon})")
    logger.info(f"  UTM: ({wyoming_easting}, {wyoming_northing})")

    # Test UTM -> WGS84
    logger.info("\nTesting UTM -> WGS84 transformation:")
    try:
        result_geo = transformer_utm_to_wgs84.transform(wyoming_easting, wyoming_northing)
        logger.info(f"  Result: {result_geo}")
        logger.info(f"  Expected: ~({wyoming_lat}, {wyoming_lon})")
        logger.info(f"  Success: {abs(result_geo[0] - wyoming_lat) < 1 and abs(result_geo[1] - wyoming_lon) < 1}")
    except Exception as e:
        logger.error(f"  Failed: {e}")

    # Test WGS84 -> UTM
    logger.info("\nTesting WGS84 -> UTM transformation:")
    try:
        result_utm = transformer_wgs84_to_utm.transform(wyoming_lon, wyoming_lat)
        logger.info(f"  Result: {result_utm}")
        logger.info(f"  Expected: ~({wyoming_easting}, {wyoming_northing})")
        logger.info(f"  Success: {abs(result_utm[0] - wyoming_easting) < 10000 and abs(result_utm[1] - wyoming_northing) < 10000}")
    except Exception as e:
        logger.error(f"  Failed: {e}")

    # Test the actual issue: what happens with our transformer creation in the app?
    logger.info("\n🔍 INVESTIGATING APPLICATION ISSUE:")

    # Recreate the exact same CRS objects as in our application
    app_wgs84 = CRS.from_epsg(4326)
    app_utm_epsg = 32613  # Zone 13N
    app_utm_crs = CRS.from_epsg(app_utm_epsg)

    logger.info("Application-style CRS creation:")
    logger.info(f"  WGS84: {app_wgs84}")
    logger.info(f"  UTM: {app_utm_crs}")

    # Create transformer exactly as in our application
    app_transformer = Transformer.from_crs(app_utm_crs, app_wgs84, always_xy=False)
    logger.info("Application-style transformer:")
    logger.info(f"  Source: {app_transformer.source_crs}")
    logger.info(f"  Target: {app_transformer.target_crs}")

    # Test with application coordinates
    logger.info("Testing with application coordinates:")
    try:
        app_result = app_transformer.transform(433873.421, 4562910.166)
        logger.info(f"  Application coordinates result: {app_result}")
    except Exception as e:
        logger.error(f"  Application test failed: {e}")

    # Test with the actual coordinates from our logs
    logger.info("\nTesting actual problem coordinates:")
    actual_easting, actual_northing = 433873.421, 4562910.166

    logger.info(f"Actual UTM coordinates: ({actual_easting}, {actual_northing})")

    try:
        actual_result = transformer_utm_to_wgs84.transform(actual_easting, actual_northing)
        logger.info(f"  UTM->WGS84 result: {actual_result}")
    except Exception as e:
        logger.error(f"  UTM->WGS84 failed: {e}")

    try:
        actual_result_reverse = transformer_wgs84_to_utm.transform(actual_easting, actual_northing)
        logger.info(f"  WGS84->UTM result (using UTM coords as geo): {actual_result_reverse}")
    except Exception as e:
        logger.error(f"  WGS84->UTM failed: {e}")

if __name__ == "__main__":
    test_pyproj_behavior()
