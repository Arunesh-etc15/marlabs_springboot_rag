import json
import httpx
import pytest
from app.config import Settings
from app.errors import ServiceError
from app.models import Answer, Citation
from app.providers import OllamaProvider


def expected():
    return Answer(status="ANSWERED", answer="Approved policy text.",
                  citations=[Citation(chunk_id="approved", quote="Approved policy text.")])


@pytest.mark.parametrize("failure,code", [
    ("timeout", "PROVIDER_TIMEOUT"), ("unavailable", "PROVIDER_UNAVAILABLE"),
    ("json", "INVALID_PROVIDER_RESPONSE"), ("schema", "INVALID_PROVIDER_RESPONSE"),
    ("invented", "INVALID_PROVIDER_RESPONSE"), ("missing", "MODEL_UNAVAILABLE"),
])
def test_failure_without_retry(failure, code):
    calls = []
    def respond(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if failure == "unavailable":
            raise httpx.ConnectError("offline", request=request)
        if failure == "json":
            return httpx.Response(200, text="{broken")
        if failure == "schema":
            return httpx.Response(200, json={"done": True, "message": {"content": "{}"}})
        if failure == "missing":
            return httpx.Response(404, json={"error": "model not found"})
        wrong = expected().model_copy(update={"answer": "Claim approved for INR 999999."})
        return httpx.Response(200, json={"done": True, "message": {"content": wrong.model_dump_json()}})
    provider = OllamaProvider(Settings(), transport=httpx.MockTransport(respond))
    with pytest.raises(ServiceError) as exc:
        provider.generate("question", [], expected())
    assert exc.value.code == code and len(calls) == 1
    provider.close()


def test_ollama_payload_uses_configured_model_and_schema():
    calls = []
    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[1.0, 0.0]]})
        return httpx.Response(200, json={"done": True, "message": {"content": expected().model_dump_json()}})
    provider = OllamaProvider(Settings(), transport=httpx.MockTransport(respond))
    assert provider.embed(["test"]) == [[1.0, 0.0]]
    assert provider.generate("question", [], expected()) == expected()
    assert calls[0]["model"] == "nomic-embed-text"
    assert calls[1]["model"] == "llama3.2:3b"
    assert calls[1]["stream"] is False and isinstance(calls[1]["format"], dict)
    provider.close()


@pytest.mark.parametrize("vectors", [[], [[]], [[True]], [[1, float("nan")]], [[1], [1, 2]]])
def test_bad_embeddings(vectors):
    def respond(request):
        return httpx.Response(200, text=json.dumps({"embeddings": vectors}))
    provider = OllamaProvider(Settings(), transport=httpx.MockTransport(respond))
    with pytest.raises(ServiceError) as exc:
        provider.embed(["a"])
    assert exc.value.code == "INVALID_PROVIDER_RESPONSE"
    provider.close()
