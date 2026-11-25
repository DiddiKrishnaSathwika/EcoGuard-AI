
def split_text_into_chunks(
    text,
    chunk_size=1000,
    chunk_overlap=150
):
    """
    Split document text into overlapping chunks.
    """

    if not text or not text.strip():
        return []

    if chunk_size <= 0:
        raise ValueError("Chunk size must be greater than zero.")

    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(
            "Overlap must be non-negative and smaller than chunk size."
        )

    paragraphs = [
        paragraph.strip()
        for paragraph in text.splitlines()
        if paragraph.strip()
    ]

    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:

        if len(paragraph) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            start = 0

            while start < len(paragraph):
                end = start + chunk_size
                chunks.append(paragraph[start:end])
                start += chunk_size - chunk_overlap

            continue

        candidate = (
            current_chunk + "\n" + paragraph
            if current_chunk else paragraph
        )

        if len(candidate) <= chunk_size:
            current_chunk = candidate

        else:
            if current_chunk:
                chunks.append(current_chunk)

            overlap_words = []
            total_length = 0

            if chunk_overlap > 0:
                for word in reversed(current_chunk.split()):
                    if total_length + len(word) > chunk_overlap:
                        break

                    overlap_words.append(word)
                    total_length += len(word) + 1

            overlap_text = " ".join(reversed(overlap_words))

            current_chunk = (
                overlap_text + "\n" + paragraph
                if overlap_text else paragraph
            )

    if current_chunk:
        chunks.append(current_chunk)

    return [
        chunk.strip()
        for chunk in chunks
        if chunk.strip()
    ]
