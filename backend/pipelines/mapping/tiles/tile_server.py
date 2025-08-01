"""
Tile Server
Handles fetching tiles from remote tile servers
"""
import logging
import urllib.request
import urllib.error
from typing import Dict, Any
import time

logger = logging.getLogger(__name__)

class TileServer:
    """
    Fetches map tiles from remote tile servers
    """
    
    def __init__(self):
        """Initialize tile server"""
        self.request_timeout = 30  # 30 second timeout
        self.retry_count = 3
        self.retry_delay = 1  # 1 second between retries
        
    def fetch_tile(self, x: int, y: int, z: int, provider_config: dict) -> dict:
        """
        Fetch a single tile from remote server
        
        Args:
            x: Tile X coordinate
            y: Tile Y coordinate  
            z: Zoom level
            provider_config: Provider configuration with URL template
            
        Returns:
            dict: Result with tile data or error
        """
        try:
            # Build tile URL from template
            tile_url = self._build_tile_url(x, y, z, provider_config)
            logger.debug(f"🌐 Fetching tile: {tile_url}")
            
            # Fetch with retries
            for attempt in range(self.retry_count):
                try:
                    fetch_result = self._fetch_tile_data(tile_url, provider_config)
                    if fetch_result["success"]:
                        return {
                            "success": True,
                            "tile_data": fetch_result["data"],
                            "remote_url": tile_url,
                            "size_bytes": len(fetch_result["data"]),
                            "attempt": attempt + 1
                        }
                    
                    # If not last attempt, wait and retry
                    if attempt < self.retry_count - 1:
                        logger.warning(f"⏳ Tile fetch attempt {attempt + 1} failed, retrying...")
                        time.sleep(self.retry_delay)
                    
                except Exception as e:
                    if attempt < self.retry_count - 1:
                        logger.warning(f"⏳ Tile fetch attempt {attempt + 1} error: {str(e)}, retrying...")
                        time.sleep(self.retry_delay)
                    else:
                        raise e
            
            return {
                "success": False,
                "error": f"Failed to fetch tile after {self.retry_count} attempts"
            }
            
        except Exception as e:
            logger.error(f"❌ Tile fetch error: {str(e)}")
            return {
                "success": False,
                "error": f"Tile fetch error: {str(e)}"
            }
    
    def _build_tile_url(self, x: int, y: int, z: int, provider_config: dict) -> str:
        """Build tile URL from provider template"""
        url_template = provider_config["url_template"]
        
        # Replace placeholders
        tile_url = url_template.replace("{x}", str(x))
        tile_url = tile_url.replace("{y}", str(y))
        tile_url = tile_url.replace("{z}", str(z))
        
        # Handle subdomains if specified
        if "{s}" in tile_url and "subdomains" in provider_config:
            subdomain = provider_config["subdomains"][x % len(provider_config["subdomains"])]
            tile_url = tile_url.replace("{s}", subdomain)
        
        return tile_url
    
    def _fetch_tile_data(self, url: str, provider_config: dict) -> dict:
        """Fetch raw tile data from URL"""
        try:
            # Create request with headers
            request = urllib.request.Request(url)
            
            # Add user agent
            user_agent = provider_config.get("user_agent", "Plattera/1.0 (Mapping Application)")
            request.add_header("User-Agent", user_agent)
            
            # Add any custom headers
            if "headers" in provider_config:
                for header_name, header_value in provider_config["headers"].items():
                    request.add_header(header_name, header_value)
            
            # Fetch data
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                if response.status == 200:
                    tile_data = response.read()
                    
                    # Validate response is actually image data
                    if len(tile_data) < 100:  # Too small to be valid image
                        return {
                            "success": False,
                            "error": "Response too small to be valid tile"
                        }
                    
                    # Check for common image headers
                    if not (tile_data.startswith(b'\x89PNG') or  # PNG
                           tile_data.startswith(b'\xff\xd8\xff') or  # JPEG
                           tile_data.startswith(b'GIF')):  # GIF
                        return {
                            "success": False,
                            "error": "Response does not appear to be valid image data"
                        }
                    
                    return {
                        "success": True,
                        "data": tile_data
                    }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: {response.reason}"
                    }
                    
        except urllib.error.HTTPError as e:
            return {
                "success": False,
                "error": f"HTTP error {e.code}: {e.reason}"
            }
        except urllib.error.URLError as e:
            return {
                "success": False,
                "error": f"URL error: {e.reason}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Fetch error: {str(e)}"
            }
    
    def test_provider_connection(self, provider_config: dict) -> dict:
        """Test connection to tile provider"""
        try:
            # Test with a standard tile (zoom 1, center of world)
            test_result = self.fetch_tile(1, 1, 1, provider_config)
            
            if test_result["success"]:
                return {
                    "success": True,
                    "message": "Provider connection successful",
                    "response_size": test_result["size_bytes"]
                }
            else:
                return {
                    "success": False,
                    "error": f"Provider test failed: {test_result['error']}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Provider test error: {str(e)}"
            }