"""
PLSS Nearest Snap Engine
Ultra-fast spatial queries for finding nearest PLSS features
Uses parquet data and spatial indexing for optimal performance
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import numpy as np
from math import radians, sin, cos, sqrt, atan2

logger = logging.getLogger(__name__)

class PLSSNearestSnapEngine:
    """
    High-performance PLSS nearest feature finder
    Uses hierarchical search: Township → Range → Section → Quarter Section
    """

    def __init__(self, data_dir: str = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            # Navigate from backend/pipelines/mapping/plss/ to project root
            project_root = Path(__file__).parent.parent.parent.parent.parent
            self.data_dir = project_root / "plss"

        # Verify the data directory exists
        if not self.data_dir.exists():
            logger.warning(f"PLSS data directory does not exist: {self.data_dir}")

        # Search radii in degrees (convert from miles)
        self.search_radii = {
            'township': 5.0 / 69.0,    # ~5 miles
            'range': 2.0 / 69.0,      # ~2 miles
            'section': 1.0 / 69.0,    # ~1 mile
            'quarter': 0.5 / 69.0,    # ~0.5 miles
        }

        # Cache for loaded parquet data
        self._parquet_cache = {}

    def find_nearest_plss(
        self,
        latitude: float,
        longitude: float,
        state: str = "Wyoming",
        search_radius_miles: float = 1.0
    ) -> Dict[str, Any]:
        """
        Find the nearest PLSS feature to given coordinates

        Args:
            latitude: Target latitude
            longitude: Target longitude
            state: State name (e.g., "Wyoming")
            search_radius_miles: Search radius in miles

        Returns:
            Dict with nearest PLSS feature info or error
        """
        try:
            logger.info(".6f")

            # Convert search radius to degrees
            search_radius_deg = search_radius_miles / 69.0

            # Hierarchical search: Sections first (most common), then townships/ranges
            nearest_result = self._find_nearest_section(latitude, longitude, state, search_radius_deg)

            if nearest_result:
                distance_miles = self._haversine_distance(
                    latitude, longitude,
                    nearest_result['latitude'], nearest_result['longitude']
                )

                logger.info(".6f")
                return {
                    "success": True,
                    "longitude": nearest_result['longitude'],
                    "latitude": nearest_result['latitude'],
                    "plss_reference": nearest_result['plss_reference'],
                    "township": nearest_result.get('township'),
                    "township_direction": nearest_result.get('township_direction'),
                    "range_number": nearest_result.get('range_number'),
                    "range_direction": nearest_result.get('range_direction'),
                    "section": nearest_result.get('section'),
                    "quarter_sections": nearest_result.get('quarter_sections'),
                    "distance_miles": distance_miles,
                    "method": "parquet_query"
                }

            # Fallback to township search if no sections found
            logger.info("No nearby sections found, trying township search...")
            nearest_result = self._find_nearest_township(latitude, longitude, state, search_radius_deg)

            if nearest_result:
                distance_miles = self._haversine_distance(
                    latitude, longitude,
                    nearest_result['latitude'], nearest_result['longitude']
                )

                logger.info(".6f")
                return {
                    "success": True,
                    "longitude": nearest_result['longitude'],
                    "latitude": nearest_result['latitude'],
                    "plss_reference": nearest_result['plss_reference'],
                    "township": nearest_result.get('township'),
                    "township_direction": nearest_result.get('township_direction'),
                    "range_number": nearest_result.get('range_number'),
                    "range_direction": nearest_result.get('range_direction'),
                    "distance_miles": distance_miles,
                    "method": "township_fallback"
                }

            return {
                "success": False,
                "error": f"No PLSS features found within {search_radius_miles} miles of {latitude:.6f}, {longitude:.6f}",
                "search_location": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "state": state,
                    "search_radius_miles": search_radius_miles
                }
            }

        except Exception as e:
            import traceback
            logger.error(f"PLSS nearest snap failed: {e}\n{traceback.format_exc()}")
            return {
                "success": False,
                "error": f"Failed to find nearest PLSS feature: {str(e)}"
            }

    def _find_nearest_section(
        self,
        latitude: float,
        longitude: float,
        state: str,
        search_radius_deg: float
    ) -> Optional[Dict[str, Any]]:
        """Find nearest section using parquet data"""
        try:
            # Load sections parquet
            sections_df = self._load_parquet_data(state, 'sections')
            if sections_df is None or sections_df.empty:
                return None

            # Calculate distances to all sections
            distances = self._calculate_distances_vectorized(
                latitude, longitude, sections_df
            )

            # Find the closest section within search radius
            min_idx = np.argmin(distances)
            min_distance = distances[min_idx]

            if min_distance <= search_radius_deg:
                row = sections_df.iloc[min_idx]

                # Build PLSS reference
                plss_ref = ".0f"

                return {
                    'latitude': float(row['CENTROID_LAT']),
                    'longitude': float(row['CENTROID_LON']),
                    'township': int(row['TWNSHPNO']),
                    'township_direction': str(row['TWNSHPDIR']).upper(),
                    'range_number': int(row['RANGENO']),
                    'range_direction': str(row['RANGEDIR']).upper(),
                    'section': int(row['FRSTDIVNO']),
                    'plss_reference': plss_ref
                }

        except Exception as e:
            logger.warning(f"Section search failed: {e}")

        return None

    def _find_nearest_township(
        self,
        latitude: float,
        longitude: float,
        state: str,
        search_radius_deg: float
    ) -> Optional[Dict[str, Any]]:
        """Find nearest township centroid as fallback"""
        try:
            # Load townships parquet
            townships_df = self._load_parquet_data(state, 'townships')
            if townships_df is None or townships_df.empty:
                return None

            # Calculate distances to all townships
            distances = self._calculate_distances_vectorized(
                latitude, longitude, townships_df
            )

            # Find the closest township within search radius
            min_idx = np.argmin(distances)
            min_distance = distances[min_idx]

            if min_distance <= search_radius_deg:
                row = townships_df.iloc[min_idx]

                # Build PLSS reference
                plss_ref = ".0f"

                return {
                    'latitude': float(row['CENTROID_LAT']),
                    'longitude': float(row['CENTROID_LON']),
                    'township': int(row['TWNSHPNO']),
                    'township_direction': str(row['TWNSHPDIR']).upper(),
                    'range_number': int(row['RANGENO']),
                    'range_direction': str(row['RANGEDIR']).upper(),
                    'plss_reference': plss_ref
                }

        except Exception as e:
            logger.warning(f"Township search failed: {e}")

        return None

    def _load_parquet_data(self, state: str, layer: str) -> Optional[pd.DataFrame]:
        """Load parquet data with caching"""
        cache_key = f"{state}_{layer}"

        if cache_key in self._parquet_cache:
            return self._parquet_cache[cache_key]

        try:
            import geopandas as gpd

            parquet_path = self.data_dir / state.lower() / "parquet" / f"{layer}.parquet"

            if not parquet_path.exists():
                logger.debug(f"Parquet file not found: {parquet_path}")
                return None

            # Load parquet data
            gdf = gpd.read_parquet(parquet_path)

            # Convert to regular DataFrame with centroid coordinates
            if 'geometry' in gdf.columns:
                gdf['CENTROID_LAT'] = gdf.geometry.centroid.y
                gdf['CENTROID_LON'] = gdf.geometry.centroid.x

            # Cache the data
            self._parquet_cache[cache_key] = gdf

            logger.debug(f"Loaded {len(gdf)} {layer} features from parquet")
            return gdf

        except ImportError:
            logger.error("GeoPandas not available for parquet queries")
        except Exception as e:
            logger.warning(f"Failed to load parquet data for {state}/{layer}: {e}")

        return None

    def _calculate_distances_vectorized(
        self,
        target_lat: float,
        target_lon: float,
        df: pd.DataFrame
    ) -> np.ndarray:
        """Calculate haversine distances to all points in DataFrame"""
        # Convert to radians
        lat1_rad = np.radians(target_lat)
        lon1_rad = np.radians(target_lon)
        lat2_rad = np.radians(df['CENTROID_LAT'].values)
        lon2_rad = np.radians(df['CENTROID_LON'].values)

        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = np.sin(dlat/2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))

        # Return distances in degrees (not miles, since we compare to search_radius_deg)
        return c

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate haversine distance between two points in miles"""
        R = 3959  # Earth's radius in miles

        lat1_rad, lon1_rad = radians(lat1), radians(lon1)
        lat2_rad, lon2_rad = radians(lat2), radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c
