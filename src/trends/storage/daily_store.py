import json
import os
from pathlib import Path

from trends.domain.models import DailyDigest


class DailyStore:
    def __init__(self, root: Path):
        self.root = root

    def write(self, digest: DailyDigest) -> Path:
        digest_root = self.root / digest.digest_id
        daily_path = digest_root / "days" / digest.date.strftime("%Y/%m") / f"{digest.date}.json"
        payload = digest.model_dump(mode="json", by_alias=True)
        self._atomic_json(daily_path, payload)
        self._atomic_json(digest_root / "current.json", payload)
        self._rebuild_index(digest_root)
        self._rebuild_source_history(digest_root)
        return daily_path

    @staticmethod
    def _atomic_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _rebuild_index(self, digest_root: Path) -> None:
        days = sorted(
            (path.stem for path in (digest_root / "days").glob("*/*/*.json")),
            reverse=True,
        )
        self._atomic_json(digest_root / "archive-index.json", {"dates": days})

    def _rebuild_source_history(self, digest_root: Path) -> None:
        daily_paths = sorted((digest_root / "days").glob("*/*/*.json"))[-7:]
        history: dict[str, dict[str, object]] = {}
        for path in daily_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for source in payload.get("sources", []):
                item = history.setdefault(source["source_id"], {
                    "source_id": source["source_id"],
                    "source_name": source["source_name"],
                    "releases": [],
                })
                item["releases"].append({
                    "date": payload["date"],
                    "accepted": source["accepted"],
                    "represented_events": source["represented_events"],
                    "state": source["state"],
                })
        self._atomic_json(digest_root / "source-history.json", {"sources": list(history.values())})
