import chromadb
from chromadb.config import Settings
import pytest
from app.config import Settings as ServiceSettings
from unittest.mock import Mock
from app.providers import OllamaProvider
from app.service import PolicyService
from app.store import PolicyStore, load_policies


@pytest.fixture(scope="session")
def records():
    return load_policies(ServiceSettings.from_env().policy_file)


@pytest.fixture
def provider():
    # Unit tests mock the provider; the application itself always uses Ollama.
    mock = Mock(spec=OllamaProvider)
    mock.identity = "test-ollama"
    mock.calls = []
    mock.embed.side_effect = lambda texts: [[1.0, 0.0] for text in texts]

    def generate(question, policies, expected):
        mock.calls.append((question, policies))
        return expected.model_copy(deep=True)

    mock.generate.side_effect = generate
    return mock


@pytest.fixture
def service(records, provider):
    client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
    return PolicyService(PolicyStore(records, provider, client=client), provider)
