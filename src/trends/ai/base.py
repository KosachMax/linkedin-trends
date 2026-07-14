from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AIProvider(Protocol):
    async def generate(self, prompt: str, schema: type[T]) -> T: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
