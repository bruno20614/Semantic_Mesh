"""
RAG simples para perguntas sobre os documentos de uma análise.

Primeiro corte:
  1. Carrega o texto extraído dos documentos da organização da análise
  2. Quebra textos em chunks
  3. Ranqueia chunks por embedding local, se sentence-transformers estiver disponível
  4. Usa TF-IDF como fallback sem dependência pesada
  5. Retorna uma resposta extrativa com fontes
"""
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache

from service.orm import (
    AnalysisRun, Cluster, ClusterDocument, Document, DocumentContent,
    DocumentSimilarity,
)


DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_STOPWORDS = {
    "aos", "ao", "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "por", "para", "com", "sem", "sobre", "entre", "ate", "até",
    "que", "qual", "quais", "quem", "quando", "onde", "como", "porque",
    "tem", "ter", "existe", "existem", "conteudo", "conteúdo",
    "e", "ou", "mas", "se", "sao", "são", "ser", "foi", "sua", "seu",
    "suas", "seus", "este", "esta", "esse", "essa", "isso", "isto",
    "documento", "documentos", "arquivo", "arquivos", "fale", "fala",
    "falam", "trata", "tratam", "mostrar", "mostre", "sobre",
}


def _tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[_\-./\\]+", " ", normalized)
    tokens = re.findall(r"\b[a-z0-9]{3,}\b", normalized.lower())
    return [token for token in tokens if token not in _STOPWORDS]


def _chunk_text(text: str, size: int = 1100, overlap: int = 180) -> list[str]:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if not clean:
        return []

    chunks = []
    start = 0
    while start < len(clean):
        end = min(start + size, len(clean))
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _cosine_sparse(v1: dict, v2: dict) -> float:
    if not v1 or not v2:
        return 0.0
    common = set(v1) & set(v2)
    dot = sum(v1[t] * v2[t] for t in common)
    mag1 = math.sqrt(sum(w * w for w in v1.values()))
    mag2 = math.sqrt(sum(w * w for w in v2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def _keyword_overlap(question: str, chunk: dict) -> float:
    question_terms = set(_tokenize(question))
    if not question_terms:
        return 0.0

    text_terms = set(_tokenize(chunk["text"]))
    name_terms = set(_tokenize(chunk.get("document_name", "")))
    content_overlap = len(question_terms & text_terms) / len(question_terms)
    filename_overlap = len(question_terms & name_terms) / len(question_terms)
    return min(1.0, content_overlap + filename_overlap * 1.4)


def _filename_score(question: str, document_name: str) -> float:
    question_terms = set(_tokenize(question))
    name_terms = set(_tokenize(document_name))
    if not question_terms or not name_terms:
        return 0.0
    return len(question_terms & name_terms) / len(question_terms)


def _has_specific_question_terms(question: str) -> bool:
    return bool(set(_tokenize(question)))


def _filter_relevant_results(question: str, ranked: list[dict]) -> list[dict]:
    if not ranked or not _has_specific_question_terms(question):
        return ranked

    filtered = [
        item for item in ranked
        if item.get("keyword_overlap", 0) >= 0.2
        or _filename_score(question, item.get("document_name", "")) >= 0.2
    ]
    return filtered


def _normalize_match_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-zA-Z0-9]+", " ", normalized.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _is_similarity_question(question: str) -> bool:
    text = _normalize_match_text(question)
    similarity_terms = (
        "similar", "similaridade", "parecido", "parecida", "parecidos",
        "relacionado", "relacionada", "relacionados", "proximo", "proxima",
        "semelhante", "semelhanca", "similidade", "similiaridade",
    )
    document_terms = ("documento", "arquivo", "pdf", "docx", "contrato")
    return (
        any(term in text for term in similarity_terms)
        and any(term in text for term in document_terms)
    )


def _find_referenced_document(question: str, docs: list[Document]) -> Document | None:
    question_text = _normalize_match_text(question)
    question_terms = set(_tokenize(question))
    best_doc = None
    best_score = 0.0

    for doc in docs:
        filename = doc.filename or ""
        name_text = _normalize_match_text(filename)
        stem_text = _normalize_match_text(re.sub(r"\.[^.]+$", "", filename))

        if name_text and name_text in question_text:
            return doc
        if stem_text and len(stem_text) >= 4 and stem_text in question_text:
            return doc

        name_terms = set(_tokenize(filename))
        if not name_terms:
            continue
        overlap = len(question_terms & name_terms) / len(name_terms)
        if overlap > best_score:
            best_score = overlap
            best_doc = doc

    return best_doc if best_score >= 0.5 else None


def _answer_similarity_question(
    db,
    run_id,
    question: str,
    docs: list[Document],
    cluster_id: str | None,
    allowed_doc_ids: set | None,
    top_k: int,
    min_similarity: float,
    llm_provider: str | None,
) -> dict | None:
    if not _is_similarity_question(question):
        return None

    source_doc = _find_referenced_document(question, docs)
    if not source_doc:
        return {
            "question": question,
            "answer": (
                "Entendi que você quer consultar similaridade entre documentos, "
                "mas não consegui identificar com segurança qual documento foi citado. "
                "Use parte do nome do arquivo exatamente como aparece na análise."
            ),
            "answer_mode": "grafo-similaridade",
            "llm_model": None,
            "sources": [],
            "source_document_ids": [],
            "related_documents": [],
            "retrieval_mode": "document-similarity",
            "cluster_id": cluster_id,
            "expand_neighbors": False,
            "chunks_indexed": 0,
        }

    similarities = (
        db.query(DocumentSimilarity)
        .filter(
            DocumentSimilarity.analysis_run_id == run_id,
            DocumentSimilarity.similarity_score > 0,
        )
        .filter(
            (DocumentSimilarity.document_id_1 == source_doc.id)
            | (DocumentSimilarity.document_id_2 == source_doc.id)
        )
        .order_by(DocumentSimilarity.similarity_score.desc())
        .all()
    )

    doc_names = {str(doc.id): doc.filename for doc in docs}
    allowed_doc_id_strings = (
        {str(doc_id) for doc_id in allowed_doc_ids}
        if allowed_doc_ids is not None
        else None
    )
    related_documents = []
    weak_documents = []
    for item in similarities:
        doc1 = str(item.document_id_1)
        doc2 = str(item.document_id_2)
        related_id = doc2 if doc1 == str(source_doc.id) else doc1
        if allowed_doc_id_strings is not None and related_id not in allowed_doc_id_strings:
            continue
        if related_id not in doc_names:
            continue
        related_item = {
            "source_document_id": str(source_doc.id),
            "source_document_name": source_doc.filename,
            "document_id": related_id,
            "document_name": doc_names[related_id],
            "similarity_score": round(float(item.similarity_score), 4),
        }
        if float(item.similarity_score) >= min_similarity:
            related_documents.append(related_item)
        else:
            weak_documents.append(related_item)
        if len(related_documents) >= top_k:
            break

    if related_documents:
        answer, answer_mode, llm_model, sources, llm_error = _summarize_similar_documents(
            db,
            question,
            source_doc,
            related_documents,
            llm_provider,
        )
        chunks_indexed = len(sources)
    else:
        llm_error = None
        if weak_documents:
            weak_lines = [
                f"{idx}. {item['document_name']} (similaridade {item['similarity_score']:.4f})"
                for idx, item in enumerate(weak_documents[:top_k], 1)
            ]
            answer = (
                f"Não encontrei documentos suficientemente similares a {source_doc.filename} "
                f"acima do limiar da análise ({min_similarity:.2f}).\n\n"
                "Existem apenas relações fracas abaixo do limiar:\n"
                + "\n".join(weak_lines)
            )
        else:
            answer = (
                f"Não encontrei outro documento com similaridade positiva registrada "
                f"para {source_doc.filename} nesta análise."
            )
        answer_mode = "grafo-similaridade"
        llm_model = None
        sources = []
        chunks_indexed = 0

    return {
        "question": question,
        "answer": answer,
        "answer_mode": answer_mode,
        "llm_model": llm_model,
        "sources": sources,
        "source_document_ids": [str(source_doc.id)] + [
            item["document_id"] for item in related_documents
        ],
        "related_documents": related_documents,
        "retrieval_mode": "document-similarity",
        "cluster_id": cluster_id,
        "expand_neighbors": False,
        "chunks_indexed": chunks_indexed,
        "llm_error": llm_error,
    }


def _build_similarity_prompt(
    question: str,
    source_doc: Document,
    related_documents: list[dict],
    reference_sources: list[dict],
    related_sources: list[dict],
) -> str:
    relation_lines = [
        f"- {item['document_name']}: similaridade {item['similarity_score']:.4f}"
        for item in related_documents
    ]
    reference_lines = []
    for idx, item in enumerate(reference_sources, 1):
        reference_lines.append(
            f"[Referência {idx}]\n"
            f"Documento: {item['document_name']}\n"
            f"Trecho:\n{item['text'][:1200]}"
        )
    related_lines = []
    for idx, item in enumerate(related_sources, 1):
        related_lines.append(
            f"[Trecho {idx}]\n"
            f"Documento: {item['document_name']}\n"
            f"Similaridade com {source_doc.filename}: {item['similarity_score']:.4f}\n"
            f"Trecho:\n{item['text'][:1200]}"
        )

    return (
        "Você é um assistente de análise documental do sistema Semantic Mesh.\n"
        "A similaridade entre documentos já foi calculada pelo grafo; não recalcule e não invente scores.\n"
        "Use somente os scores e trechos fornecidos. Não use conhecimento externo.\n"
        "Se os trechos não forem suficientes para descrever um documento, diga que os trechos fornecidos não bastam.\n"
        "Não diga que não há similaridade quando a lista do grafo informar similaridade.\n"
        "Explique separadamente: documento de referência, documentos similares e possível motivo textual da similaridade.\n"
        "Responda em português do Brasil, de forma objetiva.\n\n"
        f"Pergunta do usuário:\n{question}\n\n"
        f"Documento de referência: {source_doc.filename}\n\n"
        "Documentos similares encontrados no grafo:\n"
        f"{chr(10).join(relation_lines)}\n\n"
        "Trechos do documento de referência:\n"
        f"{chr(10).join(reference_lines) if reference_lines else 'Nenhum trecho disponível.'}\n\n"
        "Trechos dos documentos similares:\n"
        f"{chr(10).join(related_lines) if related_lines else 'Nenhum trecho disponível.'}\n\n"
        "Resposta:"
    )


def _summarize_similar_documents(
    db,
    question: str,
    source_doc: Document,
    related_documents: list[dict],
    llm_provider: str | None = None,
) -> tuple[str, str, str | None, list[dict], str | None]:
    related_ids = [item["document_id"] for item in related_documents]
    reference_content = (
        db.query(Document, DocumentContent)
        .join(DocumentContent, DocumentContent.document_id == Document.id)
        .filter(Document.id == source_doc.id)
        .filter(DocumentContent.raw_text.isnot(None))
        .first()
    )
    contents = (
        db.query(Document, DocumentContent)
        .join(DocumentContent, DocumentContent.document_id == Document.id)
        .filter(Document.id.in_(related_ids))
        .filter(DocumentContent.raw_text.isnot(None))
        .all()
    )
    similarity_by_doc = {
        item["document_id"]: item["similarity_score"]
        for item in related_documents
    }

    reference_sources = []
    if reference_content:
        doc, content = reference_content
        for idx, chunk in enumerate(_chunk_text(content.raw_text, size=900, overlap=120)[:2], 1):
            reference_sources.append({
                "document_id": str(doc.id),
                "document_name": doc.filename,
                "chunk_index": idx,
                "text": chunk,
            })

    sources = []
    for doc, content in contents:
        chunks = _chunk_text(content.raw_text, size=900, overlap=120)
        for idx, chunk in enumerate(chunks[:2], 1):
            sources.append({
                "document_id": str(doc.id),
                "document_name": doc.filename,
                "chunk_index": idx,
                "text": chunk,
                "score": similarity_by_doc.get(str(doc.id), 0.0),
                "similarity_score": similarity_by_doc.get(str(doc.id), 0.0),
            })

    graph_lines = [
        f"{idx}. {item['document_name']} (similaridade {item['similarity_score']:.4f})"
        for idx, item in enumerate(related_documents, 1)
    ]
    graph_summary = (
        f"Pelo grafo de similaridade, {source_doc.filename} tem similaridade registrada com:\n"
        + "\n".join(graph_lines)
    )

    if sources:
        try:
            from service.llm_service import generate_llm_response

            llm_result = generate_llm_response(
                _build_similarity_prompt(
                    question,
                    source_doc,
                    related_documents,
                    reference_sources,
                    sources,
                ),
                provider=llm_provider,
            )
            if llm_result.get("ok"):
                return (
                    f"{graph_summary}\n\n{llm_result['text']}",
                    f"grafo-similaridade+{llm_result.get('provider', 'llm')}",
                    llm_result.get("model"),
                    sources,
                    None,
                )
            llm_error = llm_result.get("error")
        except Exception as exc:
            llm_error = str(exc)
    else:
        llm_error = None

    lines = [
        f"Documentos mais similares a {source_doc.filename}:",
        "",
    ]
    for idx, item in enumerate(related_documents, 1):
        lines.append(
            f"{idx}. {item['document_name']} "
            f"(similaridade {item['similarity_score']:.4f})"
        )
        excerpt = next(
            (source["text"][:320].strip() for source in sources if source["document_id"] == item["document_id"]),
            "",
        )
        if excerpt:
            lines.append(f"   Trecho inicial: {excerpt}...")
    return "\n".join(lines), "grafo-similaridade", None, sources, llm_error


def _rerank(
    question: str,
    ranked: list[dict],
    base_weight: float,
    overlap_weight: float,
    filename_weight: float,
) -> list[dict]:
    if not ranked:
        return []

    max_score = max((item.get("score", 0.0) for item in ranked), default=0.0) or 1.0
    reranked = []
    for item in ranked:
        base_score = max(item.get("score", 0.0), 0.0) / max_score
        overlap = _keyword_overlap(question, item)
        filename = _filename_score(question, item.get("document_name", ""))
        final_score = (
            (base_score * base_weight)
            + (overlap * overlap_weight)
            + (filename * filename_weight)
        )
        reranked.append({
            **item,
            "base_score": item.get("score", 0.0),
            "score": round(final_score, 4),
            "keyword_overlap": round(overlap, 4),
        })

    reranked.sort(key=lambda item: item["score"], reverse=True)
    return reranked


def _tfidf_rank(question: str, chunks: list[dict], top_k: int) -> tuple[list[dict], str]:
    documents = [question] + [
        f"{chunk.get('document_name', '')} {chunk['text']}"
        for chunk in chunks
    ]
    tokenized = [_tokenize(text) for text in documents]
    total_docs = len(tokenized)

    df = Counter()
    for tokens in tokenized:
        for term in set(tokens):
            df[term] += 1

    def vector(tokens: list[str]) -> dict:
        total = len(tokens) or 1
        tf = Counter(tokens)
        return {
            term: (count / total) * math.log((total_docs + 1) / df[term])
            for term, count in tf.items()
            if df[term] > 0
        }

    question_vec = vector(tokenized[0])
    ranked = []
    for chunk, tokens in zip(chunks, tokenized[1:]):
        score = _cosine_sparse(question_vec, vector(tokens))
        ranked.append({**chunk, "score": round(score, 4)})

    ranked = _rerank(
        question,
        ranked,
        base_weight=0.55,
        overlap_weight=0.3,
        filename_weight=0.45,
    )
    return ranked[:top_k], "tfidf-hibrido"


@lru_cache(maxsize=1)
def _load_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(DEFAULT_MODEL)


def _embedding_rank(question: str, chunks: list[dict], top_k: int) -> tuple[list[dict], str]:
    try:
        import numpy as np

        model = _load_embedding_model()
        texts = [question] + [
            f"Documento: {chunk.get('document_name', '')}\nTrecho: {chunk['text']}"
            for chunk in chunks
        ]
        embeddings = model.encode(texts, normalize_embeddings=True)
        question_vec = embeddings[0]
        chunk_vecs = embeddings[1:]
        scores = np.dot(chunk_vecs, question_vec)

        ranked = [
            {**chunk, "score": round(float(score), 4)}
            for chunk, score in zip(chunks, scores)
        ]
        ranked = _rerank(
            question,
            ranked,
            base_weight=0.65,
            overlap_weight=0.28,
            filename_weight=0.22,
        )
        return ranked[:top_k], "sentence-transformers-hibrido"
    except Exception:
        return _tfidf_rank(question, chunks, top_k)


def _build_prompt(question: str, results: list[dict]) -> str:
    context_parts = []
    for idx, item in enumerate(results[:5], 1):
        context_parts.append(
            f"[Fonte {idx}]\n"
            f"Documento: {item['document_name']}\n"
            f"Chunk: {item['chunk_index']}\n"
            f"Trecho:\n{item['text'][:1500]}"
        )

    context = "\n\n".join(context_parts)
    return (
        "Você é um assistente de análise documental do sistema Semantic Mesh.\n"
        "Responda em português do Brasil usando apenas o contexto fornecido.\n"
        "O contexto pode conter documentos em outros idiomas; traduza e sintetize em português quando necessário.\n"
        "Se o contexto não for suficiente, diga claramente que não há evidência suficiente.\n"
        "Não invente informações. Cite os documentos usados pelo nome.\n\n"
        f"Pergunta do usuário:\n{question}\n\n"
        f"Contexto recuperado:\n{context}\n\n"
        "Resposta:"
    )


def _build_answer(
    question: str,
    results: list[dict],
    llm_provider: str | None = None,
) -> tuple[str, str, str | None, str | None]:
    useful = [item for item in results if item["score"] > 0]
    if not useful:
        return (
            "Não encontrei trechos relevantes o suficiente nos documentos desta análise "
            "para responder com confiança.",
            "extrativo",
            None,
            None,
        )

    try:
        from service.llm_service import generate_llm_response

        llm_result = generate_llm_response(_build_prompt(question, useful), provider=llm_provider)
        if llm_result.get("ok"):
            return llm_result["text"], llm_result.get("provider", "llm"), llm_result.get("model"), None
        llm_error = llm_result.get("error")
    except Exception as exc:
        llm_error = str(exc)

    parts = [
        "Resposta baseada nos trechos mais relevantes encontrados nos documentos:",
    ]
    for idx, item in enumerate(useful[:3], 1):
        excerpt = item["text"][:420].strip()
        if len(item["text"]) > 420:
            excerpt += "..."
        parts.append(f"{idx}. {excerpt}")
    return "\n\n".join(parts), "extrativo", None, llm_error


def _cluster_doc_ids(db, cluster_id: str | None) -> set | None:
    if not cluster_id:
        return None
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        return set()
    return {
        cd.document_id
        for cd in db.query(ClusterDocument)
        .filter(ClusterDocument.cluster_id == cluster.id)
        .all()
    }


def _graph_neighbors(
    db,
    run_id,
    seed_doc_ids: set,
    min_similarity: float,
    limit_per_doc: int = 3,
) -> list[dict]:
    if not seed_doc_ids:
        return []
    seed_doc_ids = {str(doc_id) for doc_id in seed_doc_ids}

    similarities = (
        db.query(DocumentSimilarity)
        .filter(
            DocumentSimilarity.analysis_run_id == run_id,
            DocumentSimilarity.similarity_score >= min_similarity,
        )
        .order_by(DocumentSimilarity.similarity_score.desc())
        .all()
    )

    neighbors = []
    counts = Counter()
    for item in similarities:
        doc1 = str(item.document_id_1)
        doc2 = str(item.document_id_2)
        if doc1 in seed_doc_ids and doc2 not in seed_doc_ids:
            source_id, neighbor_id = doc1, doc2
        elif doc2 in seed_doc_ids and doc1 not in seed_doc_ids:
            source_id, neighbor_id = doc2, doc1
        else:
            continue

        if counts[source_id] >= limit_per_doc:
            continue

        neighbors.append({
            "source_document_id": source_id,
            "document_id": neighbor_id,
            "similarity_score": round(float(item.similarity_score), 4),
        })
        counts[source_id] += 1
    return neighbors


def _apply_neighbor_boost(results: list[dict], neighbor_ids: set) -> list[dict]:
    boosted = []
    for item in results:
        score = item["score"]
        is_neighbor = item["document_id"] in neighbor_ids
        boosted.append({
            **item,
            "graph_neighbor": is_neighbor,
            "score": round(score + (0.08 if is_neighbor else 0), 4),
        })
    boosted.sort(key=lambda item: item["score"], reverse=True)
    return boosted


def ask_documents(
    db,
    run_id,
    question: str,
    top_k: int = 5,
    cluster_id: str | None = None,
    expand_neighbors: bool = False,
    llm_provider: str | None = None,
) -> dict:
    question = (question or "").strip()
    if not question:
        return {"error": "Digite uma pergunta para consultar os documentos."}

    run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
    if not run:
        return {"error": "Análise não encontrada."}

    similarity_threshold = float((run.parameters or {}).get("similarity_threshold", 0.75))

    allowed_doc_ids = _cluster_doc_ids(db, cluster_id)
    if allowed_doc_ids == set():
        return {"error": "Cluster não encontrado ou sem documentos."}

    docs_for_similarity_query = db.query(Document).filter(
        Document.organization_id == run.organization_id
    )
    if allowed_doc_ids is not None:
        docs_for_similarity_query = docs_for_similarity_query.filter(
            Document.id.in_(allowed_doc_ids)
        )
    docs_for_similarity = docs_for_similarity_query.all()

    similarity_answer = _answer_similarity_question(
        db,
        run_id,
        question,
        docs_for_similarity,
        cluster_id,
        allowed_doc_ids,
        top_k,
        similarity_threshold,
        llm_provider,
    )
    if similarity_answer:
        return similarity_answer

    docs_query = (
        db.query(Document, DocumentContent)
        .join(DocumentContent, DocumentContent.document_id == Document.id)
        .filter(Document.organization_id == run.organization_id)
        .filter(DocumentContent.raw_text.isnot(None))
    )
    if allowed_doc_ids is not None:
        docs_query = docs_query.filter(Document.id.in_(allowed_doc_ids))
    docs = docs_query.all()

    chunks = []
    for doc, content in docs:
        for idx, chunk in enumerate(_chunk_text(content.raw_text), 1):
            chunks.append({
                "document_id": str(doc.id),
                "document_name": doc.filename,
                "chunk_index": idx,
                "text": chunk,
            })

    if not chunks:
        return {
            "error": "Nenhum texto extraído foi encontrado para os documentos desta análise."
        }

    results, mode = _embedding_rank(question, chunks, top_k)
    results = _filter_relevant_results(question, results)
    if not results:
        return {
            "question": question,
            "answer": (
                "Não encontrei fontes com aderência textual suficiente à pergunta. "
                "Tente usar um termo que apareça no nome ou no texto do documento."
            ),
            "answer_mode": "extrativo",
            "llm_model": None,
            "sources": [],
            "source_document_ids": [],
            "related_documents": [],
            "retrieval_mode": mode,
            "cluster_id": cluster_id,
            "expand_neighbors": expand_neighbors,
            "chunks_indexed": len(chunks),
            "llm_error": None,
        }
    related_documents = []
    if expand_neighbors:
        top_result = results[0] if results else None
        top_keyword_overlap = top_result.get("keyword_overlap", 0) if top_result else 0
        seed_doc_ids = (
            {top_result["document_id"]}
            if top_result and top_result.get("score", 0) > 0 and top_keyword_overlap >= 0.2
            else set()
        )
        neighbor_min_similarity = max(similarity_threshold, 0.20)
        if _is_similarity_question(question):
            neighbor_min_similarity = similarity_threshold
        related_documents = _graph_neighbors(
            db,
            run_id,
            {item for item in seed_doc_ids},
            neighbor_min_similarity,
        )
        neighbor_ids = {item["document_id"] for item in related_documents}
        results = _apply_neighbor_boost(results, neighbor_ids)
        if related_documents:
            doc_ids = {item["document_id"] for item in related_documents}
            doc_names = {
                str(doc.id): doc.filename
                for doc in db.query(Document)
                .filter(Document.organization_id == run.organization_id)
                .all()
            }
            for item in related_documents:
                item["document_name"] = doc_names.get(item["document_id"], item["document_id"])
                item["source_document_name"] = doc_names.get(
                    item["source_document_id"],
                    item["source_document_id"],
                )

    results = results[:top_k]
    answer, answer_mode, llm_model, llm_error = _build_answer(
        question,
        results,
        llm_provider=llm_provider,
    )
    return {
        "question": question,
        "answer": answer,
        "answer_mode": answer_mode,
        "llm_model": llm_model,
        "sources": results,
        "source_document_ids": sorted({item["document_id"] for item in results}),
        "related_documents": related_documents,
        "retrieval_mode": mode,
        "cluster_id": cluster_id,
        "expand_neighbors": expand_neighbors,
        "chunks_indexed": len(chunks),
        "llm_error": llm_error,
    }
