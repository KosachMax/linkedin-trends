from google import genai
from google.genai import types
from pydantic import BaseModel


class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite") -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model

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

