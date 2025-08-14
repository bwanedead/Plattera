"""
PLSS Data Manager
Handles downloading, caching, and management of PLSS vector data

Bulk FGDB approach for Wyoming (stable, offline):
- Downloads statewide File Geodatabases (FGDB) for Townships, Sections (First Division), and Subdivisions
- Installs to plss/<state>/fgdb/
- Creates processed summary with FGDB layer references for consumers
"""
import logging
import threading
import os
import requests
import geopandas as gpd
import fiona
from pathlib import Path
from typing import Dict, Any, Optional, List
import json
import zipfile
import io
from datetime import datetime

logger = logging.getLogger(__name__)

class PLSSDataManager:
    """
    Manages PLSS vector data downloads from BLM CadNSDI and local caching
    """
    
    def __init__(self, data_directory: Optional[str] = None):
        """
        Initialize data manager
        
        Args:
            data_directory: Custom directory for PLSS data storage
        """
        if data_directory:
            self.data_dir = Path(data_directory)
        else:
            # Use project directory instead of hidden home directory
            # Navigate up from backend/pipelines/mapping/plss/ to project root
            project_root = Path(__file__).parent.parent.parent.parent.parent
            self.data_dir = project_root / "plss"
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.data_dir / "metadata.json"
        
        # BLM ArcGIS Hub FGDB endpoints for Wyoming
        # Townships (PLSS Township)
        self.wy_fgdb_townships_url = (
            "https://gbp-blm-egis.hub.arcgis.com/api/download/v1/items/94fc3c33aea845399966ca777ec71089/filegdb?layers=0"
        )
        # First Division (Sections)
        self.wy_fgdb_sections_url = (
            "https://gbp-blm-egis.hub.arcgis.com/api/download/v1/items/164a262d820540a4a956a0db169d14b5/filegdb?layers=1"
        )
        # Second/Third Division (quarters, QQ, gov lots)
        self.wy_fgdb_subdivisions_url = (
            "https://gbp-blm-egis.hub.arcgis.com/api/download/v1/items/f484aef3642d4756a352cf2b63d5009d/filegdb?layers=0"
        )
        
        # State abbreviations mapping  
        self.state_abbrevs = {
            "Wyoming": "WY", "Colorado": "CO", "Utah": "UT", "Montana": "MT",
            "New Mexico": "NM", "Idaho": "ID", "Nevada": "NV", "Arizona": "AZ",
            "California": "CA", "Oregon": "OR", "Washington": "WA", "Alaska": "AK",
            "North Dakota": "ND", "South Dakota": "SD", "Nebraska": "NE", "Kansas": "KS",
            "Oklahoma": "OK", "Arkansas": "AR", "Louisiana": "LA", "Mississippi": "MS",
            "Alabama": "AL", "Florida": "FL", "Wisconsin": "WI", "Minnesota": "MN",
            "Iowa": "IA", "Missouri": "MO", "Illinois": "IL", "Indiana": "IN",
            "Michigan": "MI", "Ohio": "OH"
        }
        
    def ensure_state_data(self, state: str) -> dict:
        """
        Ensure PLSS data is available for the specified state using BLM CadNSDI API
        
        Args:
            state: State name (e.g., "Wyoming", "Colorado")
            
        Returns:
            dict: Result with vector data path and metadata
        """
        try:
            logger.info(f"📦 Ensuring PLSS data for {state}")
            
            if state not in self.state_abbrevs:
                return {
                    "success": False,
                    "error": f"PLSS data not available for state: {state}"
                }
            
            state_abbr = self.state_abbrevs[state]
            state_dir = self.data_dir / state.lower()
            state_dir.mkdir(exist_ok=True)
            
            # Check if data already exists and is current
            if self._is_data_current(state):
                logger.info(f"✅ Using cached PLSS data for {state}")
                return self._load_cached_data(state)
            
            # If FGDB already exists locally but processed data is missing/outdated, rebuild without re-downloading
            fgdb_dir = (self.data_dir / state.lower() / "fgdb")
            if fgdb_dir.exists():
                logger.info(f"♻️ Rebuilding processed data for {state} from existing FGDB (no re-download)")
                processing_result = self._process_state_data(state)
                if processing_result.get("success"):
                    # Update metadata and return
                    self._update_metadata(state, state_abbr)
                    return self._load_cached_data(state)
                logger.warning(f"Processing from existing FGDB failed, falling back to download: {processing_result.get('error')}")

            # Download and cache data (Bulk FGDB for Wyoming)
            logger.info(f"⬇️ Downloading PLSS data for {state} (bulk FGDB)")
            download_result = self._download_state_data_bulk_fgdb(state, state_abbr)
            if not download_result["success"]:
                return download_result

            # Process and validate data
            processing_result = self._process_state_data(state)
            if not processing_result["success"]:
                return processing_result
            
            # Update metadata
            self._update_metadata(state, state_abbr)
            
            logger.info(f"✅ PLSS data ready for {state}")
            return self._load_cached_data(state)
            
        except Exception as e:
            logger.error(f"❌ Failed to ensure PLSS data for {state}: {str(e)}")
            return {
                "success": False,
                "error": f"Data management error: {str(e)}"
            }
    
    # ---- Progress & cancel helpers ----
    def _progress_path(self, state: str) -> Path:
        return (self.data_dir / state.lower()) / "download_progress.json"

    def _cancel_flag_path(self, state: str) -> Path:
        return (self.data_dir / state.lower()) / "cancel.flag"

    def _write_progress(self, state: str, progress: dict) -> None:
        try:
            p = self._progress_path(state)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, 'w') as f:
                json.dump(progress, f)
        except Exception:
            pass

    def get_progress(self, state: str) -> dict:
        try:
            p = self._progress_path(state)
            if not p.exists():
                return {"success": True, "stage": "idle"}
            with open(p, 'r') as f:
                data = json.load(f)
            return {"success": True, **data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def request_cancel(self, state: str) -> dict:
        try:
            flag = self._cancel_flag_path(state)
            flag.write_text("cancel")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def start_bulk_install_background(self, state: str) -> dict:
        try:
            if state not in self.state_abbrevs:
                return {"success": False, "error": f"Unsupported state: {state}"}
            # Clear previous cancel flag
            flag = self._cancel_flag_path(state)
            if flag.exists():
                try:
                    flag.unlink()
                except Exception:
                    pass
            # Start background thread
            t = threading.Thread(target=self.ensure_state_data, args=(state,), daemon=True)
            t.start()
            return {"success": True, "started": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _download_state_data_bulk_fgdb(self, state: str, state_abbr: str) -> dict:
        """Download and install statewide FGDBs for Wyoming."""
        try:
            if state != "Wyoming" or state_abbr != "WY":
                return {"success": False, "error": f"Bulk FGDB not configured for {state}"}

            base_dir = self.data_dir / state.lower()
            raw_dir = base_dir / "raw"
            fgdb_dir = base_dir / "fgdb"
            raw_dir.mkdir(parents=True, exist_ok=True)
            fgdb_dir.mkdir(parents=True, exist_ok=True)

            # Initialize progress file
            progress = {
                "stage": "initializing",
                "files": [],
                "overall": {"downloaded": 0, "total": 0, "percent": 0}
            }
            self._write_progress(state, progress)

            downloads = [
                (self.wy_fgdb_townships_url, raw_dir / "wy_townships_fgdb.zip"),
                (self.wy_fgdb_sections_url, raw_dir / "wy_sections_fgdb.zip"),
                (self.wy_fgdb_subdivisions_url, raw_dir / "wy_subdivisions_fgdb.zip"),
            ]

            # Pre-fetch content-lengths (may be inaccurate or zero; we'll correct dynamically on stream begin)
            sizes = []
            for url, _ in downloads:
                sizes.append(self._head_content_length(url) or 0)
            total_bytes = sum(sizes)
            progress["overall"]["total"] = total_bytes
            self._write_progress(state, progress)

            downloaded_cumulative = 0
            for (idx, (url, out_zip)) in enumerate(downloads):
                file_label = out_zip.name
                file_total = sizes[idx]
                # Cancellation check
                if self._cancel_flag_path(state).exists():
                    progress.update({"stage": "canceled"})
                    self._write_progress(state, progress)
                    if out_zip.exists():
                        try:
                            out_zip.unlink()
                        except Exception:
                            pass
                    return {"success": False, "error": "Canceled by user"}
                progress.update({"stage": f"downloading:{file_label}"})
                self._write_progress(state, progress)

                def on_prog(written_bytes: int):
                    # written_bytes includes resume offset + current file writes
                    per_file_downloaded = written_bytes
                    # Estimate overall downloaded
                    overall_downloaded = downloaded_cumulative + per_file_downloaded
                    # Keep percent below 100% during active download to avoid UI stall when HEAD is unreliable
                    est_total = total_bytes if total_bytes > 0 else (overall_downloaded + 1)
                    pct = int(overall_downloaded * 100 / est_total)
                    if pct >= 100:
                        pct = 99
                    self._write_progress(state, {
                        "stage": f"downloading:{file_label}",
                        "files": [{
                            "file": file_label,
                            "downloaded": int(per_file_downloaded),
                            "total": int(file_total)
                        }],
                        "overall": {"downloaded": int(overall_downloaded), "total": int(total_bytes), "percent": pct}
                    })

                # Allow dynamic correction of file size once streaming begins
                def on_begin(total_for_file: int, resume_bytes: int):
                    nonlocal file_total, total_bytes
                    if total_for_file and total_for_file > file_total:
                        delta = total_for_file - file_total
                        file_total = total_for_file
                        total_bytes += delta
                        self._write_progress(state, {
                            "stage": f"downloading:{file_label}",
                            "files": [{"file": file_label, "downloaded": int(resume_bytes), "total": int(file_total)}],
                            "overall": {"downloaded": int(downloaded_cumulative + resume_bytes), "total": int(total_bytes), "percent": min(99, int((downloaded_cumulative + resume_bytes) * 100 / (total_bytes or 1)))}
                        })

                ok = self._download_with_resume(
                    url,
                    out_zip,
                    total_size=file_total,
                    on_progress=on_prog,
                    cancel_flag=self._cancel_flag_path(state),
                    on_cancel=lambda: self._write_progress(state, {"stage": "canceled"}),
                    on_begin=on_begin,
                )
                if not ok:
                    return {"success": False, "error": f"Failed to download {url}"}
                downloaded_cumulative += file_total or out_zip.stat().st_size
                # Post-file progress write
                self._write_progress(state, {
                    "stage": f"downloaded:{file_label}",
                    "files": [{"file": file_label, "downloaded": int(file_total or out_zip.stat().st_size), "total": int(file_total)}],
                    "overall": {"downloaded": int(downloaded_cumulative), "total": int(total_bytes), "percent": min(99, int(downloaded_cumulative * 100 / total_bytes) if total_bytes else 99)}
                })
                # Cancellation check before unzip
                if self._cancel_flag_path(state).exists():
                    self._write_progress(state, {"stage": "canceled"})
                    return {"success": False, "error": "Canceled by user"}
                self._unzip_file(out_zip, fgdb_dir)

            # Validate FGDBs exist by opening layers (best-effort)
            self._write_progress(state, {"stage": "validating"})
            validation = self._validate_wy_fgdb_layers(fgdb_dir)
            if not validation["success"]:
                return validation
            self._write_progress(state, {"stage": "processing:prepare"})

            # Process and write manifest; then mark complete so UI can stop polling
            proc = self._process_state_data(state)
            if not proc.get("success"):
                return proc
            self._write_progress(state, {"stage": "complete"})

            return {"success": True, "installed": True, "fgdb_path": str(fgdb_dir)}
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _download_with_resume(self, url: str, dest: Path, chunk_size: int = 2 * 1024 * 1024, total_size: int | None = None, on_progress=None, cancel_flag: Path | None = None, on_cancel=None, on_begin=None) -> bool:
        """Download a file with HTTP Range resume support."""
        try:
            headers = {"User-Agent": "Plattera/1.0 (PLSS Bulk Installer)"}
            mode = "ab" if dest.exists() else "wb"
            resume_at = dest.stat().st_size if dest.exists() else 0
            if resume_at > 0:
                headers["Range"] = f"bytes={resume_at}-"
            with requests.get(url, headers=headers, stream=True, timeout=300) as r:
                if r.status_code in (200, 206):
                    # If server provides a reliable length, correct totals
                    try:
                        cl = r.headers.get('Content-Length') or r.headers.get('content-length')
                        if cl and on_begin:
                            on_begin(int(cl) + resume_at, resume_at)
                    except Exception:
                        pass
                    written = resume_at
                    with open(dest, mode) as f:
                        for chunk in r.iter_content(chunk_size=chunk_size):
                            if not chunk:
                                continue
                            if cancel_flag is not None and cancel_flag.exists():
                                # Cleanup partial file and return
                                try:
                                    f.flush()
                                    f.close()
                                except Exception:
                                    pass
                                try:
                                    dest.unlink()
                                except Exception:
                                    pass
                                if on_cancel:
                                    try:
                                        on_cancel()
                                    except Exception:
                                        pass
                                return False
                            f.write(chunk)
                            written += len(chunk)
                            if on_progress:
                                try:
                                    on_progress(written)
                                except Exception:
                                    pass
                    return True
                else:
                    logger.error(f"Download failed {url}: HTTP {r.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Download error for {url}: {e}")
            return False

    def _unzip_file(self, zip_path: Path, out_dir: Path) -> None:
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(out_dir)
        except Exception as e:
            logger.warning(f"Unzip failed for {zip_path}: {e}")

    def _head_content_length(self, url: str) -> Optional[int]:
        try:
            r = requests.head(url, timeout=30)
            if r.status_code < 400:
                cl = r.headers.get('Content-Length') or r.headers.get('content-length')
                if cl:
                    return int(cl)
        except Exception:
            return None
        return None

    def _validate_wy_fgdb_layers(self, fgdb_dir: Path) -> dict:
        """Basic validation: ensure at least one .gdb exists and is readable.
        We defer exact layer selection to _process_state_data which inspects layers.
        """
        try:
            gdbs = list(fgdb_dir.glob('**/*.gdb'))
            if not gdbs:
                return {"success": False, "error": "No FGDB directories found"}
            # Try listing layers from the first gdb as a sanity check
            try:
                _ = fiona.listlayers(str(gdbs[0]))
            except Exception as e:
                return {"success": False, "error": f"Failed to open FGDB: {e}"}
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _download_layer_data(self, state_abbr: str, layer_id: int, output_path: Path) -> dict:
        """Download specific layer data from BLM CadNSDI (single-shot)."""
        try:
            # Build query URL for BLM CadNSDI
            query_url = f"{self.blm_mapserver_base}/{layer_id}/query"
            
            params = {
                'where': f"STATEABBR='{state_abbr}'",
                'outFields': '*',
                'returnGeometry': 'true', 
                'outSR': '4326',  # WGS84
                'f': 'geojson'
            }
            
            logger.info(f"🌐 Querying BLM CadNSDI layer {layer_id} for {state_abbr}")
            
            # Make request with proper headers
            headers = {
                'User-Agent': 'Plattera/1.0 (PLSS Data Manager)',
                'Accept': 'application/json'
            }
            
            response = requests.get(query_url, params=params, headers=headers, timeout=60)
            response.raise_for_status()
            
            # Validate GeoJSON response
            geojson_data = response.json()
            if 'features' not in geojson_data:
                return {
                    "success": False,
                    "error": f"Invalid GeoJSON response for layer {layer_id}"
                }
            
            feature_count = len(geojson_data['features'])
            logger.info(f"📊 Downloaded {feature_count} features for layer {layer_id}")
            
            # Save to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(geojson_data, f)
            
            return {
                "success": True,
                "feature_count": feature_count,
                "output_path": str(output_path)
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"HTTP request failed: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Layer download error: {str(e)}"
            }

    # Legacy REST helpers removed from main path; retained only if needed elsewhere
    def _get_layer_info(self, layer_id: int) -> dict:
        return {}

    def _discover_layer_ids(self) -> None:
        return

    def _find_field_case_insensitive(self, fields_meta: List[dict], candidates: List[str]) -> Optional[str]:
        """Return the first matching field name from candidates, case-insensitive."""
        if not fields_meta:
            return None
        existing = {f.get("name"): f for f in fields_meta if isinstance(f, dict) and f.get("name")}
        upper_map = {name.upper(): name for name in existing.keys()}
        for cand in candidates:
            if cand.upper() in upper_map:
                return upper_map[cand.upper()]
        return None

    def _find_column_case_insensitive(self, columns: List[str], candidates: List[str]) -> Optional[str]:
        """Return the first matching column from a list of strings (case-insensitive)."""
        upper_map = {c.upper(): c for c in columns}
        for cand in candidates:
            if cand.upper() in upper_map:
                return upper_map[cand.upper()]
        return None

    def _build_state_where(self, info: dict, state_abbr: str) -> Optional[str]:
        """Construct a WHERE clause for filtering to a state using available field names."""
        fields_meta = info.get("fields") or []
        candidates = [
            "STATEABBR", "STATE", "STATE_CODE", "STATE_CD", "STATE_ALPHA",
            "ST", "STATEABBREV", "STATEABBRV", "STUSPS"
        ]
        field = self._find_field_case_insensitive(fields_meta, candidates)
        if field:
            return f"UPPER({field})='{state_abbr.upper()}'"
        return None

    def _download_layer_data_paginated(self, state_abbr: str, layer_id: int, output_path: Path) -> dict:
        return {"success": False, "error": "REST pagination disabled in bulk FGDB mode"}

    def ensure_township_sections(self, state: str, township: int, tdir: str, rng: int, rdir: str) -> dict:
        """Deprecated in bulk mode: sections are available locally via FGDB."""
        try:
            state_dir = self.data_dir / state.lower()
            processed_file = state_dir / "processed_plss.json"
            if not processed_file.exists():
                return {"success": False, "error": "Processed data not found"}
            with open(processed_file, 'r') as f:
                meta = json.load(f)
            if meta.get("layers", {}).get("sections_fgdb"):
                return {"success": True, "output_path": meta["layers"]["sections_fgdb"], "cached": True}
            return {"success": False, "error": "Sections FGDB not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _is_data_current(self, state: str) -> bool:
        """Check if cached data exists and is current"""
        try:
            if not self.metadata_file.exists():
                return False
            
            with open(self.metadata_file, 'r') as f:
                metadata = json.load(f)
            
            state_data = metadata.get("states", {}).get(state)
            if not state_data:
                return False
            
            # Check if files exist
            state_dir = self.data_dir / state.lower()
            processed_file = state_dir / "processed_plss.json"
            fgdb_dir = state_dir / "fgdb"
            return processed_file.exists() and fgdb_dir.exists()
            
        except Exception as e:
            logger.warning(f"Error checking data currency: {str(e)}")
            return False
    
    def _process_state_data(self, state: str) -> dict:
        """Process installed FGDBs into a lightweight manifest for consumers."""
        try:
            logger.info(f"⚙️ Processing PLSS FGDB data for {state}")
            state_dir = self.data_dir / state.lower()
            fgdb_dir = state_dir / "fgdb"
            if not fgdb_dir.exists():
                return {"success": False, "error": "FGDB directory not found"}

            # Attempt to locate FGDB directories and infer layer names
            fgdb_paths = list(fgdb_dir.glob("**/*.gdb"))
            townships_layer = None
            sections_layer = None
            subdivisions_layer = None
            townships_fgdb = None
            sections_fgdb = None
            subdivisions_fgdb = None

            # Heuristic: open each FGDB and list layers; pick likely matches by name
            for gdb in fgdb_paths:
                try:
                    layers = fiona.listlayers(str(gdb))
                except Exception:
                    continue
                lower = [l.lower() for l in layers]
                if any("township" in l for l in lower):
                    townships_fgdb = str(gdb)
                    townships_layer = layers[lower.index(next(l for l in lower if "township" in l))]
                if any(("first" in l and "division" in l) or "section" in l for l in lower):
                    sections_fgdb = str(gdb)
                    # prefer explicit 'section' if present
                    if "section" in lower:
                        sections_layer = layers[lower.index("section")]
                    else:
                        sections_layer = layers[lower.index(next(l for l in lower if ("first" in l and "division" in l) or "section" in l))]
                if any("second" in l or "third" in l or "qtr" in l or "quarter" in l for l in lower):
                    subdivisions_fgdb = str(gdb)
                    subdivisions_layer = layers[lower.index(next(l for l in lower if ("second" in l or "third" in l or "qtr" in l or "quarter" in l)))]

            if not townships_fgdb or not townships_layer:
                return {"success": False, "error": "Failed to locate Townships FGDB/layer"}
            if not sections_fgdb or not sections_layer:
                return {"success": False, "error": "Failed to locate Sections FGDB/layer"}

            # Compute extent using townships (cheapest)
            try:
                gdf_bounds = gpd.read_file(townships_fgdb, layer=townships_layer)
                bounds = gdf_bounds.total_bounds
                feature_count = len(gdf_bounds)
            except Exception as e:
                return {"success": False, "error": f"Failed to read FGDB: {e}"}

            processed_data = {
                "format": "processed_plss",
                "crs": "EPSG:4326",
                "feature_count": feature_count,
                "extent": {
                    "min_lat": float(bounds[1]), "max_lat": float(bounds[3]),
                    "min_lon": float(bounds[0]), "max_lon": float(bounds[2])
                },
                "data_source": "BLM_FGDB",
                "layers": {
                    "townships_fgdb": townships_fgdb,
                    "townships_layer": townships_layer,
                    "sections_fgdb": sections_fgdb,
                    "sections_layer": sections_layer,
                    "subdivisions_fgdb": subdivisions_fgdb,
                    "subdivisions_layer": subdivisions_layer
                }
            }

            # Build GeoParquet + TRS index for fast runtime lookups (best-effort)
            try:
                from .section_index import SectionIndex
                idx = SectionIndex(str(self.data_dir))
                # Inform UI that we're building Parquet/Index
                try:
                    self._write_progress(state, {"stage": "building:geoparquet"})
                except Exception:
                    pass
                build = idx.build_index_from_fgdb(state, sections_fgdb, sections_layer, townships_fgdb, townships_layer)
                if build.get("success"):
                    try:
                        self._write_progress(state, {"stage": "building:index"})
                    except Exception:
                        pass
                    processed_data["layers"].update({
                        "sections_parquet": build.get("sections_parquet"),
                        "sections_index": build.get("sections_index"),
                    })
                    if build.get("townships_parquet"):
                        processed_data["layers"]["townships_parquet"] = build.get("townships_parquet")
                    logger.info(f"✅ Built GeoParquet and section index for {state} ({build.get('rows')} rows)")
                else:
                    logger.warning(f"GeoParquet/index build skipped: {build.get('error')}")
            except Exception as e:
                logger.warning(f"GeoParquet/index build failed: {e}")
            
            # Save processed metadata
            try:
                self._write_progress(state, {"stage": "writing:manifest"})
            except Exception:
                pass
            processed_file = state_dir / "processed_plss.json"
            with open(processed_file, 'w') as f:
                json.dump(processed_data, f, indent=2)
            
            logger.info(f"✅ Processed PLSS FGDB for {state}")

            # Mark progress as complete so UI can dismiss modal
            try:
                self._write_progress(state, {"stage": "complete"})
            except Exception:
                pass

            return {"success": True, "processed_file": str(processed_file)}
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Processing failed: {str(e)}"
            }
    
    def _load_cached_data(self, state: str) -> dict:
        """Load cached PLSS data for state"""
        try:
            state_dir = self.data_dir / state.lower()
            processed_file = state_dir / "processed_plss.json"
            
            if not processed_file.exists():
                return {
                    "success": False,
                    "error": "Processed data file not found"
                }
            
            with open(processed_file, 'r') as f:
                vector_data = json.load(f)
            
            return {
                "success": True,
                "vector_data": vector_data,
                "data_path": str(state_dir),
                "source": "cached"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to load cached data: {str(e)}"
            }
    
    def _update_metadata(self, state: str, state_abbr: str):
        """Update metadata file with state information"""
        try:
            metadata = {}
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    metadata = json.load(f)
            
            if "states" not in metadata:
                metadata["states"] = {}
            
            metadata["states"][state] = {
                "downloaded": datetime.now().isoformat(),
                "status": "ready",
                "state_abbreviation": state_abbr,
                "source": "BLM_FGDB",
                "mapserver_url": None
            }
            
            with open(self.metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to update metadata: {str(e)}")
    
    def get_available_states(self) -> dict:
        """Get list of states with available PLSS data"""
        return {
            "available_states": list(self.state_abbrevs.keys()),
            "data_directory": str(self.data_dir),
            "source": "BLM_CadNSDI"
        }
    
    def get_state_coverage(self, state: str) -> dict:
        """Get coverage information for specific state"""
        if state not in self.state_abbrevs:
            return {
                "success": False,
                "error": f"No data source configured for {state}"
            }
        
        state_dir = self.data_dir / state.lower()
        is_downloaded = (state_dir / "processed_plss.json").exists()
        
        return {
            "success": True,
            "state": state,
            "state_abbreviation": self.state_abbrevs[state],
            "is_downloaded": is_downloaded,
            "data_source": "BLM_CadNSDI",
            "storage_path": str(state_dir)
        }