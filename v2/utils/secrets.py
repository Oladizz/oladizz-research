"""
Secret Manager integration with env var fallback.
"""
import os

try:
    from google.cloud import secretmanager
    _SECRET_MANAGER_AVAILABLE = True
except ImportError:
    _SECRET_MANAGER_AVAILABLE = False

# Cache secrets in memory
_SECRETS_CACHE = {}

KNOWN_SECRETS = [
    "GEMINI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "GOOGLE_SEARCH_API_KEY",
    "GOOGLE_SEARCH_ENGINE_ID"
]

def get_secret(name: str, default: str = '') -> str:
    if name in _SECRETS_CACHE:
        return _SECRETS_CACHE[name]
        
    val = os.environ.get(name)
    if val is not None:
        _SECRETS_CACHE[name] = val
        return val
        
    if _SECRET_MANAGER_AVAILABLE:
        try:
            client = secretmanager.SecretManagerServiceClient()
            project_id = os.environ.get("GCP_PROJECT", "oladizz-research")
            name_path = f"projects/{project_id}/secrets/{name}/versions/latest"
            response = client.access_secret_version(request={"name": name_path})
            secret_val = response.payload.data.decode("UTF-8")
            _SECRETS_CACHE[name] = secret_val
            return secret_val
        except Exception:
            pass

    return default

def get_all_secrets() -> dict:
    return {name: get_secret(name) for name in KNOWN_SECRETS}
