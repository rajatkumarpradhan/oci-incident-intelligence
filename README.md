# OCI Incident Intelligence

> **Independent portfolio simulation** · Runnable offline · Optional OCI inference and Oracle DB integrations require your own tenancy and are **not live-tested**. No real incidents or Oracle internal systems.

**Start here:** `python3 app.py --mode offline` · `python3 -m unittest -v` · `python3 evaluate.py`

**Explore:** [Architecture](#architecture) · [Offline run](#run-offline) · [OCI setup](#connect-real-oci-inference) · [Retrieval and evaluation](#retrieval-ingest-and-evaluation) · [Limits](#limits-before-production)


A reference incident-intake workflow for SRE teams. It ranks synthetic incidents by severity, retrieves relevant approved runbooks, extracts entities, and drafts cited triage notes for human review. Offline mode works without credentials. Optional live mode uses **OCI AI Language** for entity extraction and **OCI Generative AI** for a Cohere-format chat draft.

> Portfolio simulation, not an Oracle internal system. Offline mode and tests were run. Live OCI requests require Rajat's tenancy and have not been exercised or deployed here. No incident is automatically resolved; no remediation command runs.

## Architecture

```text
Synthetic incident JSON -> severity validation -> local feature-vector retrieval or OCI embeddings + Oracle DB vector retrieval
     -> OCI Language entities (or deterministic offline SEV tags)
     -> OCI Generative AI cited draft (or template offline)
     -> JSON human review queue
```

The three runbooks and incidents are invented. The baseline now uses deterministic hashed lexical feature vectors with cosine similarity, **not learned semantic embeddings**. The optional OCI path can use OCI Generative AI embeddings and Oracle Database 23ai vector retrieval when separately provisioned. See the retrieval section below. Model output is an untrusted draft: a human must verify claims and citations before acting. The prompt asks the model to treat incident descriptions as untrusted data; this alone is not a prompt-injection defense.

## Run offline

Python 3.10+; no dependency install:

```bash
python3 app.py --mode offline
python3 -m unittest -v
python3 app.py --mode offline --output output.json
```

Expected: three items, sorted SEV1, SEV2, SEV3. Replace `--incidents` or `--runbooks` with JSON files matching the samples to try another synthetic dataset. Runbooks are approved context, while an incident description is untrusted.

## Connect real OCI inference

1. Obtain permission for OCI AI Language entity detection and OCI Generative AI chat in a supported region, plus a compartment and a model ID that supports `CohereChatRequest` on-demand chat. Models, regions, IAM rules, rate limits and cost vary; check Oracle docs for your tenancy.
2. Create an OCI SDK API-key config at `~/.oci/config`, or point `OCI_CONFIG_FILE` to a private file. See [SDK configuration](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm). Never commit keys.
3. `python3 -m pip install -r requirements.txt`; set `OCI_COMPARTMENT_OCID` and `OCI_GENAI_MODEL_ID`. Optionally set `OCI_PROFILE`.
4. `python3 app.py --mode oci` sends incident descriptions to OCI Language and GenAI. Use only data approved for the tenancy; review privacy/retention before sending production incidents.

The official SDK calls are `oci.ai_language.AIServiceLanguageClient.batch_detect_language_entities` with `BatchDetectLanguageEntitiesDetails` and `TextDocument`, then `oci.generative_ai_inference.GenerativeAiInferenceClient.chat` with `ChatDetails`, `OnDemandServingMode` and `CohereChatRequest`. See [OCI Language example](https://docs.oracle.com/en-us/iaas/tools/python-sdk-examples/latest/ailanguage/batch_detect_language_entities.py.html), [OCI GenAI chat API](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference/client/oci.generative_ai_inference.GenerativeAiInferenceClient.html), and [Cohere request model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference/models/oci.generative_ai_inference.models.CohereChatRequest.html).

## Limits before production

Severity labels are input-provided, not inferred truth. The offline retrieval matcher is a tiny transparent example, not a learned embedding model or production search benchmark. A production system should add authorization per runbook, feedback/evaluation sets, durable incident IDs, audit logging, model-output citation validation, human review gates, monitoring and privacy controls. OCI inference can incur charges.

## Retrieval, ingest and evaluation

The extended offline path now uses `vector.py`: deterministic 256-dimensional hashed lexical feature vectors, cosine similarity and a threshold to avoid hallucinating a runbook when there is no match. This is a **local feature-vector baseline, not neural/semantic embeddings**. OCI mode can use OCI Generative AI embedding inference with `SEARCH_DOCUMENT` and `SEARCH_QUERY`, and Oracle Database 23ai AI Vector Search with `VECTOR_DISTANCE(..., COSINE)`. To enable the Oracle vector path, set `OCI_EMBED_MODEL_ID` to an embedding-capable model and `ORACLE_DB_USER`, `ORACLE_DB_PASSWORD`, `ORACLE_DB_DSN` for a least-privilege Oracle DB 23ai schema. `oracledb` is an optional extra (install `python3 -m pip install oracledb`); without *all* these settings OCI mode uses local retrieval plus OCI Language/GenAI. OCI inference and database path are untested on a live tenancy. The demo creates a table and upserts local runbooks each time, not a production ingestion service. See [Oracle embed API example](https://docs.oracle.com/en-us/iaas/tools/python-sdk-examples/latest/generativeaiinference/embed_text.py.html) and [Oracle DB vector search tutorial](https://docs.oracle.com/en/learn/oracledb-hybrid-search/index.html).

`pipeline.py` implements SQLite incident ingestion with duplicate fingerprints, sightings, and a SEV1/SEV2 *outbox* for escalation. The outbox is not sent to a pager or contact; an authorized dispatcher and an on-call schedule would be needed. Use `--queue incidents.sqlite` for persistence; no flag means an in-memory test queue. Never put live incidents or credentials in the repo. This demo treats identical service+description as duplicates; production needs time windows, status transitions and normalization to avoid collisions.

Run `python3 evaluate.py` for a **three-case synthetic retrieval recall@2**, citation coverage on the deterministic offline draft, and an adversarial-text smoke check. These numbers do not establish LLM faithfulness or a security guarantee. Real model-generated claims, citations and attacks need human review and an evaluated labeled dataset before operational use. Oracle DB credentials should be supplied via a secret manager or trusted environment, never committed.
