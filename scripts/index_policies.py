"""
RAG Indexing Script
Indexes all Ryde policy documents into ChromaDB.

Usage:
    python scripts/index_policies.py          # Index all policies
    python scripts/index_policies.py --clear  # Clear and re-index
    python scripts/index_policies.py --stats  # Show collection stats
"""
import sys
import argparse

# Ensure project root is in path
sys.path.insert(0, ".")

from src.rag.indexer import PolicyIndexer


def main():
    parser = argparse.ArgumentParser(description="Index Ryde policy documents into ChromaDB")
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

    indexer = PolicyIndexer()

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

    print(f"\nIndexing into ChromaDB (collection: {indexer.get_or_create_collection().name})...")
    count = indexer.index_documents(docs)
    print(f"\nIndexed {count} chunks total.")

    stats = indexer.get_collection_stats()
    print(f"Collection stats: {stats}")


if __name__ == "__main__":
    main()
