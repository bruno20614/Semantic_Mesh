from werkzeug.security import generate_password_hash, check_password_hash
from service.orm import SessionLocal, User

def get_user_by_username_service(username):
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).first()
    db.close()
    if user:
        return {"id": user.id, "username": user.username, "password": user.password}
    return None

def login_user_service(username, password):
    user = get_user_by_username_service(username)
    if user and check_password_hash(user['password'], password):
        return user
    return None

def register_user_service(username, password):
    hashed_password = generate_password_hash(password)
    db = SessionLocal()
    try:
        user = User(username=username, password=hashed_password)
        db.add(user)
        db.commit()
        return "success"
    except Exception as e:
        db.rollback()
        if "unique constraint" in str(e).lower():
            return "exists"
        return "error"
    finally:
        db.close()
