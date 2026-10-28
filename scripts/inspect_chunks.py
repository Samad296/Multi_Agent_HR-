import sys
from pathlib import Path

from app.rag.ingest import make_chunks
from app.rag.loaders import extract_text

p = Path(sys.argv[1])
chunks = make_chunks(extract_text(p.name, p.read_bytes()))
for c in chunks:
    print(f"{c['section']!r:40} | {c['text'][:60]}")
print(f"\n{len(chunks)} chunks")