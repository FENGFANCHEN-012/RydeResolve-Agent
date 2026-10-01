"""Policy section tags (data/policies/official/policy_tags.json) and their chunk metadata."""
import json
import os
import re

import pytest

from src.rag.indexer import POLICY_TAGS_FILE, DocumentIndexer

OFFICIAL = os.path.join(os.path.dirname(__file__), "..", "data", "policies", "official")
TAGS_PATH = os.path.join(OFFICIAL, POLICY_TAGS_FILE)
ALLOWED_TYPES = {"route_deviation", "no_show", "fare_dispute", "cancellation_refund", "service_quality",
                 "delivery_dispute", "driver_rights", "accident_liability", "general", "none"}


def test_tags_become_readable_fields_and_boolean_flags():
    meta = DocumentIndexer._tag_metadata({"dispute_types": ["no_show", "cancellation_refund"], "audience": "rider"})
    assert meta == {"dispute_types": "no_show,cancellation_refund", "audience": "rider",
                    "dt_no_show": True, "dt_cancellation_refund": True}


def test_untagged_section_gets_no_flags():
    assert DocumentIndexer._tag_metadata(None) == {}


def test_chunks_carry_their_section_tags():
    doc = {"id": "d", "title": "D", "source": "d.md", "file_type": ".md",
           "content": "# D\n\n## Waiting time\nDrivers wait 5 minutes.\n\n## Privacy\nWe keep data.",
           "tags": {"Waiting time": {"dispute_types": ["no_show"], "audience": "both"}}}
    indexer = DocumentIndexer.__new__(DocumentIndexer)  # no vector store needed
    records = []
    indexer.store = type("S", (), {"upsert": lambda self, r: records.extend(r) or len(r)})()
    indexer.index_documents([doc])
    by_section = {r["metadata"]["section"]: r["metadata"] for r in records}
    assert by_section["Waiting time"]["dt_no_show"] is True
    assert "dt_no_show" not in by_section["Privacy"]


@pytest.mark.skipif(not os.path.exists(TAGS_PATH), reason="no tags file yet")
def test_every_official_section_is_tagged_with_allowed_values():
    tags = json.load(open(TAGS_PATH, encoding="utf-8"))
    for name in sorted(os.listdir(OFFICIAL)):
        if not name.endswith(".md") or name.lower() == "readme.md":
            continue
        text = open(os.path.join(OFFICIAL, name), encoding="utf-8").read()
        headings = [m.strip() for m in re.findall(r"^## (.+)$", text, flags=re.M)]
        for h in headings:
            assert h in tags.get(name, {}), (name, h)
        for section, t in tags.get(name, {}).items():
            assert set(t["dispute_types"]) <= ALLOWED_TYPES, (name, section)
            assert t["dispute_types"], (name, section)
            assert t["audience"] in {"rider", "driver", "both"}, (name, section)
