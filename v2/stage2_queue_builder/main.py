import os
import sys
import json
import hashlib
from collections import defaultdict

from google.cloud import firestore
from google.cloud import tasks_v2

# Import shared config and models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *

def create_queue_if_not_exists(client: tasks_v2.CloudTasksClient, project: str, location: str, queue_id: str):
    parent = f"projects/{project}/locations/{location}"
    queue_name = f"{parent}/queues/{queue_id}"
    
    try:
        # Try to get the queue first
        client.get_queue(name=queue_name)
    except Exception:
        # If it doesn't exist, create it
        queue = tasks_v2.Queue(
            name=queue_name,
            rate_limits=tasks_v2.RateLimits(
                max_concurrent_dispatches=CT_MAX_CONCURRENT_PER_DOMAIN
            ),
            retry_config=tasks_v2.RetryConfig(
                max_attempts=CT_RETRY_MAX_ATTEMPTS,
                min_backoff={"seconds": int(CT_RETRY_MIN_BACKOFF.replace('s', ''))},
                max_backoff={"seconds": int(CT_RETRY_MAX_BACKOFF.replace('s', ''))}
            )
        )
        try:
            client.create_queue(parent=parent, queue=queue)
            print(f"Created queue: {queue_name}")
        except Exception as e:
            print(f"Failed to create queue {queue_name}: {e}")
    return queue_name

def main():
    run_id = os.environ.get("RUN_ID")
    if not run_id:
        print("Error: RUN_ID must be set.")
        sys.exit(1)
        
    print(f"Starting Stage 2 for run '{run_id}'")
    
    db = firestore.Client(project=GCP_PROJECT, database="(default)")
    tasks_client = tasks_v2.CloudTasksClient()
    
    # Read pending URLs
    docs = db.collection(FS_DISCOVERED_URLS).where("run_id", "==", run_id).where("status", "==", "pending").stream()
    
    domain_to_urls = defaultdict(list)
    doc_refs = []
    
    for doc in docs:
        data = doc.to_dict()
        url = data.get("url")
        domain = data.get("domain")
        if url and domain:
            domain_to_urls[domain].append({"url": url, "doc_id": doc.id})
            doc_refs.append(doc.reference)
            
    if not domain_to_urls:
        print("No pending URLs found for this run.")
        return
        
    print(f"Found {len(doc_refs)} pending URLs across {len(domain_to_urls)} domains.")
    
    # Sort domains by number of URLs (descending)
    sorted_domains = sorted(domain_to_urls.keys(), key=lambda d: len(domain_to_urls[d]), reverse=True)
    
    # Assign domains to queues (up to CT_MAX_DOMAINS_PARALLEL)
    # If more than CT_MAX_DOMAINS_PARALLEL, batch smaller ones into shared queues
    num_queues = min(len(sorted_domains), CT_MAX_DOMAINS_PARALLEL)
    queue_assignments = {}
    
    for i, domain in enumerate(sorted_domains):
        queue_idx = i % num_queues
        queue_id = f"scraper-q-{queue_idx}"
        queue_assignments[domain] = queue_id
        
    print(f"Using {num_queues} queues for processing.")
    
    # Create queues and dispatch tasks
    queues_created = set()
    
    for domain, urls_info in domain_to_urls.items():
        queue_id = queue_assignments[domain]
        
        if queue_id not in queues_created:
            create_queue_if_not_exists(tasks_client, GCP_PROJECT, CT_LOCATION, queue_id)
            queues_created.add(queue_id)
            
        queue_path = tasks_client.queue_path(GCP_PROJECT, CT_LOCATION, queue_id)
        
        for info in urls_info:
            url = info["url"]
            doc_id = info["doc_id"]
            
            # Domain-based task name to prevent duplicates (using hash for safe chars)
            # URL hash is already in doc_id
            task_name_hash = hashlib.md5(f"{run_id}_{doc_id}".encode()).hexdigest()
            task_name = f"{queue_path}/tasks/task-{task_name_hash}"
            
            payload = {
                "url": url,
                "domain": domain,
                "run_id": run_id
            }
            
            task = tasks_v2.Task(
                name=task_name,
                http_request=tasks_v2.HttpRequest(
                    http_method=tasks_v2.HttpMethod.POST,
                    url=CT_SCRAPER_SERVICE_URL,
                    headers={"Content-Type": "application/json"},
                    body=json.dumps(payload).encode()
                )
            )
            
            try:
                tasks_client.create_task(parent=queue_path, task=task)
            except Exception as e:
                # Might fail if task already exists, which is fine (deduplication)
                if "ALREADY_EXISTS" not in str(e):
                    print(f"Failed to create task for {url}: {e}")
                
    # Update Firestore status
    batch = db.batch()
    batch_count = 0
    
    for ref in doc_refs:
        batch.update(ref, {"status": "queued"})
        batch_count += 1
        
        if batch_count >= 500:
            batch.commit()
            batch = db.batch()
            batch_count = 0
            
    if batch_count > 0:
        batch.commit()
        
    print(f"Stage 2 complete. Dispatched tasks and updated {len(doc_refs)} URLs to 'queued'.")

if __name__ == "__main__":
    main()
