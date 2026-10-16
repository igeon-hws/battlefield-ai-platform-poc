import httpx
import pytest
from openai import AuthenticationError
from platform_api.providers import openai as module


async def test_provider_errors_do_not_expose_credentials(monkeypatch):
    class Client:
        async def __aenter__(self):
            self.responses = self
            return self

        async def __aexit__(self, *args):
            pass

        async def create(self, **kwargs):
            raise AuthenticationError(
                "private-key-must-not-escape",
                response=httpx.Response(
                    401, request=httpx.Request("POST", "https://api.openai.com/v1/responses")
                ),
                body={},
            )

    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kwargs: Client())
    with pytest.raises(RuntimeError, match="authentication failed") as error:
        await module.OpenAIProvider(api_key="test", model="test").respond([])
    assert "private-key" not in str(error.value)
