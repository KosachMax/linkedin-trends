import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from trends.collectors.runner import collect_sources
from trends.config import load_sources
from trends.pipeline.fixture_builder import build_fixture_digests
from trends.pipeline.production import run_production
from trends.storage.retention import apply_retention


def main() -> None:
    parser = argparse.ArgumentParser(description="News digest pipeline")
    parser.add_argument("command", choices=["build-fixture", "collect", "run", "retention"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    if args.command == "build-fixture":
        for path in build_fixture_digests(args.root):
            print(path)
    elif args.command == "collect":
        articles, runs = asyncio.run(collect_sources(load_sources(args.root / "config/sources")))
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = args.root / "data/pipeline" / f"{run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "run_id": run_id,
            "articles": [item.model_dump(mode="json") for item in articles],
            "sources": [item.model_dump(mode="json") for item in runs],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path)
    elif args.command == "run":
        for path in asyncio.run(run_production(args.root)):
            print(path)
    elif args.command == "retention":
        print(json.dumps(apply_retention(args.root), ensure_ascii=False))


if __name__ == "__main__":
    main()
