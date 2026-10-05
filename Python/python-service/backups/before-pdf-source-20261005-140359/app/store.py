"""Load source policies and search their persistent Chroma index."""

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
    """Read JSON, validate every record, and reject conflicting duplicate IDs."""
    policy_json = path.read_text(encoding="utf-8")
    policies = TypeAdapter(list[Policy]).validate_json(policy_json)
    policies_by_id = {}
    for policy in policies:
        if policy.id in policies_by_id and policies_by_id[policy.id] != policy:
            raise ValueError("Policy IDs must not identify different records.")
        policies_by_id[policy.id] = policy
    return sorted(policies_by_id.values(), key=lambda policy: policy.id)


class PolicyStore:
    """The JSON is the source of truth; Chroma is its searchable index."""

    def __init__(self, records, provider, client=None, path=None):
        self.records = records
        self.provider = provider
        self.client = client or chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        # A different corpus or embedding model must use a different collection.
        policy_data = [policy.model_dump(mode="json") for policy in records]
        fingerprint = json.dumps(policy_data, sort_keys=True)
        collection_key = (provider.identity + fingerprint).encode()
        digest = hashlib.sha256(collection_key).hexdigest()[:32]
        self.collection = self.client.get_or_create_collection(
            name="policies-" + digest, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )
        self._indexed = False
        self._lock = Lock()

    def _ensure_index(self):
        """Build embeddings once when a request first needs policy retrieval."""
        with self._lock:
            if self._indexed:
                return
            needs_index = self.collection.count() != len(self.records)
            if needs_index and self.records:
                ids = []
                texts = []
                metadata = []
                for policy in self.records:
                    ids.append(policy.id)
                    texts.append(policy.text)
                    metadata.append({
                        "tenant": policy.tenant,
                        "role": policy.role,
                        "approval_state": policy.approval_state,
                        # Chroma compares dates as integer day numbers.
                        "effective_from": policy.effective_from.toordinal(),
                        "effective_to": policy.effective_to.toordinal(),
                        "is_evidence": is_evidence(policy.text),
                    })

                vectors = self.provider.embed(texts)
                self.collection.upsert(
                    ids=ids,
                    documents=texts,
                    embeddings=vectors,
                    metadatas=metadata,
                )
            self._indexed = True

    def retrieve(self, context, question, topics):
        """Filter authorized policies first, then search and match benefit topics."""
        try:
            self._ensure_index()
            requested_day = context.as_of.toordinal()
            where = {
                "$and": [
                    {"tenant": context.tenant},
                    {"role": context.role},
                    {"approval_state": "Approved"},
                    {"effective_from": {"$lte": requested_day}},
                    {"effective_to": {"$gt": requested_day}},
                    {"is_evidence": True},
                ]
            }
            eligible = self.collection.get(where=where, include=[])
            count = len(eligible["ids"])
            if not count:
                return []
            # Retrieve all eligible passages so ranking cannot hide a policy conflict.
            question_vector = self.provider.embed([question])
            result = self.collection.query(
                query_embeddings=question_vector,
                n_results=count,
                where=where,
                include=["documents"],
            )
            policies_by_id = {policy.id: policy for policy in self.records}
            relevant = []
            requested_topics = set(topics)
            for policy_id in result["ids"][0]:
                policy = policies_by_id[policy_id]
                # Recheck returned evidence rather than trusting the index alone.
                authorized = (
                    policy.tenant == context.tenant
                    and policy.role == context.role
                    and policy.approval_state == "Approved"
                    and policy.effective_from <= context.as_of < policy.effective_to
                    and is_evidence(policy.text)
                )
                if not authorized:
                    raise ServiceError("RETRIEVAL_ERROR", "Policy retrieval returned unauthorized evidence.")
                policy_topics = set(mentions(policy.text))
                if policy_topics & requested_topics:
                    relevant.append(policy)
            return sorted(relevant, key=lambda policy: policy.id)
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError("RETRIEVAL_ERROR", "Policy retrieval failed.") from exc
