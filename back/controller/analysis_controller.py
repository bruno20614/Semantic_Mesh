from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from service.orm import SessionLocal, AnalysisRun, Organization, User, DocumentSimilarity, Cluster, DocumentSummary, DocumentComparison, Document
import uuid

router = APIRouter()
templates = Jinja2Templates(directory="../front/templates")


@router.get("/analysis", response_class=HTMLResponse)
def list_analysis_runs(request: Request):
    if 'user_id' not in request.session:
        return RedirectResponse("/", status_code=302)
    user_id = request.session['user_id']
    db = SessionLocal()
    try:
        import uuid as uuid_mod
        try:
            user_uuid = uuid_mod.UUID(str(user_id))
        except Exception:
            user_uuid = user_id
        from service.orm import UserOrganization
        org_ids = [uo.organization_id for uo in db.query(UserOrganization).filter(UserOrganization.user_id == user_uuid).all()]
        runs = db.query(AnalysisRun).filter(AnalysisRun.organization_id.in_(org_ids)).order_by(AnalysisRun.created_at.desc()).all()
        orgs = {str(org.id): org.name for org in db.query(Organization).all()}
        users = {str(u.id): u.name for u in db.query(User).all()}

        runs_data = []
        for run in runs:
            run_id = run.id
            similarities_count = db.query(DocumentSimilarity).filter(DocumentSimilarity.analysis_run_id == run_id).count()
            clusters_count = db.query(Cluster).filter(Cluster.analysis_run_id == run_id).count()
            summaries_count = db.query(DocumentSummary).filter(DocumentSummary.analysis_run_id == run_id).count()
            comparisons_count = db.query(DocumentComparison).filter(DocumentComparison.analysis_run_id == run_id).count()
            doc_count = db.query(Document).filter(Document.organization_id == run.organization_id).count()

            runs_data.append({
                "id": str(run.id),
                "org_name": orgs.get(str(run.organization_id), "N/A"),
                "created_by": users.get(str(run.created_by), "N/A"),
                "parameters": run.parameters or {},
                "created_at": run.created_at,
                "similarities": similarities_count,
                "clusters": clusters_count,
                "summaries": summaries_count,
                "comparisons": comparisons_count,
                "doc_count": doc_count,
            })
    finally:
        db.close()

    return templates.TemplateResponse("analysis_runs.html", {
        "request": request,
        "runs": runs_data,
    })


@router.get("/analysis/new", response_class=HTMLResponse)
def new_analysis_form(request: Request):
    if 'user_id' not in request.session:
        return RedirectResponse("/", status_code=302)
    user_id = request.session['user_id']
    db = SessionLocal()
    try:
        from service.orm import UserOrganization
        org_ids = [uo.organization_id for uo in db.query(UserOrganization).filter(UserOrganization.user_id == user_id).all()]
        orgs = db.query(Organization).filter(Organization.id.in_(org_ids)).all()
    finally:
        db.close()
    return templates.TemplateResponse("analysis_new.html", {
        "request": request,
        "orgs": orgs,
    })


@router.post("/analysis/new")
def create_analysis_run(
    request: Request,
    org_id: str = Form(...),
    model: str = Form("sem_modelo"),
    similarity_threshold: float = Form(0.75),
    max_clusters: int = Form(5),
):
    if 'user_id' not in request.session:
        return RedirectResponse("/", status_code=302)
    user_id = request.session['user_id']
    db = SessionLocal()
    try:
        from service.orm import UserOrganization
        import uuid as uuid_mod

        try:
            org_uuid = uuid_mod.UUID(org_id)
            user_uuid = uuid_mod.UUID(str(user_id))
        except Exception:
            org_uuid = org_id
            user_uuid = user_id

        membership = db.query(UserOrganization).filter(
            UserOrganization.user_id == user_uuid,
            UserOrganization.organization_id == org_uuid
        ).first()

        org_ids = [uo.organization_id for uo in db.query(UserOrganization).filter(UserOrganization.user_id == user_uuid).all()]
        orgs = db.query(Organization).filter(Organization.id.in_(org_ids)).all()

        if not membership:
            return templates.TemplateResponse("analysis_new.html", {
                "request": request,
                "orgs": orgs,
                "error": "Você não tem acesso a esta organização.",
            })

        doc_count = db.query(Document).filter(Document.organization_id == org_uuid).count()
        if doc_count == 0:
            return templates.TemplateResponse("analysis_new.html", {
                "request": request,
                "orgs": orgs,
                "error": "Esta organização não possui documentos. Adicione documentos antes de criar uma análise.",
            })

        run = AnalysisRun(
            organization_id=org_uuid,
            created_by=user_uuid,
            parameters={
                "model": model,
                "similarity_threshold": similarity_threshold,
                "max_clusters": max_clusters,
            },
        )
        db.add(run)
        db.commit()
    finally:
        db.close()

    return RedirectResponse("/analysis", status_code=303)
