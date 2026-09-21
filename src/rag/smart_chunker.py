"""
Smart Document Chunking
Chunks documents at semantic boundaries (paragraphs, sections)
instead of fixed word counts. Adds contextual summaries.
"""
import re
import uuid


class SmartChunker:
    """
    Semantic-aware document chunker.
    - Respects paragraph and section boundaries
    - Adds parent document context to each chunk
    - Generates chunk summaries for better retrieval
    """

    def __init__(self, max_chunk_size: int = 800, overlap_size: int = 100):
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size

    def chunk(self, text: str, doc_title: str = "", doc_source: str = "") -> list[dict]:
        """
        Split text into semantic chunks with metadata.

        Returns:
            List of dicts: {text, summary, start_pos, end_pos, parent_doc}
        """
        # Split into semantic units (paragraphs/sections)
        units = self._split_into_units(text)

        chunks = []
        current_chunk = []
        current_size = 0

        for unit in units:
            unit_size = len(unit.split())

            if current_size + unit_size > self.max_chunk_size and current_chunk:
                # Save current chunk
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(self._create_chunk(chunk_text, doc_title, doc_source))

                # Start new chunk with overlap
                overlap_words = self._get_overlap(current_chunk)
                current_chunk = overlap_words + [unit]
                current_size = len(" ".join(current_chunk).split())
            else:
                current_chunk.append(unit)
                current_size += unit_size

        # Don't forget the last chunk
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(self._create_chunk(chunk_text, doc_title, doc_source))

        return chunks

    def _split_into_units(self, text: str) -> list[str]:
        """Split text into semantic units (paragraphs/sections)."""
        # Split on double newlines (paragraphs)
        units = [u.strip() for u in re.split(r'\n\s*\n', text) if u.strip()]

        # Further split very long paragraphs at sentence boundaries
        result = []
        for unit in units:
            if len(unit.split()) > self.max_chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', unit)
                result.extend(s for s in sentences if s.strip())
            else:
                result.append(unit)

        return result

    def _get_overlap(self, chunks: list[str]) -> list[str]:
        """Get overlapping text from previous chunk."""
        if not chunks or self.overlap_size <= 0:
            return []

        overlap_text = " ".join(chunks[-2:]) if len(chunks) >= 2 else chunks[-1]
        words = overlap_text.split()
        overlap_words = words[-self.overlap_size:] if len(words) > self.overlap_size else words
        return [" ".join(overlap_words)]

    def _create_chunk(self, text: str, doc_title: str, doc_source: str) -> dict:
        """Create a chunk dict with metadata."""
        # Generate a simple summary (first sentence or first 100 chars)
        summary = self._generate_summary(text)

        return {
            "id": f"chunk_{uuid.uuid4().hex[:8]}",
            "text": text,
            "summary": summary,
            "parent_doc": doc_title or doc_source,
            "word_count": len(text.split()),
        }

    def _generate_summary(self, text: str, max_len: int = 150) -> str:
        """Generate a brief summary of the chunk."""
        # Use first sentence if available
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if sentences:
            first = sentences[0].strip()
            if len(first) <= max_len:
                return first
            return first[:max_len] + "..."
        return text[:max_len] + "..." if len(text) > max_len else text


class ContextualChunker(SmartChunker):
    """
    Adds parent document context prefix to each chunk.
    Helps the embedding model understand the chunk's context.
    """

    def chunk(self, text: str, doc_title: str = "", doc_source: str = "") -> list[dict]:
        """Chunk with contextual prefix."""
        chunks = super().chunk(text, doc_title, doc_source)

        # Add context prefix to each chunk
        context_prefix = f"Document: {doc_title or doc_source}\n\n" if (doc_title or doc_source) else ""

        for chunk in chunks:
            chunk["text"] = context_prefix + chunk["text"]

        return chunks


# Singleton
smart_chunker = SmartChunker()
contextual_chunker = ContextualChunker()
