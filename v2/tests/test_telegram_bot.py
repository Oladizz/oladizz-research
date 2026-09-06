import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'utils')))
from telegram_bot import ResearchTelegramBot


def test_telegram_bot_configuration():
    bot_unconfigured = ResearchTelegramBot(token="")
    assert not bot_unconfigured.is_configured()

    bot_configured = ResearchTelegramBot(token="123456789:ABCdefGhIJKlmNoPQRstuVWXyz")
    assert bot_configured.is_configured()


@patch("requests.post")
def test_telegram_send_message(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp

    bot = ResearchTelegramBot(token="123456789:ABCdefGhIJKlmNoPQRstuVWXyz")
    success = bot.send_message(chat_id=999, text="Hello World")
    assert success
    mock_post.assert_called_once()


@patch("requests.post")
def test_telegram_send_document(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp

    bot = ResearchTelegramBot(token="123456789:ABCdefGhIJKlmNoPQRstuVWXyz")
    success = bot.send_document(chat_id=999, file_bytes=b"%PDF-1.4...", filename="test.pdf", caption="PDF Report")
    assert success
    mock_post.assert_called_once()


def test_telegram_generate_pdf():
    bot = ResearchTelegramBot(token="123456789:ABCdefGhIJKlmNoPQRstuVWXyz")
    pdf_bytes = bot.generate_pdf(report_md="# Title\n\n- Claim 1 verified.", run_id="run_test_pdf")
    assert pdf_bytes is not None
    assert pdf_bytes.startswith(b"%PDF")


@patch.object(ResearchTelegramBot, "send_message")
def test_telegram_handle_help_command(mock_send):
    bot = ResearchTelegramBot(token="123456789:ABCdefGhIJKlmNoPQRstuVWXyz")
    bot.handle_command(chat_id=999, text="/help")
    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    assert "Truth-Filtering Research Engine Bot" in args[1]


@patch.object(ResearchTelegramBot, "send_message")
@patch.object(ResearchTelegramBot, "send_document")
def test_telegram_handle_report_command(mock_send_doc, mock_send_msg):
    from api_server import RUNS
    test_run_id = "test_tg_run_88"
    RUNS[test_run_id] = {
        "status": "completed",
        "report_md": "# Dossier\n\n🟢 Fact 1: Confirmed"
    }

    bot = ResearchTelegramBot(token="123456789:ABCdefGhIJKlmNoPQRstuVWXyz")
    bot.handle_command(chat_id=999, text=f"/report {test_run_id}")
    mock_send_msg.assert_called_once()
    mock_send_doc.assert_called_once()
