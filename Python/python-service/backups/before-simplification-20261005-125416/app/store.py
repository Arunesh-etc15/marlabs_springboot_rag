import hashlib
import json
from threading import Lock
import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import TypeAdapter
from .errors import ServiceError
from .models import Policy
from .topics import is_evidence, mentions


def load_policies(path):
    parsed = TypeAdapter(list[Policy]).validate_json(path.read_text(encoding="utf-8"))
    records = {}
    for policy in parsed:
        if policy.id in records and records[policy.id] != policy:
            raise ValueError("Policy IDs must not identify different records.")
        records[policy.id] = policy
    return sorted(records.values(), key=lambda p: p.id)


class PolicyStore:
    def __init__(self, records, provider, client=None, path=None):
        self.records = records
        self.provider = provider
        self.client = client or chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        fingerprint = json.dumps([p.model_dump(mode="json") for p in records], sort_keys=True)
        digest = hashlib.sha256((provider.identity + fingerprint).encode()).hexdigest()[:32]
        self.collection = self.client.get_or_create_collection(
            name="policies-" + digest, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )
        self._indexed = False
        self._lock = Lock()

    def _ensure_index(self):
        with self._lock:
            if self._indexed:
                return
            if self.collection.count() != len(self.records):
                if self.records:
                    vectors = self.provider.embed([p.text for p in self.records])
                    self.collection.upsert(
                        ids=[p.id for p in self.records], documents=[p.text for p in self.records],
                        embeddings=vectors, metadatas=[{
                            "tenant": p.tenant, "role": p.role, "approval_state": p.approval_state,
                            "effective_from": p.effective_from.toordinal(),
                            "effective_to": p.effective_to.toordinal(), "is_evidence": is_evidence(p.text),
                        } for p in self.records],
                    )
            self._indexed = True

    def retrieve(self, context, question, topics):
        try:
            self._ensure_index()
            where = {"$and": [
                {"tenant": context.tenant}, {"role": context.role}, {"approval_state": "Approved"},
                {"effective_from": {"$lte": context.as_of.toordinal()}},
                {"effective_to": {"$gt": context.as_of.toordinal()}}, {"is_evidence": True},
            ]}
            count = len(self.collection.get(where=where, include=[])["ids"])
            if not count:
                return []
            # Retrieve all eligible passages so ranking cannot hide a policy conflict.
            result = self.collection.query(query_embeddings=self.provider.embed([question]),
                                           n_results=count, where=where, include=["documents"])
            by_id = {p.id: p for p in self.records}
            relevant = []
            for id_ in result["ids"][0]:
                policy = by_id[id_]
                if not (policy.tenant == context.tenant and policy.role == context.role
                        and policy.approval_state == "Approved"
                        and policy.effective_from <= context.as_of < policy.effective_to
                        and is_evidence(policy.text)):
                    raise ServiceError("RETRIEVAL_ERROR", "Policy retrieval returned unauthorized evidence.")
                if set(mentions(policy.text)) & set(topics):
                    relevant.append(policy)
            return sorted(relevant, key=lambda p: p.id)
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError("RETRIEVAL_ERROR", "Policy retrieval failed.") from exc
