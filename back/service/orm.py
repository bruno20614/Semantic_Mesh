from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Float, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import uuid

DATABASE_URL = "postgresql://postgres:bruno1234@127.0.0.1:5433/semantic_mesh"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    organizations = relationship(
        'UserOrganization',
        back_populates='user',
        cascade="all, delete-orphan",
        passive_deletes=True
    )

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    users = relationship(
        'UserOrganization',
        back_populates='organization',
        cascade="all, delete-orphan",
        passive_deletes=True
    )

class UserOrganization(Base):
    __tablename__ = "user_organization"
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True)
    role = Column(String(50), nullable=False)
    user = relationship('User', back_populates='organizations')
    organization = relationship('Organization', back_populates='users')

class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'))
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class DocumentFile(Base):
    __tablename__ = "document_files"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'))
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

class DocumentContent(Base):
    __tablename__ = "document_contents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'), unique=True)
    raw_text = Column(String, nullable=False)
    cleaned_text = Column(String)
    language = Column(String(50))
    processed_at = Column(DateTime, default=datetime.datetime.utcnow)

class DocumentSection(Base):
    __tablename__ = "document_sections"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'))
    title = Column(String(255))
    content = Column(String, nullable=False)
    section_order = Column(Integer, nullable=False)

class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'))
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    parameters = Column(JSONB)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class DocumentSimilarity(Base):
    __tablename__ = "document_similarities"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    analysis_run_id = Column(UUID(as_uuid=True), ForeignKey('analysis_runs.id', ondelete='CASCADE'))
    document_id_1 = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'))
    document_id_2 = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'))
    similarity_score = Column(Float, nullable=False)

class Cluster(Base):
    __tablename__ = "clusters"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    analysis_run_id = Column(UUID(as_uuid=True), ForeignKey('analysis_runs.id', ondelete='CASCADE'))
    name = Column(String(255), nullable=False)

class ClusterDocument(Base):
    __tablename__ = "cluster_documents"
    cluster_id = Column(UUID(as_uuid=True), ForeignKey('clusters.id', ondelete='CASCADE'), primary_key=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)

class DocumentSummary(Base):
    __tablename__ = "document_summaries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'))
    analysis_run_id = Column(UUID(as_uuid=True), ForeignKey('analysis_runs.id', ondelete='CASCADE'))
    summary_text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class DocumentComparison(Base):
    __tablename__ = "document_comparisons"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    analysis_run_id = Column(UUID(as_uuid=True), ForeignKey('analysis_runs.id', ondelete='CASCADE'))
    document_id_1 = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'))
    document_id_2 = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'))
    differences = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'))
    embedding = Column(String)  # Substitua por um tipo vetorial se disponível
    model_name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Para criar as tabelas:
# Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)