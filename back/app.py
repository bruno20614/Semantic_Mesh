from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import os
from controller.user_controller import router as user_router

app = FastAPI(title="Semantic Mesh API")

app.add_middleware(SessionMiddleware, secret_key="chave_secreta_super_segura_aqui")
app.mount("/static", StaticFiles(directory="../front/static"), name="static")

import sqlite3
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)''')
    conn.commit()
    conn.close()
init_db()

app.include_router(user_router)

if __name__ == '__main__':
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

