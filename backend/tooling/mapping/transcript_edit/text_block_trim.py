"""Deterministic x-axis text-block trimming for span-line point crops.

Detects ink density in a horizontal band — not OCR or semantic text analysis.
Fails soft when no substantial dark-pixel run is found.
"""

from __future__ import annotations

from typing import Any

TRIM_METHOD = "dark_pixel_column_density_v1"
DEFAULT_TRIM_PADDING_NORM = 0.02
ALLOWED_TRIM_AXES = frozenset({"x"})

# Ink detection: pixel is "dark" when below (median - offset).
_DARK_OFFSET = 28
# Column is "inky" when smoothed dark-pixel fraction exceeds this.
_MIN_COLUMN_DENSITY = 0.04
# Ignore runs narrower than this fraction of the pre-trim band width.
_MIN_RUN_WIDTH_FRAC = 0.08
# Trimmed box must be at least this fraction of pre-trim width (norm, full image).
_MIN_TRIM_WIDTH_FRAC_OF_PRETRIM = 0.25
# Absolute floor on trimmed width in normalized image coordinates.
_MIN_TRIM_WIDTH_NORM = 0.05
_SMOOTH_WINDOW_FRAC = 0.04
_SMOOTH_WINDOW_MIN = 3
_SMOOTH_WINDOW_MAX = 31


class TextBlockTrimResult:
    """Outcome of a single x-axis trim attempt."""

    __slots__ = (
        "trim_applied",
        "trim_warning",
        "pre_trim_box_norm",
        "box_norm",
        "text_block_bounds_norm",
    )

    def __init__(
        self,
        *,
        trim_applied: bool,
        pre_trim_box_norm: list[float],
        box_norm: list[float],
        trim_warning: str | None = None,
        text_block_bounds_norm: list[float] | None = None,
    ) -> None:
        self.trim_applied = trim_applied
        self.trim_warning = trim_warning
        self.pre_trim_box_norm = pre_trim_box_norm
        self.box_norm = box_norm
        self.text_block_bounds_norm = text_block_bounds_norm

    def as_metadata(self, *, trim_axis: str, trim_padding_norm: float) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "trim_to_text_block": True,
            "trim_axis": trim_axis,
            "trim_padding_norm": round(float(trim_padding_norm), 6),
            "trim_applied": self.trim_applied,
            "pre_trim_box_norm": list(self.pre_trim_box_norm),
            "box_norm": list(self.box_norm),
        }
        if self.trim_applied:
            meta["trim_method"] = TRIM_METHOD
            if self.text_block_bounds_norm is not None:
                meta["text_block_bounds_norm"] = list(self.text_block_bounds_norm)
        elif self.trim_warning:
            meta["trim_warning"] = self.trim_warning
        return meta


def trim_box_to_text_block(
    img: Any,
    *,
    box_norm: list[float],
    point_norm: list[float],
    trim_axis: str = "x",
    trim_padding_norm: float = DEFAULT_TRIM_PADDING_NORM,
) -> TextBlockTrimResult:
    """Trim ``box_norm`` along ``trim_axis`` using dark-pixel column density."""
    pre_trim = [_round6(v) for v in box_norm]
    if trim_axis != "x":
        return TextBlockTrimResult(
            trim_applied=False,
            pre_trim_box_norm=pre_trim,
            box_norm=pre_trim,
            trim_warning="unsupported_trim_axis",
        )

    img_w = int(img.width)
    img_h = int(img.height)
    if img_w < 2 or img_h < 2:
        return TextBlockTrimResult(
            trim_applied=False,
            pre_trim_box_norm=pre_trim,
            box_norm=pre_trim,
            trim_warning="text_block_not_detected",
        )

    x1n, y1n, x2n, y2n = (float(v) for v in pre_trim)
    left = max(0, min(img_w - 1, int(round(x1n * img_w))))
    top = max(0, min(img_h - 1, int(round(y1n * img_h))))
    right = max(left + 1, min(img_w, int(round(x2n * img_w))))
    bottom = max(top + 1, min(img_h, int(round(y2n * img_h))))
    band_w = right - left
    band_h = bottom - top
    if band_w < 4 or band_h < 2:
        return TextBlockTrimResult(
            trim_applied=False,
            pre_trim_box_norm=pre_trim,
            box_norm=pre_trim,
            trim_warning="text_block_not_detected",
        )

    gray = img.crop((left, top, right, bottom)).convert("L")
    pixels = gray.load()
    samples = [pixels[x, y] for x in range(band_w) for y in range(band_h)]
    median = _median_int(samples)
    dark_threshold = max(0, median - _DARK_OFFSET)

    densities = [
        sum(1 for y in range(band_h) if pixels[col, y] < dark_threshold) / band_h
        for col in range(band_w)
    ]
    window = max(
        _SMOOTH_WINDOW_MIN,
        min(_SMOOTH_WINDOW_MAX, int(round(band_w * _SMOOTH_WINDOW_FRAC)) | 1),
    )
    smoothed = _smooth(densities, window)
    if max(smoothed) < _MIN_COLUMN_DENSITY:
        return TextBlockTrimResult(
            trim_applied=False,
            pre_trim_box_norm=pre_trim,
            box_norm=pre_trim,
            trim_warning="text_block_not_detected",
        )

    min_run_cols = max(2, int(round(band_w * _MIN_RUN_WIDTH_FRAC)))
    runs = _find_runs(smoothed, _MIN_COLUMN_DENSITY, min_width=min_run_cols)
    if not runs:
        return TextBlockTrimResult(
            trim_applied=False,
            pre_trim_box_norm=pre_trim,
            box_norm=pre_trim,
            trim_warning="text_block_not_detected",
        )

    point_x_px = float(point_norm[0]) * img_w
    point_col = int(round(point_x_px - left))
    point_col = max(0, min(band_w - 1, point_col))
    selected = _select_run(runs, point_col)
    if selected is None:
        return TextBlockTrimResult(
            trim_applied=False,
            pre_trim_box_norm=pre_trim,
            box_norm=pre_trim,
            trim_warning="text_block_not_detected",
        )

    run_start, run_end = selected
    pad_px = trim_padding_norm * img_w
    new_left_px = left + run_start - pad_px
    new_right_px = left + run_end + 1 + pad_px

    pre_trim_width_norm = x2n - x1n
    min_width_px = max(
        _MIN_TRIM_WIDTH_NORM * img_w,
        pre_trim_width_norm * img_w * _MIN_TRIM_WIDTH_FRAC_OF_PRETRIM,
    )
    if new_right_px - new_left_px < min_width_px:
        center = (new_left_px + new_right_px) / 2.0
        half = min_width_px / 2.0
        new_left_px = center - half
        new_right_px = center + half

    new_left_px = max(0.0, new_left_px)
    new_right_px = min(float(img_w), new_right_px)
    if new_right_px - new_left_px < 2:
        return TextBlockTrimResult(
            trim_applied=False,
            pre_trim_box_norm=pre_trim,
            box_norm=pre_trim,
            trim_warning="text_block_not_detected",
        )

    new_box_norm = [
        _round6(new_left_px / img_w),
        _round6(y1n),
        _round6(new_right_px / img_w),
        _round6(y2n),
    ]
    text_bounds = [
        _round6((left + run_start) / img_w),
        _round6((left + run_end + 1) / img_w),
    ]
    if new_box_norm == pre_trim:
        return TextBlockTrimResult(
            trim_applied=False,
            pre_trim_box_norm=pre_trim,
            box_norm=pre_trim,
            trim_warning="text_block_not_detected",
        )

    return TextBlockTrimResult(
        trim_applied=True,
        pre_trim_box_norm=pre_trim,
        box_norm=new_box_norm,
        text_block_bounds_norm=text_bounds,
    )


def _round6(value: float) -> float:
    return round(float(value), 6)


def _median_int(values: list[int]) -> int:
    if not values:
        return 128
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return int(ordered[mid])
    return int((ordered[mid - 1] + ordered[mid]) / 2)


def _smooth(values: list[float], window: int) -> list[float]:
    if window <= 1 or len(values) <= 1:
        return list(values)
    half = window // 2
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def _find_runs(
    densities: list[float],
    min_density: float,
    *,
    min_width: int,
) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, density in enumerate(densities):
        if density >= min_density:
            if start is None:
                start = i
        elif start is not None:
            if i - start >= min_width:
                runs.append((start, i - 1))
            start = None
    if start is not None and len(densities) - start >= min_width:
        runs.append((start, len(densities) - 1))
    return runs


def _select_run(runs: list[tuple[int, int]], point_col: int) -> tuple[int, int] | None:
    containing = [run for run in runs if run[0] <= point_col <= run[1]]
    if containing:
        return max(containing, key=lambda run: run[1] - run[0])
    return min(
        runs,
        key=lambda run: _distance_to_run(point_col, run),
    )


def _distance_to_run(col: int, run: tuple[int, int]) -> int:
    start, end = run
    if col < start:
        return start - col
    if col > end:
        return col - end
    return 0
