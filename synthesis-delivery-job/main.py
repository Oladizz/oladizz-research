import os
import requests
import markdown
from weasyprint import HTML
from google.cloud import firestore
from datetime import datetime

def get_db():
    project = os.environ.get("GCP_PROJECT", "your-gcp-project-id")
    return firestore.Client(project=project)

def fetch_top_claims(db):
    print("Fetching claims with > 60% confidence...")
    # Fetch claims ordered by score descending (requires a composite index in Firestore in prod)
    # For now, we fetch all ready for synthesis and filter in memory to keep it simple
    claims_ref = db.collection("scored_clusters").where("status", "==", "ready_for_synthesis").stream()
    
    valid_claims = []
    for doc in claims_ref:
        data = doc.to_dict()
        if data.get("confidence_score", 0) >= 60.0:
            valid_claims.append(data)
            
    # Sort highest confidence first
    valid_claims.sort(key=lambda x: x.get("confidence_score", 0), reverse=True)
    return valid_claims

def generate_markdown(claims):
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    md = f"# Oladizz Research Report\n"
    md += f"**Generated:** {date_str}\n\n"
    md += "---\n\n"
    
    if not claims:
        md += "> No claims met the strict 60% confidence threshold for this run.\n"
        return md
        
    md += "## Verified Intelligence\n\n"
    
    for i, claim in enumerate(claims, 1):
        score = claim.get('confidence_score', 0)
        sources = claim.get('sources', [])
        source_str = ", ".join(sources)
        text = claim.get('representative_claim', 'Unknown claim')
        
        # Emoji indicator based on score
        indicator = "🟢" if score >= 85 else "🟡"
        
        md += f"### {indicator} Claim {i}: {score}% Confidence\n"
        md += f"**{text}**\n\n"
        md += f"- **Independent Sources ({len(sources)}):** {source_str}\n"
        if claim.get('had_contradictions'):
            md += "- ⚠️ *Note: Initial sources contained conflicting details which were penalized in scoring.*\n"
        md += "\n---\n\n"
        
    return md

def create_pdf(markdown_text, output_filename):
    print(f"Converting markdown to PDF: {output_filename}")
    html_content = markdown.markdown(markdown_text)
    
    # Add some CSS to make it look like a textbook/professional report
    styled_html = f"""
    <html>
    <head>
        <style>
            @page {{ margin: 1in; }}
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; line-height: 1.6; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 10px; }}
            h2 {{ color: #34495e; margin-top: 30px; }}
            h3 {{ color: #2980b9; font-size: 14pt; }}
            hr {{ border: 0; border-bottom: 1px solid #eee; margin: 20px 0; }}
            p {{ margin-bottom: 15px; }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    HTML(string=styled_html).write_pdf(output_filename)
    print("PDF generated successfully.")

def send_to_telegram(pdf_filename):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("Telegram credentials missing. PDF generated but not sent.")
        return
        
    print("Uploading PDF to Telegram...")
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    
    try:
        with open(pdf_filename, 'rb') as doc:
            files = {'document': doc}
            data = {'chat_id': chat_id, 'caption': '📊 Your Oladizz Research Report is ready!'}
            
            response = requests.post(url, files=files, data=data)
            
            if response.status_code == 200:
                print("Successfully sent to Telegram!")
            else:
                print(f"Failed to send: {response.text}")
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

if __name__ == "__main__":
    print("========================================")
    print("Oladizz Research Pipeline: Stage 9 & 11")
    print("========================================")
    
    db = get_db()
    
    # 1. Fetch
    claims = fetch_top_claims(db)
    print(f"Found {len(claims)} high-confidence claims.")
    
    # 2. Synthesize Markdown
    md_text = generate_markdown(claims)
    
    # 3. Convert to PDF
    pdf_path = "/tmp/research_report.pdf"
    create_pdf(md_text, pdf_path)
    
    # 4. Deliver
    send_to_telegram(pdf_path)
    
    # Note: In production, you'd want to mark these clusters as "delivered" 
    # in Firestore so they don't get emailed again on the next run.
