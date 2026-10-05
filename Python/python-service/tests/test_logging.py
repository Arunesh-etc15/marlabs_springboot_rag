import logging
from pathlib import Path
import pytest

from fastapi.testclient import TestClient

from app import main
from app.errors import ServiceError
from app.logging_config import configure_logging


def test_repeated_configuration_does_not_duplicate_lines(tmp_path):
    path = tmp_path / "service.log"
    configure_logging(path)
    configure_logging(path)
    logging.getLogger("policy_service").info("one application event")
    logging.getLogger("uvicorn.error").error("one server event")
    text = path.read_text(encoding="utf-8")
    assert text.count("one application event") == 1
    assert text.count("one server event") == 1


def test_log_file_rotates_and_keeps_limited_backups(tmp_path):
    path = tmp_path / "service.log"
    configure_logging(path)
    logger = logging.getLogger("policy_service")
    handler = next(handler for handler in logger.handlers
                   if getattr(handler, "policy_service_file", False))
    handler.maxBytes = 150
    for number in range(20):
        logger.info("rotation event number %s", number)
    assert path.exists()
    assert Path(str(path) + ".1").exists()
    assert Path(str(path) + ".3").exists()
    assert not Path(str(path) + ".4").exists()


def test_requests_and_errors_are_logged_without_request_text(service, provider, tmp_path, monkeypatch):
    path = tmp_path / "service.log"
    monkeypatch.setattr(main, "configure_logging", lambda: configure_logging(path))

    def fail(*args):
        raise ServiceError("PROVIDER_TIMEOUT", "Ollama did not respond in time.", 504)

    provider.generate = fail
    with TestClient(main.create_app(service=service)) as client:
        response = client.post("/internal/answer", json={
            "tenant": "Atlas", "role": "employee", "as_of": "2026-09-21",
            "question": "Certification limit? PRIVATE_QUESTION_MARKER",
        })
        assert response.status_code == 504
        assert client.post("/internal/answer", json={}).status_code == 422
    text = path.read_text(encoding="utf-8")
    assert "Service starting" in text
    assert "Service stopped" in text
    assert "code=PROVIDER_TIMEOUT status=504" in text
    assert "route=/internal/answer status=504 duration_ms=" in text
    assert "status=422" in text
    assert "PRIVATE_QUESTION_MARKER" not in text


def test_startup_failure_is_logged_and_provider_is_closed(provider, tmp_path, monkeypatch):
    path = tmp_path / "service.log"
    monkeypatch.setattr(main, "configure_logging", lambda: configure_logging(path))
    monkeypatch.setattr(main, "OllamaProvider", lambda settings: provider)

    def invalid_source(path):
        raise ValueError("Invalid policy metadata")

    monkeypatch.setattr(main, "load_policies", invalid_source)
    with pytest.raises(ValueError, match="Invalid policy metadata"):
        with TestClient(main.create_app()):
            pass
    text = path.read_text(encoding="utf-8")
    assert "Service lifecycle failed" in text
    assert "Traceback" in text
    provider.close.assert_called_once()
