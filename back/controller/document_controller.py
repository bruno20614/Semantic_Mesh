from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from uuid import UUID
from service.orm import SessionFactory
from service.document_service import save_document_with_content, remove_document

router = APIRouter()
templates = Jinja2Templates(directory="../front/templates")

@router.get("/documents", response_class=HTMLResponse)
def list_documents(request: Request):
    db = SessionFactory.create_session()
    from service.orm import Document, Organization
    docs = db.query(Document).all()
    orgs = {org.id: org.name for org in db.query(Organization).all()}
    db.close()
    return templates.TemplateResponse("documents.html", {"request": request, "documents": docs, "orgs": orgs})

@router.get("/documents/add", response_class=HTMLResponse)
def add_document_form(request: Request):
    db = SessionFactory.create_session()
    from service.orm import Organization
    orgs = db.query(Organization).all()
    db.close()
    return templates.TemplateResponse("documents_add.html", {"request": request, "orgs": orgs})

@router.post("/documents/add", response_class=HTMLResponse)
def add_document(request: Request, org_id: UUID = Form(...), file: UploadFile = File(...)):
    db = SessionFactory.create_session()
    try:
        save_document_with_content(db, org_id, file)
        db.close()
        return RedirectResponse("/documents", status_code=303)
    except Exception as e:
        db.close()
        return templates.TemplateResponse("documents_add.html", {"request": request, "orgs": [], "message": f"Erro ao enviar documento: {str(e)}", "success": False})

@router.post("/documents/{doc_id}/delete")
def delete_document(request: Request, doc_id: UUID):
    db = SessionFactory.create_session()
    from service.orm import Document
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        db.close()
        return RedirectResponse("/documents", status_code=303)
    remove_document(db, doc.organization_id, doc_id)
    db.close()
    return RedirectResponse("/documents", status_code=303)
