import os
import hashlib
from flask import Flask, request, jsonify
from google.cloud import firestore
import trafilatura

app = Flask(__name__)

# Initialize Firestore (will use default credentials in GCP)
# Using lazy initialization to avoid crash on startup if not fully configured
db = None

def get_db():
    global db
    if db is None:
        project = os.environ.get("GCP_PROJECT", "your-gcp-project-id")
        db = firestore.Client(project=project)
    return db

@app.route('/process_url', methods=['POST'])
def process_url():
    """
    Webhook triggered by Cloud Tasks.
    Fetches the URL, extracts the article text, and saves it to Firestore.
    """
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "No URL provided"}), 400
        
    url = data['url']
    domain = data.get('domain', 'unknown')
    
    print(f"Worker received task for URL: {url}")
    
    try:
        # 1. Fetch and clean content using trafilatura (excellent for stripping ads/nav)
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            print(f"Failed to download {url}")
            return jsonify({"status": "failed", "reason": "download_failed"}), 200 # Return 200 so task isn't retried infinitely
            
        text = trafilatura.extract(downloaded)
        if not text:
            print(f"No text extracted from {url}")
            return jsonify({"status": "failed", "reason": "no_text_extracted"}), 200

        # 2. Content-Level Deduplication (Stage 3)
        # Hash the actual content. If multiple URLs have the exact same text 
        # (syndicated content), they will have the same hash.
        content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        
        db_client = get_db()
        content_ref = db_client.collection("extracted_pages").document(content_hash)
        
        if content_ref.get().exists:
            print(f"Content already exists for {url} (Syndicated/Duplicate). Skipping.")
            # Update the original URL status to note it was a duplicate
            url_hash = str(hash(url))
            db_client.collection("processed_urls").document(url_hash).update({"status": "duplicate_content"})
            return jsonify({"status": "duplicate_content_skipped"}), 200
            
        # 3. Save the clean text to Firestore (or BigQuery in prod for larger scale)
        content_ref.set({
            "source_url": url,
            "source_domain": domain,
            "raw_text": text,
            "status": "ready_for_extraction"
        })
        
        # Update URL status to completed
        url_hash = str(hash(url))
        db_client.collection("processed_urls").document(url_hash).update({"status": "fetched"})
        
        print(f"Successfully processed and saved text for {url}")
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        print(f"Error processing {url}: {e}")
        # Return 500 so Cloud Tasks retries according to the backoff schedule
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    # This server runs continuously and listens for tasks
    app.run(host="0.0.0.0", port=port)
