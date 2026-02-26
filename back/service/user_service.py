import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

def get_user_by_username_service(username):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    user = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if user:
        return {"id": user[0], "username": user[1], "password": user[2]}
    return None

def login_user_service(username, password):
    user = get_user_by_username_service(username)
    if user and check_password_hash(user['password'], password):
        return user
    return None

def register_user_service(username, password):
    hashed_password = generate_password_hash(password)
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        return "success"
    except sqlite3.IntegrityError:
        return "exists"
    except Exception:
        return "error"
    finally:
        conn.close()
