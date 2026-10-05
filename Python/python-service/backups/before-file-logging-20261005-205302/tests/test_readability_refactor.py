"""Focused regressions for settings, lazy indexing, and extraction evidence."""

from datetime import date
from unittest.mock import Mock

import httpx
import pytest

from app.config import Settings
from app.errors import ServiceError
from app.extraction import extract
from app.models import Context
from app.providers import OllamaProvider
from fastapi.testclient import TestClient
from app import main


def test_environment_overrides_file_paths_and_models(monkeypatch, tmp_path):
    policy_file = tmp_path / "policies.pdf"
    callers_file = tmp_path / "callers.json"
    chroma_path = tmp_path / "chroma"
    monkeypatch.setenv("POLICY_FILE", str(policy_file))
    monkeypatch.setenv("CALLERS_FILE", str(callers_file))
    monkeypatch.setenv("CHROMA_PATH", str(chroma_path))
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "45")

    settings = Settings.from_env()

    assert settings.policy_file == policy_file
    assert settings.callers_file == callers_file
    assert settings.chroma_path == chroma_path
    assert settings.model == "llama3.2:3b"
    assert settings.embedding_model == "nomic-embed-text"
    assert settings.timeout_seconds == 45


@pytest.mark.parametrize("name,value", [
    ("OLLAMA_TIMEOUT_SECONDS", "0"),
    ("OLLAMA_TIMEOUT_SECONDS", "61"),
])
def test_invalid_configuration_is_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_index_is_lazy_and_reused(service, provider, records):
    calls = []
    original_embed = provider.embed

    def record_embedding(texts):
        calls.append(list(texts))
        return original_embed(texts)

    provider.embed = record_embedding
    context = Context(tenant="Atlas", role="employee", as_of=date(2026, 9, 21))
    assert service.store.collection.count() == 0

    service.answer(context, "Certification limit?")
    service.answer(context, "Certification limit?")

    assert len(calls[0]) == len(records)
    assert [len(texts) for texts in calls[1:]] == [1, 1]
    assert service.store.collection.count() == len(records)


def test_repeated_equal_fields_keep_one_exact_quote():
    text = "Certification INR 18,000.50 Reference: CERT-1\n" * 2
    fields, evidence, issues = extract(text)
    assert fields.amount == 18000.50
    assert fields.currency == "INR"
    assert fields.reference == "CERT-1"
    assert evidence["amount"] == ["INR 18,000.50"]
    assert evidence["reference"] == ["Reference: CERT-1"]
    assert issues == []


def test_embedding_dimensions_must_match():
    def respond(request):
        return httpx.Response(200, json={"embeddings": [[1.0], [1.0, 2.0]]})

    provider = OllamaProvider(Settings(), transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(ServiceError) as error:
            provider.embed(["first", "second"])
        assert error.value.code == "INVALID_PROVIDER_RESPONSE"
    finally:
        provider.close()


def test_startup_always_uses_ollama_and_closes_it(monkeypatch, provider, records):
    factory = Mock(return_value=provider)
    monkeypatch.setattr(main, "OllamaProvider", factory)
    monkeypatch.setattr(main, "load_policies", lambda path: records)
    monkeypatch.setattr(main, "PolicyStore", Mock(return_value=Mock()))
    settings = Settings.from_env()
    with TestClient(main.create_app(settings=settings)) as client:
        assert client.get("/health").json()["mode"] == "ollama"
        factory.assert_called_once_with(settings)
        assert client.app.state.service.provider is provider
    provider.close.assert_called_once()
