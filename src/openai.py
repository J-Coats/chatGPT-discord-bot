import requests


def verify_token(api_token: str) -> bool:
    headers = {
        "Authorization": f"Bearer {api_token}"
    }
    r = requests.get("https://api.openai.com/v1/models", headers=headers)
    return r.ok
