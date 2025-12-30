from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Union

from .events import OutcomeEvent, RetrievalEvent, SchemaAttemptEvent


EvalEvent = Union[RetrievalEvent, SchemaAttemptEvent, OutcomeEvent]


@dataclass
class EvalLogger:
    """
    File-backed event logger (v0).

    Writes newline-delimited JSON (jsonl). Location is intentionally simple for v0.
    If you want this stored under dossiers_data later, we can route via config.paths.
    """

    out_path: Path = Path("backend") / "logs" / "eval_events.jsonl"

    def log(self, event: EvalEvent) -> None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = asdict(event)
        payload["_ts"] = datetime.utcnow().isoformat()
        payload["_type"] = event.__class__.__name__
        with self.out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


