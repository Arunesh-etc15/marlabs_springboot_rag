"""Load source policies and search their persistent Chroma index."""

import hashlib
import json
from threading import Lock
import chromadb
from chromadb.config import Settings as ChromaSettings
from .errors import ServiceError
from .policy_source import load_pdf_policies
from .topics import is_evidence, mentions


def load_policies(path):
    """Read and validate policy records directly from the PDF source."""
    return load_pdf_policies(path)


def get_policy_id(policy):
    """Give sorted() the field to sort by."""
    return policy.id


class PolicyStore:
    """The PDF is the source of truth; Chroma is its searchable index."""

    def __init__(self, records, provider, client=None, path=None):
        self.records = records
        self.provider = provider
        if client:
            self.client = client
        else:
            self.client = chromadb.PersistentClient(
                path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
            )
        # A different corpus or embedding model must use a different collection.
        policy_data = []
        for policy in records:
            policy_data.append(policy.model_dump(mode="json"))
        policy_json = json.dumps(policy_data, sort_keys=True)
        collection_text = "pdf-source-v1:" + provider.identity + policy_json
        collection_bytes = collection_text.encode()
        full_hash = hashlib.sha256(collection_bytes).hexdigest()
        collection_name = "policies-" + full_hash[:32]
        self.collection = self.client.get_or_create_collection(
            name=collection_name, embedding_function=None, metadata={"hnsw:space": "cosine"}
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
                        "source_type": "pdf",
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
            # 1. Make sure the policy texts have been stored as vectors.
            self._ensure_index()

            # 2. Only search policies this caller is allowed to use.
            policy_filter = self._build_filter(context)
            eligible_policies = self.collection.get(where=policy_filter, include=[])
            eligible_count = len(eligible_policies["ids"])
            if eligible_count == 0:
                return []

            # 3. Convert the question into a vector and search Chroma.
            # Retrieve all eligible passages so ranking cannot hide a policy conflict.
            question_embeddings = self.provider.embed([question])
            search_result = self.collection.query(
                query_embeddings=question_embeddings,
                n_results=eligible_count,
                where=policy_filter,
                include=["documents"],
            )

            # 4. Convert search IDs back into the original policy objects.
            policies_by_id = {}
            for policy in self.records:
                policies_by_id[policy.id] = policy
            relevant_policies = []
            requested_topics = set(topics)
            # Chroma returns one result list for each question vector.
            matching_ids = search_result["ids"][0]
            for policy_id in matching_ids:
                policy = policies_by_id[policy_id]
                # Recheck returned evidence rather than trusting the index alone.
                if not self._is_allowed(policy, context):
                    raise ServiceError("RETRIEVAL_ERROR", "Policy retrieval returned unauthorized evidence.")
                policy_topics = set(mentions(policy.text))
                matching_topics = policy_topics.intersection(requested_topics)
                if matching_topics:
                    relevant_policies.append(policy)
            return sorted(relevant_policies, key=get_policy_id)
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError("RETRIEVAL_ERROR", "Policy retrieval failed.") from exc

    def _build_filter(self, context):
        """Translate the caller and date into Chroma's filter format."""
        requested_day = context.as_of.toordinal()
        return {
            "$and": [
                {"tenant": context.tenant},
                {"role": context.role},
                {"approval_state": "Approved"},
                {"effective_from": {"$lte": requested_day}},
                {"effective_to": {"$gt": requested_day}},
                {"is_evidence": True},
            ]
        }

    def _is_allowed(self, policy, context):
        """Return False as soon as a policy fails one access or date check."""
        if policy.tenant != context.tenant:
            return False
        if policy.role != context.role:
            return False
        if policy.approval_state != "Approved":
            return False
        if context.as_of < policy.effective_from:
            return False
        if context.as_of >= policy.effective_to:
            return False
        if not is_evidence(policy.text):
            return False
        return True
