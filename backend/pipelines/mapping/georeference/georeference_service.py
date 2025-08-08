"""
Georeference Service
Small orchestrator that uses POBResolver to generate geographic polygon and metadata.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from .pob_resolver import POBResolver
from pipelines.mapping.projection.pipeline import ProjectionPipeline


class GeoreferenceService:
    def __init__(self) -> None:
        self.resolver = POBResolver()
        self.projection = ProjectionPipeline()

    def project(self, request: Dict[str, Any]) -> Dict[str, Any]:
        local = request.get("local_coordinates") or []
        plss_anchor = request.get("plss_anchor") or {}
        starting_point = request.get("starting_point") or {}
        tie = starting_point.get("tie_to_corner") or {}
        # Pass through raw_text from starting_point so we can detect 'whence ... bears ... distant'
        if starting_point.get("raw_text") and "raw_text" not in tie:
            tie["raw_text"] = starting_point.get("raw_text")

        if not local or len(local) < 3:
            return {"success": False, "error": "At least 3 local coordinates required"}

        res = self.resolver.resolve_pob_and_vertices(local, plss_anchor, tie)
        if not res.get("success"):
            return res

        utm_zone = res["utm_zone"]
        geo_ring: List[Tuple[float, float]] = []
        for ux, uy in res["utm_vertices"]:
            to_geo = self.projection.transformer.utm_to_geographic(ux, uy, utm_zone)
            if not to_geo.get("success"):
                return {"success": False, "error": f"Vertex transform failed: {to_geo.get('error')}"}
            geo_ring.append((to_geo["lon"], to_geo["lat"]))

        pob_geo = None
        pob_geo_res = self.projection.transformer.utm_to_geographic(res["pob_utm"]["x"], res["pob_utm"]["y"], utm_zone)
        if pob_geo_res.get("success"):
            pob_geo = {"lat": pob_geo_res["lat"], "lon": pob_geo_res["lon"]}

        lons = [p[0] for p in geo_ring]
        lats = [p[1] for p in geo_ring]
        bounds = {
            "min_lon": min(lons),
            "max_lon": max(lons),
            "min_lat": min(lats),
            "max_lat": max(lats),
        }

        plss_ref = (
            f"T{plss_anchor.get('township_number')}{plss_anchor.get('township_direction')} "
            f"R{plss_anchor.get('range_number')}{plss_anchor.get('range_direction')} "
            f"Sec {plss_anchor.get('section_number')}"
        )

        return {
            "success": True,
            "geographic_polygon": {"type": "Polygon", "coordinates": [geo_ring], "bounds": bounds},
            "anchor_info": {
                "plss_reference": plss_ref,
                "resolved_coordinates": {"lat": res["anchor_geo"]["lat"], "lon": res["anchor_geo"]["lon"]},
                **({"pob_coordinates": pob_geo} if pob_geo else {}),
            },
            "projection_metadata": {"utm_zone": utm_zone, "vertex_count": len(geo_ring)},
            **({"debug": res.get("debug")} if res.get("debug") else {}),
        }


