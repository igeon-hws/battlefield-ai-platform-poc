import os

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, AuthenticationError


class OpenAIProvider:
    def __init__(self, api_key=None, model=None):
        self.api_key = os.getenv("OPENAI_API_KEY", "") if api_key is None else api_key
        self.model = os.getenv("OPENAI_MODEL", "") if model is None else model

    async def respond(self, inputs, *, instructions="", tools=None, result_format=None):
        if not self.api_key or not self.model:
            raise RuntimeError("OPENAI_API_KEY and OPENAI_MODEL must be configured in server .env")
        try:
            async with AsyncOpenAI(api_key=self.api_key, max_retries=1, timeout=60) as client:
                response = await client.responses.create(
                    model=self.model,
                    instructions=instructions,
                    input=inputs,
                    tools=tools or [],
                    tool_choice="auto" if tools else "none",
                    parallel_tool_calls=False,
                    text={"format": result_format},
                    store=False,
                    include=["reasoning.encrypted_content"],
                    max_output_tokens=4000,
                )
                return response.model_dump(mode="json", exclude_none=True)
        except AuthenticationError:
            raise RuntimeError("OpenAI authentication failed; check server credentials") from None
        except APIStatusError as exc:
            messages = {
                "model_not_found": "configured model is unavailable or not accessible",
                "insufficient_quota": "API quota is insufficient",
                "invalid_api_key": "authentication failed",
            }
            description = messages.get(str(exc.code), "request rejected")
            raise RuntimeError(
                f"OpenAI API returned HTTP {exc.status_code}: {description}; request {exc.request_id}"
            ) from None
        except APIConnectionError:
            raise RuntimeError("OpenAI connection failed; check server network settings") from None
