import os
from datetime import datetime
from service.orm import Document, DocumentFile, DocumentContent


def save_document_with_content(db, org_id, file):
    file_location = os.path.join("..", "front", "uploads", str(org_id))
    os.makedirs(file_location, exist_ok=True)
    file_path = os.path.join(file_location, file.filename)
    with open(file_path, "wb") as f:
        f.write(file.file.read())
    doc = Document(organization_id=org_id, filename=file.filename, file_type=file.content_type, created_at=datetime.utcnow())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    doc_file = DocumentFile(document_id=doc.id, file_path=file_path, file_hash="", uploaded_at=datetime.utcnow())
    db.add(doc_file)
    # --- Extração de texto ---
    raw_text = ""
    try:
        if file.filename.lower().endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as txtf:
                raw_text = txtf.read()
        elif file.filename.lower().endswith('.pdf'):
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(file_path)
                raw_text = "\n".join(page.extract_text() or '' for page in reader.pages)
            except Exception as e:
                raw_text = f"Erro ao extrair PDF: {str(e)}"
        elif file.filename.lower().endswith('.docx'):
            try:
                import docx
                docx_file = docx.Document(file_path)
                raw_text = "\n".join([p.text for p in docx_file.paragraphs])
            except Exception as e:
                raw_text = f"Erro ao extrair DOCX: {str(e)}"
    except Exception as e:
        raw_text = f"Erro ao extrair texto: {str(e)}"
    if raw_text:
        doc_content = DocumentContent(document_id=doc.id, raw_text=raw_text)
        db.add(doc_content)
    db.commit()
    return doc

# Função para remover documento e arquivos

def remove_document(db, org_id, doc_id):
    doc = db.query(Document).filter(Document.id == doc_id, Document.organization_id == org_id).first()
    if not doc:
        return False
    doc_file = db.query(DocumentFile).filter(DocumentFile.document_id == doc_id).first()
    if doc_file:
        try:
            if os.path.exists(doc_file.file_path):
                os.remove(doc_file.file_path)
        except Exception:
            pass
        db.delete(doc_file)
    doc_content = db.query(DocumentContent).filter(DocumentContent.document_id == doc_id).first()
    if doc_content:
        db.delete(doc_content)
    db.delete(doc)
    db.commit()
    return True
