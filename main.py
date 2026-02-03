import os
from openai import OpenAI
import requests
from markdownify import markdownify as md
import json
import hashlib

HASH_FILE = "article_hashes.json"

def load_hashes():
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r") as f:
            return json.load(f)
    return {}

def save_hashes(hashes):
    with open(HASH_FILE, "w") as f:
        json.dump(hashes, f, indent=2)
def hash_article(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()

API_URL = "https://support.optisigns.com/api/v2/help_center/articles.json"
FOLDER_NAME = "scraping"
N_ARTICLES = 40
def fetch_articles():
    url = API_URL
    all_articles = []

    while url and len(all_articles) < N_ARTICLES:
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        data = res.json()

        all_articles.extend(data["articles"])
        url = data.get("next_page")

    return all_articles[:N_ARTICLES]
def scrape_articles():
    added = 0
    updated = 0
    skipped = 0
    print("Scraping OptiSigns articles...")

    articles = fetch_articles()
    os.makedirs(FOLDER_NAME, exist_ok=True)
    existing_hashes = load_hashes()
    new_hashes = {}
    files_to_upload = []


    for article in articles:
        article_id = str(article["id"])
        html = article["body"]
        url = article.get("html_url", "")

        markdown = md(html)

        markdown = f"""# {article["title"]}

Article URL: {url}

{markdown}
"""

        article_hash = hash_article(markdown)
        new_hashes[article_id] = article_hash

        # Skip unchanged articles
        if existing_hashes.get(article_id) == article_hash:
            skipped += 1
            continue
        elif article_id in existing_hashes:
            updated += 1
        else:
            added += 1

        # New or updated article
        path = os.path.join(FOLDER_NAME, f"{article_id}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(markdown)

        files_to_upload.append(path)

    save_hashes(new_hashes)
    print(f"added={added} updated={updated} skipped={skipped}")
    return files_to_upload

VECTOR_STORE_NAME = "optisigns-docs"
def get_or_create_vector_store(client, name):
    stores = client.beta.vector_stores.list()

    for store in stores.data:
        if store.name == name:
            print(f"Using existing vector store: {store.id}")
            return store.id

    store = client.beta.vector_stores.create(name=name)
    print(f"Created vector store: {store.id}")
    return store.id

def resolve_vector_store(client):
    env_id = os.getenv("VECTOR_STORE_ID")
    if env_id:
        print(f"Using VECTOR_STORE_ID from env: {env_id}")
        return env_id

    return get_or_create_vector_store(client, VECTOR_STORE_NAME)

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply.
"""

def main():
    files = scrape_articles()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set — running in scrape-only mode.")
        return
    client = OpenAI(api_key=api_key)
    print(f"Loaded {len(files)} markdown files")

    # Upload files
    uploaded_file_ids = []

    for path in files:
        with open(path, "rb") as f:
            uploaded = client.files.create(
                file=f,
                purpose="assistants"
            )
            uploaded_file_ids.append(uploaded.id)

    print(f"Uploaded {len(files)} files")

    # Create vector store
    vector_store_id = resolve_vector_store(client)

    # Attach files to vector store
    if uploaded_file_ids:
        batch = client.beta.vector_stores.file_batches.create(
            vector_store_id=vector_store_id,
            file_ids=uploaded_file_ids
        )
        while batch.status not in ("completed", "failed"):
            batch = client.beta.vector_stores.file_batches.retrieve(
                vector_store_id=vector_store_id,
                batch_id=batch.id
            )
        print("Files attached to vector store")
    else:
        print("No new or updated files to attach")

    print("Vector store created and files attached")

    # Create assistant
    assistant = client.beta.assistants.create(
        name="OptiBot",
        instructions=SYSTEM_PROMPT,
        model="gpt-4.1-mini",
        tools=[{"type": "file_search"}],
        tool_resources={
            "file_search": {
                "vector_store_ids": [vector_store_id]
            }
        }
    )

    print(f"Assistant created: {assistant.id}")

    # Create thread + ask question
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content="How do I add a YouTube video?"
    )

    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id
    )

    # Poll until complete
    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )
        if run.status == "completed":
            break

    messages = client.beta.threads.messages.list(thread_id=thread.id)
    print("\n=== ASSISTANT ANSWER ===\n")
    print(messages.data[0].content[0].text.value)

if __name__ == "__main__":
    main()
