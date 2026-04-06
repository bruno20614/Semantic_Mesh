from service.orm import SessionLocal, Organization, UserOrganization
from sqlalchemy.exc import SQLAlchemyError

def create_organization_service(name):
    db = SessionLocal()
    try:
        org = Organization(name=name)
        db.add(org)
        db.commit()
        db.refresh(org)
        return org
    except SQLAlchemyError as e:
        db.rollback()
        return None
    finally:
        db.close()

def list_organizations_service():
    db = SessionLocal()
    try:
        orgs = db.query(Organization).all()
        return orgs
    finally:
        db.close()

def update_organization_service(org_id, name):
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            return None
        org.name = name
        db.commit()
        db.refresh(org)
        return org
    except SQLAlchemyError:
        db.rollback()
        return None
    finally:
        db.close()

def delete_organization_service(org_id):
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            return False
        db.delete(org)
        db.commit()
        return True
    except SQLAlchemyError:
        db.rollback()
        return False
    finally:
        db.close()

def add_user_to_organization_service(user_id, org_id, role="member"):
    db = SessionLocal()
    try:
        # Verifica se já existe relação
        existing = db.query(UserOrganization).filter_by(user_id=user_id, organization_id=org_id).first()
        if existing:
            return True
        user_org = UserOrganization(user_id=user_id, organization_id=org_id, role=role)
        db.add(user_org)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()

def remove_user_from_organization_service(user_id, org_id):
    db = SessionLocal()
    try:
        user_org = db.query(UserOrganization).filter_by(user_id=user_id, organization_id=org_id).first()
        if not user_org:
            return False
        db.delete(user_org)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()
