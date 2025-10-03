from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import json
from datetime import datetime
import shutil


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
		# Per-draft head maps
		if "raw_heads" not in head:
			head["raw_heads"] = {}
		if "alignment_heads" not in head:
			head["alignment_heads"] = {}
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

	def save_draft_v2(self, dossier_id: str, transcription_id: str, draft_index: int,
	                  edited_text: Optional[str] = None, edited_sections: Optional[Any] = None) -> Tuple[bool, str]:
		"""
		Per-draft edit save:
		- Backup current per-draft HEAD to .v1.json if not already backed up
		- Write edited content to .v2.json
		- Overwrite per-draft HEAD file ({tid}_v{n}.json) with edited content
		- Update head.json raw_heads map for this draft to 'v2'
		"""
		raw_dir = self._raw_dir(dossier_id, transcription_id)
		raw_dir.mkdir(parents=True, exist_ok=True)
		n = int(draft_index) + 1
		base = raw_dir / f"{transcription_id}_v{n}.json"
		v1_backup = raw_dir / f"{transcription_id}_v{n}.v1.json"
		v2_file = raw_dir / f"{transcription_id}_v{n}.v2.json"

		# Build payload
		if edited_sections is not None and isinstance(edited_sections, list):
			payload = {
				"documentId": "edited",
				"sections": edited_sections,
				"_status": "completed",
				"_draft_index": draft_index,
				"_updated_at": datetime.utcnow().isoformat()
			}
		else:
			text = edited_text or ""
			payload = {
				"documentId": "edited",
				"sections": [{"id": 1, "body": text}],
				"_status": "completed",
				"_draft_index": draft_index,
				"_updated_at": datetime.utcnow().isoformat()
			}

		# Backup v1 if not present
		try:
			if base.exists() and not v1_backup.exists():
				shutil.copyfile(base, v1_backup)
		except Exception:
			pass

		# Write v2 and update per-draft HEAD pointer
		self._write_json(v2_file, payload)
		self._write_json(base, payload)

		# Update head.json: per-draft heads map
		head = self._ensure_head(dossier_id, transcription_id)
		if "raw_heads" not in head:
			head["raw_heads"] = {}
		draft_key = f"{transcription_id}_v{n}"
		head["raw_heads"][draft_key] = "v2"
		self._write_json(self._head_file(dossier_id, transcription_id), head)

		return True, "v2"

	def revert_draft_to_v1(self, dossier_id: str, transcription_id: str, draft_index: int, purge: bool = False) -> bool:
		"""
		Per-draft revert:
		- If .v1.json exists, copy it back into per-draft HEAD ({tid}_v{n}.json)
		- Optionally delete .v2.json
		- Update head.json raw_heads map for this draft to 'v1'
		"""
		raw_dir = self._raw_dir(dossier_id, transcription_id)
		n = int(draft_index) + 1
		base = raw_dir / f"{transcription_id}_v{n}.json"
		v1_backup = raw_dir / f"{transcription_id}_v{n}.v1.json"
		v2_file = raw_dir / f"{transcription_id}_v{n}.v2.json"

		if not v1_backup.exists():
			# No backup to revert to
			return False

		try:
			with open(v1_backup, "r", encoding="utf-8") as f:
				data = json.load(f)
			self._write_json(base, data)
		except Exception:
			return False

		if purge:
			try:
				if v2_file.exists():
					v2_file.unlink()
			except Exception:
				pass

		# Update head.json map
		head = self._ensure_head(dossier_id, transcription_id)
		if "raw_heads" not in head:
			head["raw_heads"] = {}
		draft_key = f"{transcription_id}_v{n}"
		head["raw_heads"][draft_key] = "v1"
		self._write_json(self._head_file(dossier_id, transcription_id), head)
		return True

	# ---------------- Alignment per-draft persistence ----------------
	def save_alignment_v1(self, dossier_id: str, transcription_id: str, draft_index: int, sections: Any) -> Tuple[bool, str]:
		"""
		Persist alignment v1 for a specific draft and set alignment HEAD to v1.
		Writes:
		- alignment/draft_{n}_v1.json
		- alignment/draft_{n}.json (HEAD copy)
		Updates head.json.alignment_heads["{tid}_draft_{n}"] = "v1"
		"""
		align_dir = self._alignment_dir(dossier_id, transcription_id)
		align_dir.mkdir(parents=True, exist_ok=True)
		n = int(draft_index) + 1
		v1_path = align_dir / f"draft_{n}_v1.json"
		head_path = align_dir / f"draft_{n}.json"

		payload = {
			"documentId": "alignment_v1",
			"sections": sections if isinstance(sections, list) else [{"id": 1, "body": str(sections or "")}],
			"_status": "completed",
			"_draft_index": draft_index,
			"_updated_at": datetime.utcnow().isoformat()
		}
		self._write_json(v1_path, payload)
		self._write_json(head_path, payload)

		head = self._ensure_head(dossier_id, transcription_id)
		dkey = f"{transcription_id}_draft_{n}"
		head.setdefault("alignment_heads", {})[dkey] = "v1"
		self._write_json(self._head_file(dossier_id, transcription_id), head)
		return True, "v1"

	def save_alignment_v2(self, dossier_id: str, transcription_id: str, draft_index: int, sections: Any) -> Tuple[bool, str]:
		"""
		Persist alignment v2 for a specific draft and set alignment HEAD to v2.
		Writes alignment/draft_{n}_v2.json and overwrites alignment/draft_{n}.json
		Updates head.json.alignment_heads accordingly.
		"""
		align_dir = self._alignment_dir(dossier_id, transcription_id)
		align_dir.mkdir(parents=True, exist_ok=True)
		n = int(draft_index) + 1
		v2_path = align_dir / f"draft_{n}_v2.json"
		head_path = align_dir / f"draft_{n}.json"

		payload = {
			"documentId": "alignment_v2",
			"sections": sections if isinstance(sections, list) else [{"id": 1, "body": str(sections or "")}],
			"_status": "completed",
			"_draft_index": draft_index,
			"_updated_at": datetime.utcnow().isoformat()
		}
		self._write_json(v2_path, payload)
		self._write_json(head_path, payload)

		head = self._ensure_head(dossier_id, transcription_id)
		dkey = f"{transcription_id}_draft_{n}"
		head.setdefault("alignment_heads", {})[dkey] = "v2"
		self._write_json(self._head_file(dossier_id, transcription_id), head)
		return True, "v2"

	def revert_alignment_to_v1(self, dossier_id: str, transcription_id: str, draft_index: int, purge: bool = False) -> bool:
		"""
		Revert alignment HEAD for a draft back to v1; optionally remove v2 file.
		"""
		align_dir = self._alignment_dir(dossier_id, transcription_id)
		n = int(draft_index) + 1
		v1_path = align_dir / f"draft_{n}_v1.json"
		v2_path = align_dir / f"draft_{n}_v2.json"
		head_path = align_dir / f"draft_{n}.json"
		if not v1_path.exists():
			return False
		data = self._read_json(v1_path) or {}
		self._write_json(head_path, data)
		if purge and v2_path.exists():
			try: v2_path.unlink()
			except Exception: pass
		head = self._ensure_head(dossier_id, transcription_id)
		dkey = f"{transcription_id}_draft_{n}"
		head.setdefault("alignment_heads", {})[dkey] = "v1"
		self._write_json(self._head_file(dossier_id, transcription_id), head)
		return True
