"""Advisory evidence-locality evaluators for prompt observability.

Inspects structural locator geometry to detect when earned exact covered units
have only broad (low-resolution) evidence pointers.  All checks are mechanical
and advisory — the harness surfaces counts and flags; it does not reject work
or infer claim correctness.

Architecture note: keep this module focused on structural locator shape.
Domain-specific or media-specific evaluators belong in adapter/tooling layers,
not here.  New generic evaluators (e.g. text-span coverage) may be added as
additional public functions following the same ``count_*`` pattern.
"""

from __future__ import annotations

from typing import Any

# Conservative area threshold for "broad" image-region locators.
# If every image_region locator for an earned exact unit covers more than this
# fraction of the referenced image/crop, the unit is counted as broad-locator.
# 5 % is deliberately permissive — a true tight locator (single line, row, cell)
# will almost never exceed this.
BROAD_IMAGE_AREA_THRESHOLD: float = 0.05


def _str_attr(obj: Any, key: str) -> str:
    """Return a normalised lowercase string for an attribute/key, or empty string."""
    val = getattr(obj, key, None) if not isinstance(obj, dict) else obj.get(key)
    return str(val or "").strip().lower()


def _get_attr(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def box_norm_area(box_norm: list[float] | tuple[float, ...]) -> float:
    """Return the fractional area of a normalised bounding box [x_min, y_min, x_max, y_max].

    Returns 1.0 (worst case / maximally broad) if the geometry is invalid or absent.
    """
    try:
        if len(box_norm) != 4:
            return 1.0
        x_min, y_min, x_max, y_max = box_norm
        width = max(0.0, float(x_max) - float(x_min))
        height = max(0.0, float(y_max) - float(y_min))
        return width * height
    except (TypeError, ValueError):
        return 1.0


def is_broad_image_locator(
    locator: Any,
    *,
    area_threshold: float = BROAD_IMAGE_AREA_THRESHOLD,
) -> bool:
    """True when *locator* is an image_region with area > area_threshold.

    An ``image_region`` locator without a ``box_norm`` is treated as maximally
    broad (area = 1.0).  Non-image-region locators always return False; only
    image geometry is evaluated here.
    """
    if _str_attr(locator, "locator_kind") != "image_region":
        return False
    box_norm = _get_attr(locator, "box_norm")
    if box_norm is None:
        return True  # image_region with no box covers the whole image
    try:
        area = box_norm_area(box_norm)
    except Exception:
        return True  # invalid geometry → treat as broad
    return area > area_threshold


def _is_earned_exact_unit(unit: Any) -> bool:
    """True when unit is earned/closed with a compact determined_value.

    Excludes broad/group rows that lack a determined_value.
    """
    determined_value = _get_attr(unit, "determined_value")
    if not (isinstance(determined_value, str) and determined_value.strip()):
        return False
    status = _str_attr(unit, "status")
    determination = _str_attr(unit, "determination")
    return status == "closed" or determination == "earned"


def count_earned_exact_units_with_broad_image_locator(
    items: list[Any],
    *,
    area_threshold: float = BROAD_IMAGE_AREA_THRESHOLD,
) -> int:
    """Count earned/exact covered units where all image-region locators are broad.

    A unit is counted when:
    - It is earned/closed with a non-empty ``determined_value``
    - It has at least one ``image_region`` locator
    - None of its image-region locators is sufficiently tight
      (i.e. area <= *area_threshold*)

    Not counted:
    - Units without a ``determined_value`` (broad/group rows)
    - Units with no locators (a separate debt: ``earned_unit_missing_locator``)
    - Units with at least one tight image-region locator
    - Units whose locators are all non-image-region kinds (those are a different
      medium and not evaluated here)

    Advisory only — does not invalidate work or block completion.
    """
    count = 0
    for item in items:
        units = _get_attr(item, "covered_units") or []
        for unit in units:
            if not _is_earned_exact_unit(unit):
                continue
            locators = list(_get_attr(unit, "evidence_locators") or [])
            if not locators:
                continue  # Missing locator → different advisory flag

            # Filter to image_region locators only.
            image_locators = [
                loc for loc in locators
                if _str_attr(loc, "locator_kind") == "image_region"
            ]
            if not image_locators:
                continue  # No image locators → not evaluated here

            # Count when NO image locator is tight.
            has_tight = any(
                not is_broad_image_locator(loc, area_threshold=area_threshold)
                for loc in image_locators
            )
            if not has_tight:
                count += 1
    return count
