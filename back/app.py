from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import uvicorn
import os

app = FastAPI(title="Semantic Mesh API")

# Middleware para gerenciar a sessão do usuário (o "estar logado")
app.add_middleware(SessionMiddleware, secret_key="chave_secreta_super_segura_aqui")

# Configurando as pastas de arquivos estáticos e templates HTML
app.mount("/static", StaticFiles(directory="../front/static"), name="static")
templates = Jinja2Templates(directory="../front/templates")

# Inicializa o banco de dados
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)''')
    conn.commit()
    conn.close()

init_db()

@app.get("/", response_class=HTMLResponse)
async def login_get(request: Request):
    # Se já estiver logado, manda direto para o dashboard
    if 'user_id' in request.session:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    user = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    
    if user and check_password_hash(user[2], password):
        # Salva os dados na sessão
        request.session['user_id'] = user[0]
        request.session['username'] = user[1]
        return RedirectResponse(url="/dashboard", status_code=302)
    else:
        # Retorna a página com mensagem de erro
        return templates.TemplateResponse("login.html", {"request": request, "error": "Usuário ou senha incorretos."})

@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register_post(request: Request, username: str = Form(...), password: str = Form(...)):
    hashed_password = generate_password_hash(password)
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        return templates.TemplateResponse("login.html", {"request": request, "success": "Cadastro realizado com sucesso! Faça login."})
    except sqlite3.IntegrityError:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Este usuário já existe."})
    finally:
        conn.close()

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Bloqueia o acesso se não houver sessão ativa
    if 'user_id' not in request.session:
        return RedirectResponse(url="/", status_code=302)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "username": request.session['username']
    })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)

if __name__ == '__main__':
    # Roda o servidor Uvicorn em modo de desenvolvimento (atualiza sozinho ao salvar)
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)