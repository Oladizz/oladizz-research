"""
Interactive Telegram Bot Daemon for Truth-Filtering Research Pipeline.
Allows users to trigger research runs, poll progress, and receive PDF dossiers directly in chat.
"""
import io
import os
import sys
import time
import json
import uuid
import threading
from typing import Optional, Dict, Any
import requests

# Add paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

try:
    from api_server import execute_pipeline, RUNS, get_db
except ImportError:
    RUNS = {}
    execute_pipeline = None
    get_db = None


class ResearchTelegramBot:
    """Telegram Bot Daemon for interactive research triggering & PDF delivery."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self.offset = 0

    def is_configured(self) -> bool:
        return bool(self.token and len(self.token) > 10)

    def send_message(self, chat_id: int | str, text: str, parse_mode: str = "Markdown") -> bool:
        """Send formatted text message to a chat."""
        if not self.is_configured():
            return False
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text[:4096],
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            resp = requests.post(url, json=payload, timeout=12)
            if resp.status_code != 200:
                # Retry without markdown if formatting was invalid
                payload["parse_mode"] = ""
                requests.post(url, json=payload, timeout=12)
            return resp.status_code == 200
        except Exception as e:
            print(f"Telegram send_message error: {e}")
            return False

    def send_document(
        self, chat_id: int | str, file_bytes: bytes, filename: str, caption: str = ""
    ) -> bool:
        """Send a binary document (like PDF) to a chat."""
        if not self.is_configured():
            return False
        try:
            url = f"{self.base_url}/sendDocument"
            files = {"document": (filename, file_bytes, "application/pdf")}
            data = {"chat_id": chat_id, "caption": caption[:1024]}
            resp = requests.post(url, data=data, files=files, timeout=30)
            return resp.status_code == 200
        except Exception as e:
            print(f"Telegram send_document error: {e}")
            return False

    def generate_pdf(self, report_md: str, run_id: str) -> Optional[bytes]:
        """Convert Markdown report to PDF bytes via WeasyPrint."""
        try:
            import markdown
            import weasyprint

            html_body = markdown.markdown(report_md, extensions=['tables', 'fenced_code'])
            full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Research Dossier - {run_id}</title>
<style>
    @page {{
        margin: 20mm;
        size: A4;
        @bottom-right {{
            content: "Page " counter(page) " of " counter(pages);
            font-size: 8pt;
            color: #718096;
        }}
    }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        line-height: 1.6;
        color: #1a202c;
    }}
    h1 {{
        color: #1e3a8a;
        border-bottom: 2px solid #3b82f6;
        padding-bottom: 8px;
        font-size: 20pt;
    }}
    h2 {{
        color: #1e40af;
        margin-top: 20px;
        border-bottom: 1px solid #e2e8f0;
        font-size: 14pt;
    }}
    h3 {{
        color: #1e293b;
        margin-top: 14px;
        font-size: 11pt;
    }}
    p, li {{ font-size: 9.5pt; }}
    code {{ background: #f1f5f9; padding: 2px 4px; border-radius: 4px; font-size: 8pt; }}
    hr {{ border: none; border-top: 1px solid #e2e8f0; margin: 14px 0; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
            return weasyprint.HTML(string=full_html).write_pdf()
        except Exception as e:
            print(f"PDF generation error: {e}")
            return None

    def handle_command(self, chat_id: int | str, text: str):
        """Dispatches incoming bot commands."""
        parts = text.strip().split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        if command in ("/start", "/help"):
            msg = (
                "🌐 *Truth-Filtering Research Engine Bot*\n\n"
                "I cross-reference information across independent web domains, detect contradictions, "
                "and assemble textbook-grade research dossiers.\n\n"
                "⚡ *Commands:*\n"
                "• `/research <topic>` - Launch a deep verification pipeline\n"
                "• `/status <run_id>` - Check current pipeline progress\n"
                "• `/report <run_id>` - Download report summary & PDF\n\n"
                "*Example:*\n"
                "`/research Next-Generation Solid State Batteries 2026`"
            )
            self.send_message(chat_id, msg)

        elif command == "/research":
            if not args:
                self.send_message(chat_id, "⚠️ Please provide a research topic.\n*Usage:* `/research <topic>`")
                return

            run_id = f"tg_{uuid.uuid4().hex[:8]}"
            self.send_message(
                chat_id,
                f"🚀 *Research Pipeline Launched!*\n\n"
                f"• *Topic:* {args}\n"
                f"• *Run ID:* `{run_id}`\n\n"
                f"Discovering candidate sources and cross-checking claims. Type `/status {run_id}` to follow progress."
            )

            if execute_pipeline:
                def run_job():
                    execute_pipeline(run_id=run_id, topic=args, max_urls=12)
                    # Notify user on completion
                    self.send_message(
                        chat_id,
                        f"✅ *Research Complete for Run `{run_id}`!*\n\n"
                        f"Topic: *{args}*\n"
                        f"Use `/report {run_id}` to fetch the findings and PDF dossier."
                    )
                t = threading.Thread(target=run_job, daemon=True)
                t.start()

        elif command == "/status":
            if not args:
                self.send_message(chat_id, "⚠️ Please specify a run ID.\n*Usage:* `/status <run_id>`")
                return

            run_id = args.strip()
            data = RUNS.get(run_id)
            if not data and get_db:
                conn = get_db()
                row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
                if row:
                    data = dict(row)

            if not data:
                self.send_message(chat_id, f"❌ Run `{run_id}` not found.")
                return

            status = data.get("status", "unknown").upper()
            progress = data.get("progress", "In progress...")
            discovered = data.get("urls_discovered", 0)
            scraped = data.get("pages_scraped", 0)
            extracted = data.get("claims_extracted", 0)

            msg = (
                f"📊 *Run Status: `{run_id}`*\n\n"
                f"• *Status:* {status}\n"
                f"• *Progress:* {progress}\n"
                f"• *Sources Discovered:* {discovered}\n"
                f"• *Pages Scraped:* {scraped}\n"
                f"• *Atomic Facts Extracted:* {extracted}\n"
            )
            if status == "COMPLETED":
                msg += f"\n👉 Type `/report {run_id}` to retrieve your PDF."
            self.send_message(chat_id, msg)

        elif command == "/report":
            if not args:
                self.send_message(chat_id, "⚠️ Please specify a run ID.\n*Usage:* `/report <run_id>`")
                return

            run_id = args.strip()
            data = RUNS.get(run_id)
            report_md = data.get("report_md") if data else None
            if not report_md and get_db:
                conn = get_db()
                row = conn.execute("SELECT report_md FROM runs WHERE run_id = ?", (run_id,)).fetchone()
                if row and row["report_md"]:
                    report_md = row["report_md"]

            if not report_md:
                self.send_message(chat_id, f"⏳ Report for `{run_id}` is not ready yet or was not found.")
                return

            # Send preview
            preview = report_md[:1500] + ("\n\n*(Full report in attached PDF...)*" if len(report_md) > 1500 else "")
            self.send_message(chat_id, preview, parse_mode="")

            # Generate and send PDF
            pdf_bytes = self.generate_pdf(report_md, run_id)
            if pdf_bytes:
                self.send_document(
                    chat_id,
                    pdf_bytes,
                    filename=f"Research_Report_{run_id}.pdf",
                    caption=f"📄 Verified Research Dossier: {run_id}"
                )
        else:
            self.send_message(chat_id, "Unknown command. Type `/help` for available options.")

    def poll_once(self):
        """Fetch and process pending updates."""
        if not self.is_configured():
            return
        try:
            url = f"{self.base_url}/getUpdates"
            params = {"offset": self.offset, "timeout": 10}
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("result", []):
                    self.offset = item["update_id"] + 1
                    msg = item.get("message") or item.get("channel_post")
                    if msg and "text" in msg:
                        chat_id = msg["chat"]["id"]
                        text = msg["text"]
                        self.handle_command(chat_id, text)
        except Exception as e:
            print(f"Telegram polling warning: {e}")

    def poll_forever(self):
        """Long-polling daemon loop."""
        if not self.is_configured():
            print("Telegram Bot Token not configured. Export TELEGRAM_BOT_TOKEN to start bot daemon.")
            return
        print("🤖 Research Telegram Bot daemon is running... (Press Ctrl+C to stop)")
        while True:
            try:
                self.poll_once()
                time.sleep(1)
            except KeyboardInterrupt:
                print("Bot stopped by user.")
                break
            except Exception as e:
                print(f"Bot loop error: {e}")
                time.sleep(5)


if __name__ == "__main__":
    bot = ResearchTelegramBot()
    bot.poll_forever()
