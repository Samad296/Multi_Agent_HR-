import os
import tempfile
from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader


class UnsupportedFile(ValueError):
    """Message is written for the end user, so it is safe to return in the API."""


SIGNATURES = {".pdf": b"%PDF", ".docx": b"PK"}   # a .docx is a zip file


def extract_text(filename: str, raw: bytes) -> str:
    ext = Path(filename).suffix.lower()

    if ext in (".md", ".txt"):
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise UnsupportedFile("Text files must be UTF-8")

    if ext not in SIGNATURES:
        raise UnsupportedFile("Supported files: .md, .txt, .pdf, .docx")
    if not raw.startswith(SIGNATURES[ext]):
        raise UnsupportedFile("File content does not match its extension")

    fd, path = tempfile.mkstemp(suffix=ext)       # random name, never the user's filename
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        loader = PyPDFLoader(path) if ext == ".pdf" else Docx2txtLoader(path)
        docs = loader.load()
    except Exception as e:
        raise UnsupportedFile("Could not read the file (it may be corrupted or password-protected)") from e
    finally:
        Path(path).unlink(missing_ok=True)

    return "\n".join(d.page_content for d in docs)