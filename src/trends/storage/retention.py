from datetime import UTC, datetime, timedelta
from pathlib import Path


def prune_files(root: Path, pattern: str, keep_days: int, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=keep_days)
    removed = 0
    for path in root.glob(pattern):
        if not path.is_file():
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if modified < cutoff:
            path.unlink()
            removed += 1
    return removed


def apply_retention(root: Path) -> dict[str, int]:
    """Final daily digests are intentionally never deleted."""
    return {
        "run_reports": prune_files(root / "data/runs", "*/*/*/*.json", keep_days=90),
        "pipeline_snapshots": prune_files(root / "data/pipeline", "*.json", keep_days=14),
    }

