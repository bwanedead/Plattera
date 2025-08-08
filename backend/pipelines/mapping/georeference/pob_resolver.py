"""
POB Resolver
Resolves POB in UTM from PLSS corner + tie, and produces UTM vertices from local coords.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
import logging

from pipelines.mapping.projection.pipeline import ProjectionPipeline
from pipelines.mapping.plss.pipeline import PLSSPipeline
from pipelines.mapping.common.units import FEET_TO_METERS
from .pob_math import (
    flip_display_to_survey,
    normalize_local,
    parse_tie_with_azimuth,
    parse_corner_plss,
)

logger = logging.getLogger(__name__)


class POBResolver:
    def __init__(self, plss: PLSSPipeline | None = None, projection: ProjectionPipeline | None = None) -> None:
        self.plss = plss or PLSSPipeline()
        self.projection = projection or ProjectionPipeline()

    def resolve_pob_and_vertices(
        self,
        local_display_coords: List[Dict[str, float] | Tuple[float, float]],
        plss_anchor: Dict[str, Any],
        tie_to_corner: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        """
        - Choose anchor at requested section corner if provided, else centroid resolution
        - Compute POB in UTM by applying tie vector (feet->meters) from anchor
        - Convert local display coords to survey frame, normalize to start at (0,0)
        - Build UTM vertices at POB origin
        """
        corner_label = ((tie_to_corner or {}).get("corner_label") or "").strip()
        # If the corner label encodes its own TRS (e.g., R74W), override for the corner query
        override_plss = parse_corner_plss(corner_label) if corner_label else None
        plss_for_corner = dict(plss_anchor)
        if override_plss:
            plss_for_corner.update(override_plss)

        anchor_geo: Dict[str, float]
        if corner_label:
            corner_res = self.plss.get_section_corner(plss_for_corner, corner_label)
            if corner_res.get("success"):
                anchor_geo = corner_res["corner"]
                logger.info(
                    f"Using PLSS corner '{corner_label}' at {anchor_geo['lat']:.6f},{anchor_geo['lon']:.6f}"
                )
            else:
                logger.warning(
                    f"Corner '{corner_label}' resolution failed: {corner_res.get('error')}. Falling back to centroid."
                )
                resolved = self.plss.resolve_starting_point(plss_anchor)
                if not resolved.get("success"):
                    return {"success": False, "error": f"PLSS resolution failed: {resolved.get('error')}"}
                anchor_geo = resolved["coordinates"]
        else:
            resolved = self.plss.resolve_starting_point(plss_anchor)
            if not resolved.get("success"):
                return {"success": False, "error": f"PLSS resolution failed: {resolved.get('error')}"}
            anchor_geo = resolved["coordinates"]

        utm_zone = self.projection.utm_manager.get_utm_zone(anchor_geo["lat"], anchor_geo["lon"])
        anchor_utm = self.projection.transformer.geographic_to_utm(
            anchor_geo["lat"], anchor_geo["lon"], utm_zone
        )
        if not anchor_utm.get("success"):
            return {"success": False, "error": f"UTM transform failed: {anchor_utm.get('error')}"}

        # Parse tie and auto-apply reciprocal if deed phrasing indicates corner is bearing FROM POB
        tie_dx_ft, tie_dy_ft, az_used, recip = parse_tie_with_azimuth(tie_to_corner or {})
        invert_tie_y = bool((tie_to_corner or {}).get("debug_invert_tie_y", False))
        skip_normalize = bool((tie_to_corner or {}).get("debug_skip_normalize", False))
        if invert_tie_y:
            tie_dy_ft = -tie_dy_ft
        pob_utm_x = anchor_utm["utm_x"] + tie_dx_ft * FEET_TO_METERS
        pob_utm_y = anchor_utm["utm_y"] + tie_dy_ft * FEET_TO_METERS

        survey_feet = flip_display_to_survey(local_display_coords)
        if survey_feet and survey_feet[0] != survey_feet[-1]:
            survey_feet = survey_feet + [survey_feet[0]]
        normalized_feet = survey_feet if skip_normalize else normalize_local(survey_feet)

        utm_vertices: List[Tuple[float, float]] = [
            (pob_utm_x + x_ft * FEET_TO_METERS, pob_utm_y + y_ft * FEET_TO_METERS) for (x_ft, y_ft) in normalized_feet
        ]

        return {
            "success": True,
            "utm_zone": utm_zone,
            "pob_utm": {"x": pob_utm_x, "y": pob_utm_y},
            "anchor_geo": anchor_geo,
            "utm_vertices": utm_vertices,
            "debug": {
                "tie_dx_ft": tie_dx_ft,
                "tie_dy_ft": tie_dy_ft,
                "tie_azimuth_deg": az_used,
                "reciprocal_applied": recip,
                "invert_tie_y": invert_tie_y,
                "skip_normalize": skip_normalize,
                **({"corner_debug": corner_res.get("debug")} if corner_label and corner_res.get("debug") else {}),
            }
        }


