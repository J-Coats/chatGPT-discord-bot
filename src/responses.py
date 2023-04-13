from revChatGPT.V1 import AsyncChatbot
from revChatGPT.V3 import Chatbot
from dotenv import load_dotenv
import os
from src import config
from typing import Optional


load_dotenv()
OPENAI_EMAIL = os.getenv("OPENAI_EMAIL")
OPENAI_PASSWORD = os.getenv("OPENAI_PASSWORD")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")
CHAT_MODEL = os.getenv("CHAT_MODEL")

unofficial_chatbot: Optional[AsyncChatbot] = None
official_chatbot: Optional[Chatbot] = None


def setup_chatbots():
    global unofficial_chatbot, official_chatbot
    if CHAT_MODEL == "UNOFFICIAL":
        unofficial_chatbot = AsyncChatbot(config={
            "email": OPENAI_EMAIL,
            "password": OPENAI_PASSWORD,
            "session_token": SESSION_TOKEN
        })
    elif CHAT_MODEL == "OFFICIAL":
        official_chatbot = Chatbot(
            api_key=config.config["open_ai"]["api_key"],
            engine=config.config["open_ai"]["chat_model"]
        )


async def official_handle_response(message) -> str:
    global official_chatbot
    if official_chatbot is None:
        raise NotImplementedError
    return official_chatbot.ask(message)


async def unofficial_handle_response(message) -> str:
    global unofficial_chatbot
    response_message = ""
    async for response in unofficial_chatbot.ask(message):
        response_message = response["message"]

    return response_message
