from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import TenantContext, require_role
from app.db.tenant import tenant_session
from app.rag import ingest
from app.rag.loaders import UnsupportedFile, extract_text
from app.services import audit_service

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_BYTES = 5_000_000
ALLOWED = {".md", ".txt", ".pdf", ".docx"}


@router.post("", status_code=201)
def upload(
    file: UploadFile = File(...),
    access_level: str = Form("all"),
    ctx: TenantContext = Depends(require_role("hr_admin")),
):
    name = Path(file.filename or "").name[:120]          # basename only, no paths
    if Path(name).suffix.lower() not in ALLOWED:
        raise HTTPException(400, "Supported files: .md, .txt, .pdf, .docx")
    if access_level not in ("all", "hr_admin"):
        raise HTTPException(400, "access_level must be 'all' or 'hr_admin'")

    raw = file.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "File is larger than 5 MB")

    try:
        text = extract_text(name, raw)
    except UnsupportedFile as e:
        raise HTTPException(400, str(e))
    if not text.strip():
        raise HTTPException(
            400, "No text found. Scanned PDFs are images and need OCR, which is not supported yet."
        )

    chunks = ingest.ingest_text(ctx, name, text, access_level)
    if chunks == 0:
        raise HTTPException(400, "No text found in the file")

    with tenant_session(ctx) as db:
        audit_service.log(
            db, ctx, "document.upload",
            {"doc_name": name, "chunks": chunks, "access_level": access_level},
        )
    return {"doc_name": name, "chunks": chunks, "access_level": access_level}


@router.get("")
def list_docs(ctx: TenantContext = Depends(require_role("hr_admin"))):
    return ingest.list_documents(ctx)


@router.delete("/{doc_name}", status_code=204)
def delete_doc(doc_name: str, ctx: TenantContext = Depends(require_role("hr_admin"))):
    ingest.delete_document(ctx, doc_name)
    with tenant_session(ctx) as db:
        audit_service.log(db, ctx, "document.delete", {"doc_name": doc_name})