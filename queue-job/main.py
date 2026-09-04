import os
import json
import urllib.parse
from google.cloud import tasks_v2
from google.cloud import firestore

def get_domain(url):
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.replace("www.", "")

def enqueue_urls():
    project = os.environ.get("GCP_PROJECT", "your-gcp-project-id")
    location = os.environ.get("GCP_LOCATION", "us-central1")
    worker_url = os.environ.get("WORKER_URL", "https://your-worker-url.run.app/process_url")
    
    # Initialize Google Cloud clients
    # Note: These will use Application Default Credentials when running on GCP
    db = firestore.Client(project=project)
    client = tasks_v2.CloudTasksClient()
    
    # Load the discovered URLs from Stage 1
    try:
        with open("../search-job/discovered_urls.json", "r") as f:
            urls = json.load(f)
    except FileNotFoundError:
        print("discovered_urls.json not found. Run the search job first.")
        return

    print(f"Loaded {len(urls)} URLs to process.")
    
    # Process each URL
    for url in urls:
        domain = get_domain(url)
        if not domain:
            continue
            
        # 1. Deduplication (URL Level)
        url_hash = str(hash(url))  # Simplistic hash for demo, consider hashlib in prod
        doc_ref = db.collection("processed_urls").document(url_hash)
        
        if doc_ref.get().exists:
            print(f"Skipping {url} (Already processed)")
            continue
            
        # 2. Queue Assignment
        # In Cloud Tasks, queue names can only contain letters, numbers, and hyphens.
        safe_domain = domain.replace(".", "-").replace("_", "-")
        queue_name = client.queue_path(project, location, safe_domain)
        
        # 3. Queue Creation (if it doesn't exist)
        try:
            client.get_queue(name=queue_name)
        except Exception:
            print(f"Creating new queue for domain: {safe_domain}")
            queue = {
                "name": queue_name,
                "rate_limits": {
                    "max_concurrent_dispatches": 1  # THE MAGIC RULE: 1 worker per domain!
                },
                "retry_config": {
                    "max_attempts": 3,
                    "min_backoff": {"seconds": 10},
                    "max_backoff": {"seconds": 300}
                }
            }
            try:
                client.create_queue(parent=f"projects/{project}/locations/{location}", queue=queue)
            except Exception as e:
                print(f"Failed to create queue {safe_domain}: {e}")
                
        # 4. Enqueue Task
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": worker_url,
                "headers": {"Content-type": "application/json"},
                "body": json.dumps({"url": url, "domain": domain}).encode()
            }
        }
        
        try:
            client.create_task(parent=queue_name, task=task)
            print(f"Enqueued: {url} -> {safe_domain}")
            
            # Mark as queued in Firestore so we don't enqueue it again
            doc_ref.set({"url": url, "domain": domain, "status": "queued"})
        except Exception as e:
            print(f"Failed to enqueue {url}: {e}")

if __name__ == "__main__":
    print("========================================")
    print("Oladizz Research Pipeline: Stage 2 (Queue & Dedup)")
    print("========================================")
    # When deployed, this script will be triggered after the search job finishes
    # For now, we mock the execution
    print("Note: Set GCP_PROJECT, GCP_LOCATION, and WORKER_URL env variables.")
    enqueue_urls()
