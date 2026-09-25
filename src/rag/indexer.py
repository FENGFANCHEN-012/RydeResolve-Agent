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
import threading
import chromadb

from src import config
from src.config import (
    CHROMA_HOST, CHROMA_PORT, CHROMA_COLLECTION,
    POLICIES_DIR, BASE_DIR,
)
from src.rag.embedding import embedding_manager


_chroma_client_cache: tuple | None = None
_chroma_client_lock = threading.Lock()


def _get_chroma_client():
    """
    Get a ChromaDB client (created once per process, then reused).
    Tries HttpClient first (for Docker/remote), falls back to PersistentClient (local dev).

    The HTTP probe takes several seconds to fail when no Chroma server is
    running, so it must not be repeated for every retriever.
    """
    global _chroma_client_cache
    with _chroma_client_lock:
        if _chroma_client_cache is not None:
            return _chroma_client_cache
        try:
            client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            client.heartbeat()
            _chroma_client_cache = (client, "http")
        except Exception:
            local_path = os.path.join(BASE_DIR, "chroma_data")
            os.makedirs(local_path, exist_ok=True)
            _chroma_client_cache = (chromadb.PersistentClient(path=local_path), "local")
        return _chroma_client_cache


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
        # VECTOR_BACKEND=qdrant stores chunks in Qdrant Cloud instead of ChromaDB
        self.store = None
        if config.VECTOR_BACKEND == "qdrant":
            from src.rag.qdrant_store import QdrantStore
            self.store = QdrantStore()
            self.client, self.mode = None, "qdrant"
        else:
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
        records = []
        for doc in documents:
            # Markdown is split on its "## " headings so one chunk never mixes
            # two policy scenarios; other text uses plain word windows.
            if doc.get("file_type") == ".md" or "\n## " in doc["content"]:
                chunks = self._chunk_markdown(doc["content"])
            else:
                chunks = [(doc.get("section", ""), c) for c in self._chunk_document(doc["content"])]
            for i, (section, chunk_text) in enumerate(chunks):
                chunk_id = f"{doc['id']}_{i:04d}"
                metadata = {
                    "title": doc["title"],
                    "source": doc.get("source", doc["title"]),
                    "section": section,
                    "file_type": doc.get("file_type", ""),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                }
                records.append({"id": chunk_id, "text": chunk_text, "metadata": metadata})

        if self.store is not None:
            return self.store.upsert(records)

        collection = self.get_or_create_collection(collection_name)
        for r in records:
            collection.upsert(ids=[r["id"]], documents=[r["text"]], metadatas=[r["metadata"]])
        return len(records)

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
            # README describes the folder; it is not a policy
            if not filename.endswith(".md") or filename.lower() == "readme.md":
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

    def _chunk_markdown(self, text: str) -> list[tuple[str, str]]:
        """
        Split markdown into (section heading, chunk text) pairs, one per "## "
        section. The text before the first "## " is kept as "Overview".
        A section longer than CHUNK_SIZE words is word-split, and every piece
        keeps its heading on the first line so it still says what it is about.
        """
        sections: list[tuple[str, list[str]]] = [("Overview", [])]
        for line in text.splitlines():
            if line.startswith("## "):
                sections.append((line[3:].strip(), []))
            sections[-1][1].append(line)

        chunks = []
        for heading, lines in sections:
            body = "\n".join(lines).strip()
            if not body or body.lstrip("#").strip() == heading:
                continue
            if len(body.split()) <= self.CHUNK_SIZE:
                chunks.append((heading, body))
                continue
            for piece in self._chunk_document(body):
                if not piece.startswith("## "):
                    piece = f"## {heading} (cont.)\n{piece}"
                chunks.append((heading, piece))
        return chunks

    def get_collection_stats(self, collection_name: str | None = None) -> dict:
        """Get statistics about the indexed collection."""
        if self.store is not None:
            return {"collection": self.store.collection, "chunk_count": self.store.count(), "mode": self.mode}
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
        if self.store is not None:
            self.store.delete_collection()
            print(f"Deleted collection: {self.store.collection}")
            return
        name = collection_name or CHROMA_COLLECTION
        try:
            self.client.delete_collection(name)
            print(f"Deleted collection: {name}")
        except Exception:
            pass

    def list_collections(self) -> list[str]:
        """List all collections in ChromaDB (or Qdrant)."""
        try:
            if self.store is not None:
                return [c.name for c in self.store.client.get_collections().collections]
            return [c.name for c in self.client.list_collections()]
        except Exception:
            return []


# Backward-compatible alias
PolicyIndexer = DocumentIndexer
