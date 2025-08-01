"""
Tile Providers
Configuration for various map tile providers
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class TileProviders:
    """
    Manages configuration for different map tile providers
    """
    
    def __init__(self):
        """Initialize tile providers"""
        self.providers = self._initialize_providers()
    
    def _initialize_providers(self) -> Dict[str, dict]:
        """Initialize provider configurations"""
        return {
            "usgs_topo": {
                "name": "USGS Topographic",
                "description": "USGS topographic maps",
                "url_template": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}",
                "attribution": "USGS",
                "tile_size": 256,
                "min_zoom": 1,
                "max_zoom": 16,
                "format": "png",
                "user_agent": "Plattera/1.0 (USGS Topo)",
                "headers": {}
            },
            
            "usgs_imagery": {
                "name": "USGS Imagery",
                "description": "USGS aerial imagery",
                "url_template": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
                "attribution": "USGS",
                "tile_size": 256,
                "min_zoom": 1,
                "max_zoom": 18,
                "format": "png",
                "user_agent": "Plattera/1.0 (USGS Imagery)",
                "headers": {}
            },
            
            "osm_standard": {
                "name": "OpenStreetMap Standard",
                "description": "Standard OpenStreetMap tiles",
                "url_template": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                "subdomains": ["a", "b", "c"],
                "attribution": "© OpenStreetMap contributors",
                "tile_size": 256,
                "min_zoom": 1,
                "max_zoom": 19,
                "format": "png",
                "user_agent": "Plattera/1.0 (OSM Standard)",
                "headers": {}
            },
            
            "esri_world_topo": {
                "name": "Esri World Topographic",
                "description": "Esri world topographic map",
                "url_template": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
                "attribution": "Esri, DeLorme, NAVTEQ, TomTom, Intermap, iPC, USGS, FAO, NPS, NRCAN, GeoBase, Kadaster NL, Ordnance Survey, Esri Japan, METI, Esri China (Hong Kong), and the GIS User Community",
                "tile_size": 256,
                "min_zoom": 1,
                "max_zoom": 19,
                "format": "png",
                "user_agent": "Plattera/1.0 (Esri Topo)",
                "headers": {}
            },
            
            "esri_world_imagery": {
                "name": "Esri World Imagery",
                "description": "Esri world imagery (satellite)",
                "url_template": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                "attribution": "Esri, DigitalGlobe, GeoEye, Earthstar Geographics, CNES/Airbus DS, USDA, USGS, AeroGRID, IGN, and the GIS User Community",
                "tile_size": 256,
                "min_zoom": 1,
                "max_zoom": 19,
                "format": "png",
                "user_agent": "Plattera/1.0 (Esri Imagery)",
                "headers": {}
            }
        }
    
    def get_provider_config(self, provider_name: str) -> dict:
        """
        Get configuration for specific provider
        
        Args:
            provider_name: Name of the tile provider
            
        Returns:
            dict: Provider configuration or error
        """
        if provider_name not in self.providers:
            return {
                "success": False,
                "error": f"Unknown provider: {provider_name}"
            }
        
        return {
            "success": True,
            "config": self.providers[provider_name]
        }
    
    def get_available_providers(self) -> List[str]:
        """Get list of available provider names"""
        return list(self.providers.keys())
    
    def get_provider_info(self, provider_name: str) -> dict:
        """Get detailed information about a provider"""
        if provider_name not in self.providers:
            return {
                "success": False,
                "error": f"Unknown provider: {provider_name}"
            }
        
        provider = self.providers[provider_name]
        return {
            "success": True,
            "info": {
                "name": provider["name"],
                "description": provider["description"],
                "attribution": provider["attribution"],
                "tile_size": provider["tile_size"],
                "min_zoom": provider["min_zoom"],
                "max_zoom": provider["max_zoom"],
                "format": provider["format"]
            }
        }
    
    def get_all_providers_info(self) -> dict:
        """Get information about all available providers"""
        providers_info = {}
        for provider_name in self.providers:
            info_result = self.get_provider_info(provider_name)
            if info_result["success"]:
                providers_info[provider_name] = info_result["info"]
        
        return {
            "success": True,
            "providers": providers_info
        }
    
    def add_custom_provider(self, provider_name: str, config: dict) -> dict:
        """
        Add a custom tile provider
        
        Args:
            provider_name: Unique name for the provider
            config: Provider configuration
            
        Returns:
            dict: Success/error result
        """
        try:
            # Validate required config fields
            required_fields = ["name", "url_template", "attribution", "tile_size"]
            for field in required_fields:
                if field not in config:
                    return {
                        "success": False,
                        "error": f"Missing required field: {field}"
                    }
            
            # Set defaults for optional fields
            config.setdefault("min_zoom", 1)
            config.setdefault("max_zoom", 18)
            config.setdefault("format", "png")
            config.setdefault("user_agent", f"Plattera/1.0 ({config['name']})")
            config.setdefault("headers", {})
            
            # Add to providers
            self.providers[provider_name] = config
            
            logger.info(f"✅ Added custom provider: {provider_name}")
            return {
                "success": True,
                "message": f"Provider '{provider_name}' added successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to add provider: {str(e)}"
            }
    
    def remove_provider(self, provider_name: str) -> dict:
        """Remove a provider (only works for custom providers)"""
        if provider_name not in self.providers:
            return {
                "success": False,
                "error": f"Provider '{provider_name}' does not exist"
            }
        
        # Prevent removal of built-in providers
        built_in_providers = [
            "usgs_topo", "usgs_imagery", "osm_standard", 
            "esri_world_topo", "esri_world_imagery"
        ]
        
        if provider_name in built_in_providers:
            return {
                "success": False,
                "error": f"Cannot remove built-in provider: {provider_name}"
            }
        
        del self.providers[provider_name]
        logger.info(f"🗑️ Removed provider: {provider_name}")
        
        return {
            "success": True,
            "message": f"Provider '{provider_name}' removed successfully"
        }