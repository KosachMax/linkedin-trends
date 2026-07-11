from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from .domain.models import DigestProfile, SourceConfig

T = TypeVar("T", bound=BaseModel)


def _load_directory(path: Path, model: type[T]) -> list[T]:
    if not path.exists():
        return []
    values = []
    for config_path in sorted(path.glob("*.yaml")):
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        values.append(model.model_validate(payload))
    return values


def load_sources(root: Path = Path("config/sources")) -> list[SourceConfig]:
    return _load_directory(root, SourceConfig)


def load_digests(root: Path = Path("config/digests")) -> list[DigestProfile]:
    return _load_directory(root, DigestProfile)

