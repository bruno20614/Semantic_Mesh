from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from werkzeug.security import generate_password_hash, check_password_hash
from service.user_service import (
    login_user_service, register_user_service, get_user_by_username_service
)

router = APIRouter()
templates = Jinja2Templates(directory="../front/templates")

@router.get("/", response_class=HTMLResponse)
async def login_get(request: Request):
    if 'user_id' in request.session:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    user = login_user_service(username, password)
    if user:
        request.session['user_id'] = user['id']
        request.session['username'] = user['username']
        return RedirectResponse(url="/dashboard", status_code=302)
    else:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Usuário ou senha incorretos."})

@router.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register")
async def register_post(request: Request, username: str = Form(...), password: str = Form(...)):
    result = register_user_service(username, password)
    if result == "success":
        return templates.TemplateResponse("login.html", {"request": request, "success": "Cadastro realizado com sucesso! Faça login."})
    elif result == "exists":
        return templates.TemplateResponse("register.html", {"request": request, "error": "Este usuário já existe."})
    else:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Erro ao cadastrar."})

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if 'user_id' not in request.session:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": request.session['username']
    })

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)
