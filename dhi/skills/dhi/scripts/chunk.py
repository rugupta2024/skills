"""Page/section-aware chunking. A chunk never crosses a page/section boundary,
so every chunk maps to exactly one citation target."""

CHUNK_WORDS = 450
OVERLAP_WORDS = 70


def chunk_text(text: str, chunk_words: int = CHUNK_WORDS, overlap_words: int = OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_words:
        return [" ".join(words)]

    chunks = []
    step = chunk_words - overlap_words
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start:start + chunk_words]))
        if start + chunk_words >= len(words):
            break
        start += step
    return chunks


def chunk_units(units: list[dict]) -> list[dict]:
    result = []
    for unit in units:
        for seq, piece in enumerate(chunk_text(unit["text"])):
            result.append({
                "page_number": unit["page_number"],
                "section_label": unit["section_label"],
                "seq_in_page": seq,
                "text": piece,
            })
    return result
