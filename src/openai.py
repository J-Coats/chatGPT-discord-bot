import requests
from src import config


def verify_token(api_token: str) -> bool:
    headers = {
        "Authorization": f"Bearer {api_token}"
    }
    r = requests.get("https://api.openai.com/v1/models", headers=headers)
    return r.ok


def verify_model(model) -> bool:
    headers = {
        "Authorization": f"Bearer {config.config['open_ai']['api_key']}"
    }
    r = requests.get(f"https://api.openai.com/v1/models/{model}", headers=headers)
    return r.ok
