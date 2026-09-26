"""Swappable local feature-vector and OCI GenAI + Oracle DB vector retrieval."""
import hashlib
import math
import os

DIM = 256


def local_embedding(text):
    """Deterministic lexical feature vector, not a neural embedding."""
    import re
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    features = tokens
    vec = [0.0] * DIM
    for token in features:
        raw = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(raw[:2], "big") % DIM
        vec[index] += 1.0 if raw[2] % 2 else -1.0
    length = math.sqrt(sum(v*v for v in vec))
    return [v / length for v in vec] if length else vec


def cosine(a, b):
    if len(a) != len(b):
        raise ValueError("Vector dimensions differ")
    norm = math.sqrt(sum(v*v for v in a) * sum(v*v for v in b))
    return sum(x*y for x, y in zip(a,b)) / norm if norm else 0.0


def local_search(query, runbooks, limit=2, threshold=.07):
    q = local_embedding(query)
    ranked = [(cosine(q, local_embedding(doc["title"] + " " + doc["text"])), doc)
              for doc in runbooks]
    return [{**doc, "similarity": round(score, 4)} for score, doc in
            sorted(ranked, key=lambda pair: (-pair[0], pair[1]["id"]))[:limit] if score >= threshold]


def oci_embed(texts, input_type, config, compartment, model_id):
    """OCI Generative AI embeddings; model must support SEARCH_QUERY/SEARCH_DOCUMENT."""
    import oci
    client = oci.generative_ai_inference.GenerativeAiInferenceClient(config)
    details = oci.generative_ai_inference.models.EmbedTextDetails(
        compartment_id=compartment, inputs=texts, input_type=input_type, truncate="END",
        serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
            serving_type="ON_DEMAND", model_id=model_id))
    response = client.embed_text(embed_text_details=details).data
    if not response.embeddings or len(response.embeddings) != len(texts):
        raise RuntimeError("OCI embedding result count mismatch")
    return response.embeddings


class OracleVectorStore:
    """Oracle Database 23ai AI Vector Search. Use a dedicated least-privilege schema."""
    def __init__(self):
        import oracledb
        self.db = oracledb.connect(user=os.environ["ORACLE_DB_USER"],
                                   password=os.environ["ORACLE_DB_PASSWORD"],
                                   dsn=os.environ["ORACLE_DB_DSN"])

    def setup(self):
        with self.db.cursor() as cur:
            try:
                cur.execute("CREATE TABLE oci_runbooks (id VARCHAR2(128) PRIMARY KEY, title VARCHAR2(256), "
                            "body CLOB, embedding VECTOR(*, FLOAT32))")
                # Already-existing table is okay; other schema errors must surface.
            except Exception as exc:
                if getattr(exc, "code", None) != 955 and "ORA-00955" not in str(exc):
                    raise
        self.db.commit()

    def upsert(self, documents, embeddings):
        if len(documents) != len(embeddings):
            raise ValueError("Document/embedding count mismatch")
        with self.db.cursor() as cur:
            for doc, embedding in zip(documents, embeddings):
                # JSON vector binds are converted explicitly by Oracle DB 23ai TO_VECTOR.
                import json
                args = {"id": doc["id"], "title": doc["title"], "body": doc["text"],
                        "vec": json.dumps(embedding)}
                cur.execute("UPDATE oci_runbooks SET title=:title, body=:body, embedding=TO_VECTOR(:vec) WHERE id=:id", args)
                if cur.rowcount == 0:
                    cur.execute("INSERT INTO oci_runbooks (id,title,body,embedding) VALUES (:id,:title,:body,TO_VECTOR(:vec))", args)
        self.db.commit()

    def search(self, embedding, limit=2, threshold=.07):
        import json
        with self.db.cursor() as cur:
            cur.execute("SELECT id,title,body,1-VECTOR_DISTANCE(embedding,TO_VECTOR(:query),COSINE) AS similarity "
                        "FROM oci_runbooks ORDER BY similarity DESC FETCH FIRST :lim ROWS ONLY",
                        {"query": json.dumps(embedding), "lim": limit})
            return [{"id": row[0], "title": row[1], "text": row[2].read() if hasattr(row[2], "read") else row[2],
                     "similarity": float(row[3])} for row in cur if row[3] >= threshold]

    def close(self):
        self.db.close()
