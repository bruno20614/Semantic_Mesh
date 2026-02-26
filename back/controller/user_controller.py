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

from fastapi import Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from service.jwt_service import create_access_token, verify_access_token
from fastapi.responses import JSONResponse

@router.post("/")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    user = login_user_service(username, password)
    if user:
        access_token = create_access_token({"user_id": user['id'], "username": user['username']})
        request.session['user_id'] = user['id']
        request.session['username'] = user['username']
        request.session['jwt'] = access_token
        # Detecta se é requisição de navegador (HTML) ou API
        accept = request.headers.get('accept', '')
        if 'text/html' in accept:
            return RedirectResponse(url="/dashboard", status_code=302)
        else:
            return JSONResponse({"access_token": access_token})
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



@router.post("/user")
async def create_user(
    username: str = Form(...),
    password: str = Form(...)
):
    result = register_user_service(username, password)
    if result == "success":
        return {"msg": f"Usuário {username} criado com sucesso!"}
    elif result == "exists":
        return {"msg": "Usuário já existe!"}
    else:
        return {"msg": "Erro ao criar usuário."}


from fastapi import Depends
security = HTTPBearer()

@router.put("/user")
async def update_user(
    id: int = Form(...),
    username: str = Form(None),
    password: str = Form(None),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token JWT inválido")
    db = SessionLocal()
    user = db.query(User).filter(User.id == id).first()
    if not user:
        db.close()
        return {"msg": "Usuário não encontrado!"}
    if username:
        user.username = username
    if password:
        user.password = generate_password_hash(password)
    db.commit()
    db.close()
    return {"msg": f"Usuário {id} atualizado com sucesso!"}


@router.delete("/user")
async def delete_user(
    username: str = Form(...),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token JWT inválido")
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).first()
    if user:
        db.delete(user)
        db.commit()
        db.close()
        return {"msg": f"Usuário {username} deletado com sucesso!"}
    db.close()
    return {"msg": "Usuário não encontrado!"}


import sqlite3

from service.orm import SessionLocal, User

@router.get("/users")
async def get_users(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token JWT inválido")
    db = SessionLocal()
    users = db.query(User).all()
    db.close()
    return {"users": [{"id": u.id, "username": u.username} for u in users]}
