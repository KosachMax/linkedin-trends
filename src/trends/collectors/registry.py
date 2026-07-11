from collections.abc import Callable

import httpx

from trends.domain.models import SourceConfig

from .base import Collector
from .rss import RssCollector

CollectorFactory = Callable[[httpx.AsyncClient], Collector]


class CollectorRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, CollectorFactory] = {}

    def register(self, source_type: str, factory: CollectorFactory) -> None:
        self._factories[source_type] = factory

    def create(self, config: SourceConfig, client: httpx.AsyncClient) -> Collector:
        try:
            return self._factories[config.type](client)
        except KeyError as error:
            raise ValueError(f"Unsupported collector type: {config.type}") from error


default_registry = CollectorRegistry()
default_registry.register("rss", RssCollector)

