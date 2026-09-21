"""
RAG Indexer
Indexes documents into ChromaDB for vector retrieval.

Supports two modes:
1. HttpClient — connects to a running ChromaDB server (Docker or standalone)
2. PersistentClient — uses local file-based storage (for development without Docker)

Embedding strategy:
- Primary: Tencent Hunyuan Embedding API (if TENCENT_SECRET_ID/KEY set)
- Fallback: Simple hash-based embedding for local dev/testing
"""
import os
import uuid
import asyncio
import chromadb

from src.config import (
    CHROMA_HOST, CHROMA_PORT, CHROMA_COLLECTION,
    POLICIES_DIR, BASE_DIR,
)
from src.rag.embedding import embedding_manager


def _get_chroma_client():
    """
    Get a ChromaDB client.
    Tries HttpClient first (for Docker/remote), falls back to PersistentClient (local dev).
    """
    try:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        client.heartbeat()
        return client, "http"
    except Exception:
        pass

    local_path = os.path.join(BASE_DIR, "chroma_data")
    os.makedirs(local_path, exist_ok=True)
    client = chromadb.PersistentClient(path=local_path)
    return client, "local"


class ManualEmbeddingFunction:
    """
    Custom embedding function for ChromaDB that uses our EmbeddingManager.
    ChromaDB calls these synchronously, but our embedding manager uses async
    (for Tencent API calls). We bridge this with asyncio.run_in_executor
    or a new event loop in a thread.

    ChromaDB expects:
    - __call__(input: list[str]) -> list[list[float]]  (for documents)
    - embed_query(input: str) -> list[list[float]]      (for queries)
    """

    def __call__(self, input):
        """Called by ChromaDB for document embedding. Returns list of embeddings."""
        return self._run_async(embedding_manager.embed_batch(input))

    def embed_query(self, input):
        """Called by ChromaDB for query embedding.
        ChromaDB passes a list of query texts (usually 1).
        Returns a list of embeddings (matching input length).
        """
        texts = input if isinstance(input, list) else [input]
        return self._run_async(embedding_manager.embed_batch(texts))

    def _run_async(self, coro):
        """Run an async coroutine from a sync context, handling running event loops."""
        import threading
        result = [None]
        exc = [None]

        def runner():
            loop = asyncio.new_event_loop()
            try:
                result[0] = loop.run_until_complete(coro)
            except Exception as e:
                exc[0] = e
            finally:
                loop.close()

        # If there's a running event loop, use a thread
        try:
            asyncio.get_running_loop()
            t = threading.Thread(target=runner)
            t.start()
            t.join()
        except RuntimeError:
            # No running loop, run directly
            runner()

        if exc[0]:
            raise exc[0]
        return result[0]

    def name(self):
        return f"embedding_manager_{embedding_manager.mode}"


class DocumentIndexer:
    """Indexes documents into ChromaDB for RAG retrieval."""

    # Chunking settings
    CHUNK_SIZE = 500  # words per chunk
    CHUNK_OVERLAP = 50  # words of overlap between chunks

    def __init__(self):
        self.client, self.mode = _get_chroma_client()
        self.embedding_fn = ManualEmbeddingFunction()

    def get_or_create_collection(self, collection_name: str | None = None):
        """Get or create the ChromaDB collection."""
        name = collection_name or CHROMA_COLLECTION
        return self.client.get_or_create_collection(
            name=name,
            metadata={"description": "Ryde RAG knowledge base"},
            embedding_function=self.embedding_fn,
        )

    def index_documents(self, documents: list[dict], collection_name: str | None = None) -> int:
        """
        Index documents into ChromaDB.

        Args:
            documents: list of {id, title, content, source, section, file_type}
            collection_name: optional custom collection name

        Returns:
            Number of chunks indexed.
        """
        collection = self.get_or_create_collection(collection_name)

        count = 0
        for doc in documents:
            chunks = self._chunk_document(doc["content"])
            for i, chunk_text in enumerate(chunks):
                chunk_id = f"{doc['id']}_{i:04d}"
                metadata = {
                    "title": doc["title"],
                    "source": doc.get("source", doc["title"]),
                    "section": doc.get("section", ""),
                    "file_type": doc.get("file_type", ""),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }
                collection.upsert(
                    ids=[chunk_id],
                    documents=[chunk_text],
                    metadatas=[metadata],
                )
                count += 1

        return count

    def index_file(
        self,
        filename: str,
        content: str,
        file_type: str = "",
        collection_name: str | None = None,
    ) -> int:
        """
        Index a single parsed file into ChromaDB.

        Args:
            filename: original filename
            content: parsed plain text content
            file_type: file extension (e.g. ".pdf")
            collection_name: optional collection override

        Returns:
            Number of chunks indexed.
        """
        doc_id = filename.rsplit(".", 1)[0].replace(" ", "_").lower()
        doc_id += f"_{uuid.uuid4().hex[:8]}"

        documents = [{
            "id": doc_id,
            "title": filename,
            "content": content,
            "source": filename,
            "section": "",
            "file_type": file_type,
        }]

        return self.index_documents(documents, collection_name)

    def _load_policy_files(self) -> list[dict]:
        """Load all .md files from the policies directory."""
        documents = []
        if not os.path.exists(POLICIES_DIR):
            return documents

        for filename in sorted(os.listdir(POLICIES_DIR)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(POLICIES_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            doc_id = filename.replace(".md", "")
            title = doc_id.replace("_", " ").title()
            documents.append({
                "id": doc_id,
                "title": title,
                "content": content,
                "source": filename,
                "section": "",
                "file_type": ".md",
            })

        return documents

    def index_policies(self) -> int:
        """Index all policy .md files from POLICIES_DIR."""
        docs = self._load_policy_files()
        return self.index_documents(docs)

    def _chunk_document(self, text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
        """Split document into overlapping word chunks."""
        cs = chunk_size or self.CHUNK_SIZE
        ol = overlap or self.CHUNK_OVERLAP
        words = text.split()
        if len(words) <= cs:
            return [text]
        chunks = []
        start = 0
        while start < len(words):
            end = start + cs
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            start = end - ol
        return chunks

    def get_collection_stats(self, collection_name: str | None = None) -> dict:
        """Get statistics about the indexed collection."""
        name = collection_name or CHROMA_COLLECTION
        try:
            collection = self.client.get_collection(name)
            count = collection.count()
            return {
                "collection": name,
                "chunk_count": count,
                "mode": self.mode,
            }
        except Exception:
            return {
                "collection": name,
                "chunk_count": 0,
                "mode": self.mode,
                "error": "Collection not found",
            }

    def clear_collection(self, collection_name: str | None = None):
        """Delete the entire collection (for re-indexing)."""
        name = collection_name or CHROMA_COLLECTION
        try:
            self.client.delete_collection(name)
            print(f"Deleted collection: {name}")
        except Exception:
            pass

    def list_collections(self) -> list[str]:
        """List all collections in ChromaDB."""
        try:
            return [c.name for c in self.client.list_collections()]
        except Exception:
            return []


# Backward-compatible alias
PolicyIndexer = DocumentIndexer
