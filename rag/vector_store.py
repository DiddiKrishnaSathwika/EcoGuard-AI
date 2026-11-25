
from config import GEMINI_API_VERSION, GOOGLE_API_KEY, VECTOR_DB_DIR


EMBEDDING_MODEL = "models/gemini-embedding-001"


def get_embeddings():
    if not GOOGLE_API_KEY:
        raise ValueError("Google API key is missing.")

    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
        google_api_key=GOOGLE_API_KEY,
        vertexai=False,
        api_version=GEMINI_API_VERSION,
    )


def get_vector_store():
    from langchain_chroma import Chroma  # optional dependency

    embeddings = get_embeddings()

    return Chroma(
        collection_name="ecoguard_regulations",
        embedding_function=embeddings,
        persist_directory=str(VECTOR_DB_DIR)
    )


def add_documents_to_vector_store(
    chunks,
    document_id,
    metadata=None
):
    if not chunks:
        return {
            "success": False,
            "message": "No text chunks provided."
        }

    store = get_vector_store()

    documents_metadata = []

    for index, chunk in enumerate(chunks):
        item_metadata = {
            "document_id": document_id,
            "chunk_index": index
        }

        if metadata:
            item_metadata.update(metadata)

        documents_metadata.append(item_metadata)

    store.add_texts(
        texts=chunks,
        metadatas=documents_metadata,
        ids=[
            f"{document_id}_{index}"
            for index in range(len(chunks))
        ]
    )

    return {
        "success": True,
        "message": "Documents added to ChromaDB successfully.",
        "chunks_added": len(chunks),
        "document_id": document_id
    }
