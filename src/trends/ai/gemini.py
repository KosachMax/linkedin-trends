from google import genai
from google.genai import types
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential


class GeminiProvider:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-lite",
        embedding_model: str = "gemini-embedding-2",
    ) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.embedding_model = embedding_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def generate(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        return schema.model_validate_json(response.text)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), 50):
            embeddings.extend(await self._embed_batch(texts[start : start + 50]))
        return embeddings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        contents = [
            types.Content(role="user", parts=[types.Part(text=text)])
            for text in texts
        ]
        response = await self.client.aio.models.embed_content(
            model=self.embedding_model,
            contents=contents,
            config=types.EmbedContentConfig(
                task_type="CLUSTERING",
                output_dimensionality=768,
            ),
        )
        values = [list(item.values) for item in response.embeddings]
        if len(values) != len(texts):
            raise ValueError(f"expected {len(texts)} embeddings, received {len(values)}")
        return values
