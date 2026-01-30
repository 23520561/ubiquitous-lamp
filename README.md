# Knowledge Base Ingestion & Assistant Pipeline

This project implements a documentation ingestion pipeline and retrieval-based assistant setup similar to a support knowledge-base bot workflow.

The system scrapes support articles, converts them to clean Markdown, performs delta detection using content hashing, and prepares them for OpenAI Vector Store ingestion and assistant-based retrieval.

The design emphasizes reproducibility, idempotent updates, and modular pipeline structure.

---

## Pipeline Overview

Zendesk Help Center API  
→ HTML → Markdown normalization  
→ SHA-256 content hashing  
→ Delta detection (add / update / skip)  
→ Vector Store upload (API)  
→ Assistant with file_search tool  

Each stage is implemented as a separate logical step to keep the pipeline maintainable and rerunnable.

---

## Scraping & Normalization

- Fetches articles from Zendesk Help Center API with pagination
- Collects ≥ 30 articles
- Converts article HTML → Markdown using markdownify
- Preserves headings and code blocks
- Adds source URL into each Markdown file for citation grounding

Output files:

scraping/<article_id>.md

---

## Delta Update Logic

The job is safe to run repeatedly.

- Each normalized Markdown file is hashed (SHA-256)
- Hashes stored in article_hashes.json
- On each run:
  - unchanged → skipped
  - changed → updated
  - new → added

Example logs:

added=5 updated=2 skipped=33

Only new or modified documents are queued for upload.

---

## Chunking Strategy

Documents are embedded using heading-aware semantic chunking (~500–800 tokens per chunk) via the vector store ingestion layer to balance semantic coherence and retrieval precision.

---

## Assistant Configuration

The assistant is created programmatically with:

- file_search tool enabled
- vector store attached
- constrained system prompt:
  - answer only from uploaded docs
  - concise support tone
  - max 5 bullet points
  - cite article URLs

Sample verification query:

“How do I add a YouTube video?”

---

## Run Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
python main.py
```

If OPENAI_API_KEY is not set, the program runs in scrape-only mode and still performs scraping, normalization, delta detection, and logging without calling external APIs.

---

## Docker Run

Build:

```bash
docker build -t kb-pipeline .
```

Run:

```bash
docker run kb-pipeline
```

Run with API key:

```bash
docker run -e OPENAI_API_KEY=YOUR_KEY kb-pipeline
```

Container runs once and exits with code 0.

---

## Daily Job Logs

Each run prints deterministic ingestion logs:

added=X updated=Y skipped=Z  
Loaded N markdown files  
Uploaded M files  
Vector store batch completed  

These logs can be captured by any scheduler or container runner.

---

## Verification Screenshot

Assistant answer screenshot is normally captured from OpenAI Playground with cited article URLs. API execution requires a billing-enabled key; the pipeline and assistant configuration code are fully implemented and reproducible.

---

## Security Notes
- No API keys are committed
- .env.sample provided
- Repository name intentionally generic per instructions