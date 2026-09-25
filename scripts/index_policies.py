"""
RAG Indexing Script
Indexes all Ryde policy documents into ChromaDB, or into Qdrant Cloud when
VECTOR_BACKEND=qdrant (set in .env or with --backend).

Usage:
    python scripts/index_policies.py                          # Index all policies
    python scripts/index_policies.py --clear                  # Clear and re-index
    python scripts/index_policies.py --stats                  # Show collection stats
    python scripts/index_policies.py --backend qdrant --clear # Rebuild the shared Qdrant index
"""
import sys
import argparse

# Ensure project root is in path
sys.path.insert(0, ".")

from src import config


def main():
    parser = argparse.ArgumentParser(description="Index Ryde policy documents into the vector store")
    parser.add_argument(
        "--backend",
        choices=["chroma", "qdrant"],
        help="Vector store to use (default: VECTOR_BACKEND from .env)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing collection before indexing",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show collection statistics and exit",
    )
    args = parser.parse_args()
    if args.backend:
        config.VECTOR_BACKEND = args.backend

    from src.rag.indexer import PolicyIndexer
    indexer = PolicyIndexer()
    print(f"Vector backend: {indexer.mode}")

    if args.stats:
        stats = indexer.get_collection_stats()
        print(f"Collection: {stats['collection']}")
        print(f"Chunks indexed: {stats['chunk_count']}")
        return

    if args.clear:
        print("Clearing existing collection...")
        indexer.clear_collection()
        print("Done.\n")

    print("Loading policy documents from data/policies/...")
    docs = indexer._load_policy_files()
    print(f"Found {len(docs)} policy documents:")
    for doc in docs:
        print(f"  - {doc['title']} ({doc['source']})")

    if not docs:
        print("\nNo policy documents found. Ensure data/policies/*.md files exist.")
        return

    print(f"\nIndexing into {indexer.mode} (collection: {indexer.get_collection_stats()['collection']})...")
    count = indexer.index_documents(docs)
    print(f"\nIndexed {count} chunks total.")

    stats = indexer.get_collection_stats()
    print(f"Collection stats: {stats}")


if __name__ == "__main__":
    main()
