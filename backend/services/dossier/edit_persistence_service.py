from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import json
from datetime import datetime


class EditPersistenceService:
	"""
	V1/V2-only storage and HEAD management for transcription drafts.

	Layout:
	- backend/dossiers_data/views/transcriptions/{dossier_id}/{transcription_id}/
	  - raw/{transcription_id}_v1.json
	  - raw/{transcription_id}_v2.json (optional)
	  - raw/{transcription_id}.json     # pointer copy to current raw head (v1 or v2)
	  - alignment/                       # reserved for alignment outputs (future)
	  - consensus/                       # LLM and alignment consensus (existing modules write here)
	  - final/transcription_final.json   # final per-transcription (elsewhere)
	  - head.json                        # tracks heads (v1 or v2) for raw/consensus/alignment
	"""

	def __init__(self):
		self.backend_dir = Path(__file__).resolve().parents[2]
		self.transcriptions_root = self.backend_dir / "dossiers_data" / "views" / "transcriptions"

	# --------------- helpers ---------------
	def _run_dir(self, dossier_id: str, transcription_id: str) -> Path:
		return self.transcriptions_root / str(dossier_id) / str(transcription_id)

	def _raw_dir(self, dossier_id: str, transcription_id: str) -> Path:
		return self._run_dir(dossier_id, transcription_id) / "raw"

	def _consensus_dir(self, dossier_id: str, transcription_id: str) -> Path:
		return self._run_dir(dossier_id, transcription_id) / "consensus"

	def _alignment_dir(self, dossier_id: str, transcription_id: str) -> Path:
		return self._run_dir(dossier_id, transcription_id) / "alignment"

	def _head_file(self, dossier_id: str, transcription_id: str) -> Path:
		return self._run_dir(dossier_id, transcription_id) / "head.json"

	def _read_json(self, path: Path) -> Optional[Dict[str, Any]]:
		try:
			if path.exists():
				with open(path, "r", encoding="utf-8") as f:
					return json.load(f)
		except Exception:
			return None
		return None

	def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
		path.parent.mkdir(parents=True, exist_ok=True)
		with open(path, "w", encoding="utf-8") as f:
			json.dump(data, f, indent=2, ensure_ascii=False)

	def _ensure_head(self, dossier_id: str, transcription_id: str) -> Dict[str, Any]:
		head_path = self._head_file(dossier_id, transcription_id)
		head = self._read_json(head_path) or {}
		if "raw" not in head:
			head["raw"] = {"head": "v1"}
		if "alignment" not in head:
			head["alignment"] = {"head": None}
		if "consensus" not in head:
			head["consensus"] = {"llm": {"head": None}, "alignment": {"head": None}}
		return head

	def _current_raw_head(self, dossier_id: str, transcription_id: str) -> str:
		head = self._ensure_head(dossier_id, transcription_id)
		return head.get("raw", {}).get("head") or "v1"

	def _update_pointer_copy(self, dossier_id: str, transcription_id: str, v: str) -> None:
		raw_dir = self._raw_dir(dossier_id, transcription_id)
		src = raw_dir / f"{transcription_id}_{v}.json"
		dst = raw_dir / f"{transcription_id}.json"
		if src.exists():
			data = self._read_json(src)
			if data is not None:
				self._write_json(dst, data)

	# --------------- public ops ---------------
	def get_head(self, dossier_id: str, transcription_id: str) -> Dict[str, Any]:
		return self._ensure_head(dossier_id, transcription_id)

	def set_raw_head(self, dossier_id: str, transcription_id: str, v: str) -> bool:
		if v not in ("v1", "v2"):
			return False
		raw_dir = self._raw_dir(dossier_id, transcription_id)
		if not (raw_dir / f"{transcription_id}_{v}.json").exists():
			return False
		head = self._ensure_head(dossier_id, transcription_id)
		head["raw"]["head"] = v
		self._write_json(self._head_file(dossier_id, transcription_id), head)
		self._update_pointer_copy(dossier_id, transcription_id, v)
		return True

	def revert_to_v1(self, dossier_id: str, transcription_id: str, purge: bool = False) -> bool:
		ok = self.set_raw_head(dossier_id, transcription_id, "v1")
		head = self._ensure_head(dossier_id, transcription_id)
		head["alignment"]["head"] = None
		head["consensus"]["llm"]["head"] = None
		head["consensus"]["alignment"]["head"] = None
		self._write_json(self._head_file(dossier_id, transcription_id), head)

		if purge:
			try:
				raw_dir = self._raw_dir(dossier_id, transcription_id)
				v2 = raw_dir / f"{transcription_id}_v2.json"
				if v2.exists():
					v2.unlink()
			except Exception:
				pass
			try:
				cons = self._consensus_dir(dossier_id, transcription_id)
				for name in [f"llm_{transcription_id}_v2.json", f"alignment_{transcription_id}_v2.json"]:
					p = cons / name
					if p.exists():
						p.unlink()
			except Exception:
				pass
			try:
				align_dir = self._alignment_dir(dossier_id, transcription_id)
				for name in [f"reconstructed_{transcription_id}_v2.json"]:
					p = align_dir / name
					if p.exists():
						p.unlink()
			except Exception:
				pass

		return ok

	def save_raw_v2(self, dossier_id: str, transcription_id: str, edited_text: Optional[str] = None,
	                edited_sections: Optional[Any] = None) -> Tuple[bool, str]:
		"""
		Create/overwrite v2 for raw content. Preserve sectioned shape if edited_sections given;
		else, save as a single-section edited draft.
		Returns (success, head_set_to)
		"""
		raw_dir = self._raw_dir(dossier_id, transcription_id)
		raw_dir.mkdir(parents=True, exist_ok=True)

		v2 = raw_dir / f"{transcription_id}_v2.json"

		if edited_sections is not None and isinstance(edited_sections, list):
			payload = {
				"documentId": "edited",
				"sections": edited_sections,
				"_status": "completed",
				"_draft_index": 1,
				"_updated_at": datetime.utcnow().isoformat()
			}
		else:
			text = edited_text or ""
			payload = {
				"documentId": "edited",
				"sections": [
					{"id": 1, "body": text}
				],
				"_status": "completed",
				"_draft_index": 1,
				"_updated_at": datetime.utcnow().isoformat()
			}

		self._write_json(v2, payload)
		self.set_raw_head(dossier_id, transcription_id, "v2")
		return True, "v2"


