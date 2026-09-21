"""Test script for RAG pipeline: chunking, indexing, and retrieval."""
import sys
sys.path.insert(0, ".")

from src.rag.indexer import PolicyIndexer
from src.rag.retriever import PolicyRetriever


def test_chunking():
    """Test that policy documents load and chunk correctly."""
    indexer = PolicyIndexer()
    docs = indexer._load_policy_files()

    assert len(docs) > 0, "No policy documents found!"
    print(f"[OK] Loaded {len(docs)} policy documents:")

    total_chunks = 0
    for d in docs:
        chunks = indexer._chunk_document(d["content"])
        total_chunks += len(chunks)
        print(f"  - {d['title']}: {len(d['content'])} chars -> {len(chunks)} chunks")

    print(f"\n[OK] Total chunks: {total_chunks}")
    return total_chunks


def test_retrieval():
    """Test that retrieval returns relevant policy clauses."""
    retriever = PolicyRetriever()

    query = "driver took a longer route and I was overcharged"
    results = retriever.retrieve(query, top_k=3)

    if not results:
        print("[SKIP] ChromaDB not running. Start it with: docker-compose up -d chromadb")
        return

    print(f"\n[OK] Retrieval for query: '{query}'")
    for i, r in enumerate(results):
        print(f"  [{i+1}] Source: {r['source']} | Similarity: {r['similarity']}")
        print(f"      Clause: {r['clause'][:120]}...")
        print()


def test_dispute_retrieval():
    """Test dispute-type-aware retrieval."""
    retriever = PolicyRetriever()

    results = retriever.retrieve_for_dispute(
        dispute_type="route_deviation",
        dispute_description="The driver went via Geylang instead of the highway and the fare was $18 instead of the expected $12",
        top_k=3,
    )

    if not results:
        print("[SKIP] ChromaDB not running for dispute retrieval test.")
        return

    print(f"[OK] Dispute-aware retrieval for 'route_deviation':")
    for i, r in enumerate(results):
        print(f"  [{i+1}] Source: {r['source']} | Similarity: {r['similarity']}")
        print(f"      Clause: {r['clause'][:120]}...")
        print()


if __name__ == "__main__":
    print("=" * 60)
    print("RAG Pipeline Test")
    print("=" * 60)

    print("\n--- Test 1: Document Loading & Chunking ---")
    test_chunking()

    print("\n--- Test 2: Policy Retrieval ---")
    test_retrieval()

    print("\n--- Test 3: Dispute-Aware Retrieval ---")
    test_dispute_retrieval()

    print("=" * 60)
    print("All tests completed.")
    print("=" * 60)
