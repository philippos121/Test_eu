from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, get_current_user_from_token_or_query
from ..database import get_db
from ..models import Case, CaseStatus, ChatMessage, Document, MessageRole, User
from ..schemas import DocumentRead
from ..services.form_generator import generate_form_a

router = APIRouter(prefix="/api/cases/{case_id}/documents", tags=["documents"])


@router.get("", response_model=List[DocumentRead])
async def list_documents(
    case_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")

    result = await db.execute(
        select(Document)
        .where(Document.case_id == case_id)
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.post("/generate-form-a", response_model=DocumentRead, status_code=201)
async def generate_form(
    case_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")

    if case.status not in (CaseStatus.FORM_GENERATION, CaseStatus.COMPLETED):
        raise HTTPException(
            status_code=400,
            detail="Der Fall ist noch nicht bereit für die Formularerstellung. "
            "Bitte schließen Sie zuerst die Prüfung ab.",
        )

    filename, filepath = generate_form_a(case)

    doc = Document(
        case_id=case.id,
        filename=filename,
        filepath=filepath,
        doc_type="form_a",
    )
    db.add(doc)

    # Add assistant message about form generation
    msg = ChatMessage(
        case_id=case.id,
        role=MessageRole.ASSISTANT,
        content=(
            f"Das Formblatt A (Klageformblatt) wurde erstellt: **{filename}**\n\n"
            "Bitte laden Sie das Dokument herunter, prüfen Sie es sorgfältig und "
            "reichen Sie es beim zuständigen Gericht ein. Vergessen Sie nicht, "
            "alle Beweismittel als Anlagen beizufügen."
        ),
        step=CaseStatus.FORM_GENERATION,
    )
    db.add(msg)
    case.status = CaseStatus.COMPLETED
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("/{doc_id}/download")
async def download_document(
    case_id: UUID,
    doc_id: UUID,
    user: User = Depends(get_current_user_from_token_or_query),
    db: AsyncSession = Depends(get_db),
):
    # Verify case ownership
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Fall nicht gefunden.")

    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.case_id == case_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden.")

    return FileResponse(
        path=doc.filepath,
        filename=doc.filename,
        media_type="application/pdf",
    )
