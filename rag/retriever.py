from rag.local_retriever import BM25Index
from rag.vector_store import get_vector_store


def retrieve_relevant_documents(
    query,
    top_k=4,
    document_id=None
):
    if not query or not query.strip():
        return []

    if top_k <= 0:
        raise ValueError("top_k must be greater than zero.")

    store = get_vector_store()  # needs optional ChromaDB and Google embedding dependencies

    search_filter = None

    if document_id:
        search_filter = {
            "document_id": document_id
        }

    results = store.similarity_search(
        query=query,
        k=top_k,
        filter=search_filter
    )

    retrieved_documents = []

    for document in results:
        retrieved_documents.append({
            "content": document.page_content,
            "metadata": document.metadata
        })

    return retrieved_documents


def format_retrieved_context(documents):
    if not documents:
        return "No relevant documents were found."

    context_parts = []

    for index, document in enumerate(documents, start=1):
        metadata = document["metadata"]

        context_parts.append(
            f"""
DOCUMENT {index}
Document ID: {metadata.get('document_id', 'Unknown')}
Chunk: {metadata.get('chunk_index', 'Unknown')}

CONTENT:
{document['content']}
"""
        )

    return "\n".join(context_parts)


def _entry_text(entry):
    return " ".join([entry["title"], entry["instrument"], entry["citation"], entry["summary"],
                     entry["evidence_description"], " ".join(entry.get("keywords", []))])


def build_query(profile, topic_labels=None, document_text=""):
    parts = [profile.get("industry", ""), profile.get("state", "")]
    if profile.get("wastewater") == "Yes":
        parts.append("wastewater sewage trade effluent discharge consent")
    if profile.get("air_emissions") == "Yes":
        parts.append("air emissions industrial plant consent")
    if profile.get("hazardous_waste") == "Yes":
        parts.append("hazardous waste authorisation manifest annual return records")
    parts += list(topic_labels or [])
    parts.append((document_text or "")[:1500])
    return " ".join(p for p in parts if p)


def retrieve_regulations(profile, entries, topic_labels=None, document_text="", top_k=10):
    """Rank knowledge-base entries for a business.

    Uses a local BM25 index by default; the ChromaDB/Google embedding backend is used
    only if USE_VECTOR_DB=true and it works (otherwise falls back to BM25)."""
    from config import USE_VECTOR_DB
    query = build_query(profile, topic_labels, document_text)
    method, note = "local_bm25", None
    ranked = None
    if USE_VECTOR_DB:
        try:
            hits = retrieve_relevant_documents(query, top_k=top_k)
            ids = [h["metadata"].get("entry_id") for h in hits if h["metadata"].get("entry_id")]
            if ids:
                ranked = [(i, float(len(ids) - n)) for n, i in enumerate(ids)]
                method = "chromadb_vector"
        except Exception as error:
            note = f"Vector DB unavailable ({error}); used local BM25 instead."
    if ranked is None:
        index = BM25Index([(e["id"], _entry_text(e)) for e in entries])
        ranked = index.search(query, top_k)
    by_id = {e["id"]: e for e in entries}
    return {"method": method, "note": note, "query": query[:300],
            "results": [{"requirement_id": i, "score": round(s, 4), "rank": n + 1}
                        for n, (i, s) in enumerate(ranked) if i in by_id]}
