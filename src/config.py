import os
from json import load, dumps

config = {
    "open_ai": {
        "api_key": None,
        "chat_model": "gpt-3.5-turbo",
    },
    "bot": {
        "starting_prompt": None
    },
    "discord": {
        "channel_id": None,
    },
}


def update_config():
    global config
    if os.path.exists("config.json"):
        with open("config.json", "r") as file:
            config.update(load(file))

    if os.path.exists("starting-prompt.txt"):
        with open("starting-prompt.txt", "r") as file:
            config.update({
                "bot": {
                    "starting_prompt": "\n".join(file.readlines())
                }
            })

    # update config file from environment vars
    if "OPENAI_API_KEY" in os.environ:
        config["open_ai"]["api_key"] = os.getenv("OPENAI_API_KEY")
    if "OPENAI_ENGINE" in os.environ:
        config["open_ai"]["chat_model"] = os.getenv("OPENAI_ENGINE")
    if "DISCORD_CHANNEL_ID" in os.environ:
        config["discord"]["channel_id"] = os.getenv("DISCORD_CHANNEL_ID")

    with open("config.json", "w") as file:
        file.write(dumps(config, ensure_ascii=True))


def save_config():
    with open("config.json", "w") as file:
        file.write(dumps(config, ensure_ascii=True))


def setup_complete() -> bool:
    global config
    if config["open_ai"]["api_key"] is None:
        return False
    return True
