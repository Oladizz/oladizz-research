import os
import time
import requests
from bs4 import BeautifulSoup
import json
import urllib.parse

def scrape_duckduckgo(topic, target_urls=50):
    print(f"Starting DuckDuckGo search for: {topic}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    url = "https://html.duckduckgo.com/html/"
    discovered_urls = set()
    
    # Payload for the first page
    payload = {
        'q': topic,
        'b': ''
    }
    
    try:
        while len(discovered_urls) < target_urls:
            response = requests.post(url, data=payload, headers=headers)
            
            if response.status_code != 200:
                print(f"Failed to fetch results, status code: {response.status_code}")
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            results = soup.find_all('a', class_='result__url')
            
            if not results:
                print("No more results found or rate limited.")
                break
                
            for result in results:
                href = result.get('href')
                if href and href.startswith('http'):
                    discovered_urls.add(href)
                    
            print(f"Discovered {len(discovered_urls)} URLs so far...")
            
            if len(discovered_urls) >= target_urls:
                break
                
            # Find the 'Next' button to get the payload for the next page
            next_form = soup.find('form', class_='result--more__form')
            if not next_form:
                break
                
            # Update payload for the next page request
            payload = {}
            for input_tag in next_form.find_all('input'):
                payload[input_tag.get('name')] = input_tag.get('value')
                
            # Be polite to the free endpoint
            time.sleep(3)
            
    except Exception as e:
        print(f"Error during scraping: {e}")
        
    return list(discovered_urls)

if __name__ == "__main__":
    # In Cloud Run Jobs, we can pass the topic via environment variables
    # For GitHub Actions triggering, we can set this variable.
    topic = os.environ.get("SEARCH_TOPIC", "Polymarket automated trading case study")
    
    print("========================================")
    print(f"Oladizz Research Pipeline: Stage 1")
    print(f"Targeting Topic: {topic}")
    print("========================================")
    
    urls = scrape_duckduckgo(topic, target_urls=50)
    
    # In the next step, we will write these directly to Firestore.
    # For now, we log them out to verify our Cloud Run job works.
    print(f"Found {len(urls)} total URLs.")
    
    # Save locally to a JSON file for reference
    with open('discovered_urls.json', 'w') as f:
        json.dump(urls, f, indent=2)
        
    print("Saved to discovered_urls.json. Run complete!")
