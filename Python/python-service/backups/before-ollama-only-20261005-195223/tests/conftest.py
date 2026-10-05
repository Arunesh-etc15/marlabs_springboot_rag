import chromadb
from chromadb.config import Settings
import pytest
from app.config import Settings as ServiceSettings
from app.providers import OfflineProvider
from app.service import PolicyService
from app.store import PolicyStore, load_policies


@pytest.fixture(scope="session")
def records():
    return load_policies(ServiceSettings.from_env().policy_file)


@pytest.fixture
def provider():
    class Recorder(OfflineProvider):
        def __init__(self):
            self.calls = []
        def generate(self, question, policies, expected):
            self.calls.append((question, policies))
            return super().generate(question, policies, expected)
    return Recorder()


@pytest.fixture
def service(records, provider):
    client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
    return PolicyService(PolicyStore(records, provider, client=client), provider)
