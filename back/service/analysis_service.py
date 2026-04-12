"""
Serviço de análise semântica — TF-IDF + cosine similarity (Python puro, sem dependências ML).
Pipeline:
  1. Busca textos de todos os documentos da organização
  2. Gera vetores TF-IDF
  3. Calcula similaridade cosseno para todos os pares
  4. Salva DocumentSimilarity
  5. Agrupa por threshold via Union-Find → salva Cluster + ClusterDocument
"""
import re
import math
from collections import Counter, defaultdict

from service.orm import (
    AnalysisRun, Document, DocumentContent,
    DocumentSimilarity, Cluster, ClusterDocument,
)


# ── tokenização simples (português + inglês) ──────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r'\b[a-záéíóúàâêôãõçü]{3,}\b', text.lower())


# ── TF-IDF ────────────────────────────────────────────────────────────────────

def _build_tfidf(documents: list[tuple]) -> dict:
    """
    documents: [(doc_id, text), ...]
    Retorna: {doc_id: {term: tfidf_weight}}
    """
    tokenized = [(doc_id, _tokenize(text or "")) for doc_id, text in documents]
    N = len(tokenized)
    if N == 0:
        return {}

    # IDF: número de documentos que contêm cada termo
    df: Counter = Counter()
    for _, tokens in tokenized:
        for term in set(tokens):
            df[term] += 1

    vectors: dict = {}
    for doc_id, tokens in tokenized:
        total = len(tokens) or 1
        tf = Counter(tokens)
        vec: dict = {}
        for term, count in tf.items():
            if df[term] > 0:
                vec[term] = (count / total) * math.log((N + 1) / df[term])
        vectors[doc_id] = vec

    return vectors


def _cosine(v1: dict, v2: dict) -> float:
    if not v1 or not v2:
        return 0.0
    common = set(v1) & set(v2)
    dot = sum(v1[t] * v2[t] for t in common)
    mag1 = math.sqrt(sum(w * w for w in v1.values()))
    mag2 = math.sqrt(sum(w * w for w in v2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return round(dot / (mag1 * mag2), 4)


# ── Union-Find para clustering ─────────────────────────────────────────────────

class _UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)

    def groups(self):
        result = defaultdict(list)
        for x in self.parent:
            result[self.find(x)].append(x)
        return list(result.values())


# ── pipeline principal ────────────────────────────────────────────────────────

def run_analysis(db, run_id) -> dict:
    """
    Executa a análise para um AnalysisRun existente.
    Retorna um dict com contagens de resultados.
    """
    import uuid as uuid_mod

    run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
    if not run:
        return {"error": "AnalysisRun não encontrado"}

    params = run.parameters or {}
    threshold = float(params.get("similarity_threshold", 0.75))
    max_clusters = int(params.get("max_clusters", 10))

    # 1. Busca documentos da organização com texto extraído
    docs = (
        db.query(Document, DocumentContent)
        .outerjoin(DocumentContent, DocumentContent.document_id == Document.id)
        .filter(Document.organization_id == run.organization_id)
        .all()
    )

    doc_texts = []
    for doc, content in docs:
        text = content.raw_text if content else ""
        doc_texts.append((doc.id, text))

    if len(doc_texts) < 2:
        return {"error": "São necessários pelo menos 2 documentos com texto extraído."}

    # 2. TF-IDF
    vectors = _build_tfidf(doc_texts)
    doc_ids = [d[0] for d in doc_texts]

    # 3. Similaridade pares + salvar
    # Limpa resultados antigos do run
    db.query(DocumentSimilarity).filter(DocumentSimilarity.analysis_run_id == run_id).delete()
    old_cluster_ids = [c.id for c in db.query(Cluster).filter(Cluster.analysis_run_id == run_id).all()]
    if old_cluster_ids:
        db.query(ClusterDocument).filter(ClusterDocument.cluster_id.in_(old_cluster_ids)).delete(synchronize_session=False)
    db.query(Cluster).filter(Cluster.analysis_run_id == run_id).delete()

    similarities: list[tuple] = []
    for i in range(len(doc_ids)):
        for j in range(i + 1, len(doc_ids)):
            d1, d2 = doc_ids[i], doc_ids[j]
            score = _cosine(vectors.get(d1, {}), vectors.get(d2, {}))
            similarities.append((d1, d2, score))
            db.add(DocumentSimilarity(
                analysis_run_id=run_id,
                document_id_1=d1,
                document_id_2=d2,
                similarity_score=score,
            ))

    # 4. Clustering via Union-Find
    uf = _UnionFind(doc_ids)
    for d1, d2, score in similarities:
        if score >= threshold:
            uf.union(d1, d2)

    groups = uf.groups()
    # Limita ao max_clusters — agrupa os menores juntos se necessário
    groups.sort(key=len, reverse=True)
    if len(groups) > max_clusters:
        overflow = groups[max_clusters:]
        groups = groups[:max_clusters]
        groups[-1].extend(doc for grp in overflow for doc in grp)

    # Salva clusters
    for idx, group in enumerate(groups, 1):
        cluster = Cluster(
            analysis_run_id=run_id,
            name=f"Cluster {idx}",
        )
        db.add(cluster)
        db.flush()
        for doc_id in group:
            db.add(ClusterDocument(cluster_id=cluster.id, document_id=doc_id))

    db.commit()
    return {
        "similarities": len(similarities),
        "clusters": len(groups),
    }


# ── dados para o grafo ────────────────────────────────────────────────────────

def get_graph_data(db, run_id) -> dict:
    """
    Retorna nodes e edges prontos para o vis-network.
    """
    run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
    if not run:
        return {"nodes": [], "edges": []}

    params = run.parameters or {}
    min_edge = float(params.get("similarity_threshold", 0.1))

    # Monta mapa doc_id → cluster_index (cor)
    clusters = db.query(Cluster).filter(Cluster.analysis_run_id == run_id).all()
    doc_cluster: dict = {}
    cluster_labels: dict = {}
    for idx, cluster in enumerate(clusters):
        cluster_labels[str(cluster.id)] = cluster.name
        for cd in db.query(ClusterDocument).filter(ClusterDocument.cluster_id == cluster.id).all():
            doc_cluster[str(cd.document_id)] = idx

    # Busca documentos
    docs = (
        db.query(Document)
        .filter(Document.organization_id == run.organization_id)
        .all()
    )

    # Paleta de cores para clusters
    palette = [
        "#7c3aed", "#2563eb", "#16a34a", "#dc2626", "#d97706",
        "#0891b2", "#9333ea", "#15803d", "#b91c1c", "#1d4ed8",
    ]

    nodes = []
    doc_name_map: dict = {}
    for doc in docs:
        c_idx = doc_cluster.get(str(doc.id), 0)
        color = palette[c_idx % len(palette)]
        # Encurta nome longo para o nó
        short_name = doc.filename if len(doc.filename) <= 22 else doc.filename[:20] + "…"
        nodes.append({
            "id": str(doc.id),
            "label": short_name,
            "title": doc.filename,   # tooltip com nome completo
            "color": {"background": color, "border": "#1e1b4b"},
            "font": {"color": "#fff", "size": 13, "bold": True},
            "cluster": c_idx,
        })
        doc_name_map[str(doc.id)] = doc.filename

    # Retorna apenas arestas com similaridade > 0 — zeros não têm semântica útil
    sims = (
        db.query(DocumentSimilarity)
        .filter(
            DocumentSimilarity.analysis_run_id == run_id,
            DocumentSimilarity.similarity_score > 0,
        )
        .all()
    )

    edges = []
    for s in sims:
        width = max(1, round(s.similarity_score * 8))
        opacity = 0.3 + s.similarity_score * 0.7
        name1 = doc_name_map.get(str(s.document_id_1), str(s.document_id_1))
        name2 = doc_name_map.get(str(s.document_id_2), str(s.document_id_2))
        edges.append({
            "from": str(s.document_id_1),
            "to": str(s.document_id_2),
            "doc_name_1": name1,
            "doc_name_2": name2,
            "value": s.similarity_score,
            "width": width,
            "label": f"{s.similarity_score:.2f}",
            "font": {"size": 10, "color": "#374151", "strokeWidth": 3, "strokeColor": "#fff"},
            "color": {"color": f"rgba(124,58,237,{opacity:.2f})"},
            "title": f"{name1}  ↔  {name2}\nSimilaridade: {s.similarity_score:.4f}",
        })

    cluster_list = [
        {"name": c.name, "id": str(c.id)}
        for c in clusters
    ]

    return {"nodes": nodes, "edges": edges, "clusters": cluster_list}
