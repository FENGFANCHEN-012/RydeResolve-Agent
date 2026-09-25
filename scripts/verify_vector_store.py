"""
Vector store check: runs one policy lookup per dispute type and prints the top
chunks, so you can see at a glance whether retrieval returns the right policy
sections. Read-only.

Usage:
    python scripts/verify_vector_store.py                    # backend from .env
    python scripts/verify_vector_store.py --backend qdrant
    python scripts/verify_vector_store.py --backend chroma --top-k 5
"""
import argparse
import sys
import time

sys.path.insert(0, ".")

from src import config

# One realistic complaint per dispute type (types match DocumentRetriever.retrieve_for_dispute)
QUERIES = {
    "no_show": "Driver marked me as a no-show and charged a fee, but I was waiting at the pickup point.",
    "route_deviation": "The driver took a much longer route than the app showed and I paid more.",
    "fare_dispute": "I was charged more than the fare quoted when I booked the ride.",
    "cancellation_refund": "The driver cancelled on me and I was still charged a cancellation fee.",
    "service_quality": "The driver was rude and drove unsafely during the trip.",
    "safety_incident": "The driver touched me inappropriately and I felt unsafe.",
    "driver_rights": "As a driver I want to appeal a penalty and claim a cleaning fee for vomit in my car.",
}


def main():
    parser = argparse.ArgumentParser(description="Check policy retrieval per dispute type")
    parser.add_argument("--backend", choices=["chroma", "qdrant"], help="Default: VECTOR_BACKEND from .env")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    if args.backend:
        config.VECTOR_BACKEND = args.backend

    from src.rag.retriever import DocumentRetriever
    retriever = DocumentRetriever()
    print(f"Backend: {retriever.mode}\n")

    retriever.retrieve("warm up", top_k=1)  # first call loads models / opens connections
    timings = []
    for dispute_type, complaint in QUERIES.items():
        t0 = time.perf_counter()
        results = retriever.retrieve_for_dispute(dispute_type, complaint, top_k=args.top_k)
        timings.append((time.perf_counter() - t0) * 1000)
        print(f"[{dispute_type}] {complaint}")
        for i, r in enumerate(results, 1):
            print(f"   {i}. {r['source']} > {r['section']}  (score {r['similarity']})")
        print()
    print(f"Average lookup: {sum(timings) / len(timings):.0f} ms over {len(timings)} queries")


if __name__ == "__main__":
    main()
