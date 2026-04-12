from werkzeug.security import generate_password_hash, check_password_hash
from service.orm import SessionLocal, User

__all__ = [
    'get_user_by_email_service',
    'get_user_by_username_service',
    'login_user_service',
    'register_user_service',
]

def get_user_by_email_service(email):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    db.close()
    if user:
        return {"id": str(user.id), "name": user.name, "email": user.email, "password_hash": user.password_hash}
    return None

def get_user_by_username_service(username):
    db = SessionLocal()
    user = db.query(User).filter(User.name == username).first()
    db.close()
    if user:
        return {"id": str(user.id), "name": user.name, "email": user.email, "password_hash": user.password_hash}
    return None

def login_user_service(email, password):
    user = get_user_by_email_service(email)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None

def register_user_service(name, email, password):
    hashed_password = generate_password_hash(password)
    db = SessionLocal()
    try:
        user = User(name=name, email=email, password_hash=hashed_password)
        db.add(user)
        db.commit()
        return "success"
    except Exception as e:
        db.rollback()
        print(f"[REGISTER ERROR] {e}")
        if "unique" in str(e).lower():
            return "exists"
        return "error"
    finally:
        db.close()
