import discord
import os
from discord import app_commands
from src import responses, log, database, config
from src.openai import verify_token, verify_model
import requests
import time

logger = log.setup_logger(__name__)

isPrivate = False

userReplyList = []


class aclient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.activity = discord.Activity(type=discord.ActivityType.watching, name="/chat | /help")


async def send_message(message, user_message, is_reply_all):
    if is_reply_all == "False":
        author = message.user.id
        await message.response.defer(ephemeral=isPrivate)
    else:
        author = message.author.id
    try:
        response = (f'> **{user_message}** - <@{str(author)}' + '> \n\n')
        chat_model = os.getenv("CHAT_MODEL")
        if chat_model == "OFFICIAL":
            old_token = responses.official_chatbot.api_key
            token = database.query_token(author)
            if token:
                logger.info(f"Using custom token for {message.user.name}")
                responses.official_chatbot.api_key = token
            response = f"{response}{await responses.official_handle_response(user_message)}"
            responses.official_chatbot.api_key = old_token
        elif chat_model == "UNOFFICIAL":
            response = f"{response}{await responses.unofficial_handle_response(user_message)}"
        database.increment_user_prompt_counter(author)
        char_limit = 1900
        if len(response) > char_limit:
            # Split the response into smaller chunks of no more than 1900 characters each(Discord limit is 2000 per chunk)
            if "```" in response:
                # Split the response if the code block exists
                parts = response.split("```")

                for i in range(len(parts)):
                    if i % 2 == 0:  # indices that are even are not code blocks
                        if is_reply_all == "True":
                            await message.channel.send(parts[i])
                        else:
                            await message.followup.send(parts[i])
                    else:  # Odd-numbered parts are code blocks
                        code_block = parts[i].split("\n")
                        formatted_code_block = ""
                        for line in code_block:
                            while len(line) > char_limit:
                                # Split the line at the 50th character
                                formatted_code_block += line[:char_limit] + "\n"
                                line = line[char_limit:]
                            formatted_code_block += line + "\n"  # Add the line and seperate with new line

                        # Send the code block in a separate message
                        if (len(formatted_code_block) > char_limit+100):
                            code_block_chunks = [formatted_code_block[i:i+char_limit]
                                                 for i in range(0, len(formatted_code_block), char_limit)]
                            for chunk in code_block_chunks:
                                if is_reply_all == "True":
                                    await message.channel.send(f"```{chunk}```")
                                else:
                                    await message.followup.send(f"```{chunk}```")
                        elif is_reply_all == "True":
                            await message.channel.send(f"```{formatted_code_block}```")
                        else:
                            await message.followup.send(f"```{formatted_code_block}```")

            else:
                response_chunks = [response[i:i+char_limit]
                                   for i in range(0, len(response), char_limit)]
                for chunk in response_chunks:
                    if is_reply_all == "True":
                        await message.channel.send(chunk)
                    else:
                        await message.followup.send(chunk)
        elif is_reply_all == "True":
            await message.channel.send(response)
        else:
            await message.followup.send(response)
    except Exception as e:
        if is_reply_all == "True":
            await message.channel.send("> **Error: Something went wrong, please try again later!**")
        else:
            await message.followup.send("> **Error: Something went wrong, please try again later!**")
        logger.exception(f"Error while sending message: {e}")


async def send_start_prompt(client):
    import os.path
    if not config.setup_complete():
        logger.warning("Skipped start prompt because setup was not complete")
        return

    discord_channel_id = os.getenv("DISCORD_CHANNEL_ID")
    try:
        if config.config["bot"]["starting_prompt"] is not None:
            prompt = config.config["bot"]["starting_prompt"]
            if (discord_channel_id):
                logger.info(f"Send starting prompt with size {len(prompt)}")
                chat_model = os.getenv("CHAT_MODEL")
                response = ""
                if chat_model == "OFFICIAL":
                    response = f"{response}{await responses.official_handle_response(prompt)}"
                elif chat_model == "UNOFFICIAL":
                    response = f"{response}{await responses.unofficial_handle_response(prompt)}"
                channel = client.get_channel(int(discord_channel_id))
                await channel.send(response)
                logger.info(f"Starting prompt response:{response}")
            else:
                logger.info("No Channel selected. Skip sending starting prompt.")
        else:
            logger.info("No configured prompt")

    except Exception as e:
        logger.exception(f"Error while sending starting prompt: {e}")


def run_discord_bot():
    responses.setup_chatbots()
    client = aclient()

    @client.event
    async def on_ready():
        await send_start_prompt(client)
        await client.tree.sync()
        logger.info(f'{client.user} is now running!')

    @client.tree.command(name="addtoken", description="Set a user token for your requests")
    async def addtoken(interaction: discord.Interaction, *, message: str):
        is_dm = isinstance(interaction.channel, discord.PartialMessageable) \
                and interaction.channel.type == discord.ChannelType.private
        if not is_dm:
            await interaction.response.send_message(
                "You should only use this in a private DM so you do not leak your api token",
                ephemeral=True,
                delete_after=10
            )
            return
        api_token = message.strip()
        if verify_token(api_token):
            logger.info(f"{interaction.user.name} has set a custom api token")
            database.update_token(interaction.user.id, api_token)
            await interaction.response.send_message(
                f"Successfully set your OpenAI api key to {api_token}",
                ephemeral=True,
                delete_after=10
            )
        else:
            await interaction.response.send_message("You provided an invalid api key", ephemeral=True, delete_after=10)

    @client.tree.command(name="chat", description="Have a chat with ChatGPT")
    async def chat(interaction: discord.Interaction, *, message: str):
        if not config.setup_complete():
            await interaction.response.send_message("Setup is not complete", ephemeral=True)
            return
        is_reply_all = os.getenv("REPLYING_ALL")
        if is_reply_all == "True":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **Warn: You already on replyAll mode. If you want to use slash command, switch to normal mode, use `/replyall` again**")
            logger.warning("\x1b[31mYou already on replyAll mode, can't use slash command!\x1b[0m")
            return
        if interaction.user == client.user:
            return
        username = str(interaction.user)
        user_message = message
        channel = str(interaction.channel)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : '{user_message}' ({channel})")
        await send_message(interaction, user_message, is_reply_all)

    @client.tree.command(name="private", description="Toggle private access")
    async def private(interaction: discord.Interaction):
        global isPrivate
        await interaction.response.defer(ephemeral=False)
        if not isPrivate:
            isPrivate = not isPrivate
            logger.warning("\x1b[31mSwitch to private mode\x1b[0m")
            await interaction.followup.send(
                "> **Info: Next, the response will be sent via private message. If you want to switch back to public mode, use `/public`**")
        else:
            logger.info("You already on private mode!")
            await interaction.followup.send(
                "> **Warn: You already on private mode. If you want to switch to public mode, use `/public`**")

    @client.tree.command(name="public", description="Toggle public access")
    async def public(interaction: discord.Interaction):
        global isPrivate
        await interaction.response.defer(ephemeral=False)
        if isPrivate:
            isPrivate = not isPrivate
            await interaction.followup.send(
                "> **Info: Next, the response will be sent to the channel directly. If you want to switch back to private mode, use `/private`**")
            logger.warning("\x1b[31mSwitch to public mode\x1b[0m")
        else:
            await interaction.followup.send(
                "> **Warn: You already on public mode. If you want to switch to private mode, use `/private`**")
            logger.info("You already on public mode!")

    @client.tree.command(name="replyall", description="Toggle replyAll access")
    async def replyall(interaction: discord.Interaction):
        is_reply_all = os.getenv("REPLYING_ALL")
        os.environ["REPLYING_ALL_DISCORD_CHANNEL_ID"] = str(interaction.channel_id)
        await interaction.response.defer(ephemeral=False)
        if is_reply_all == "True":
            os.environ["REPLYING_ALL"] = "False"
            await interaction.followup.send(
                "> **Info: The bot will only response to the slash command `/chat` next. If you want to switch back to replyAll mode, use `/replyAll` again.**")
            logger.warning("\x1b[31mSwitch to normal mode\x1b[0m")
        elif is_reply_all == "False":
            os.environ["REPLYING_ALL"] = "True"
            await interaction.followup.send(
                "> **Info: Next, the bot will response to all message in this channel only.If you want to switch back to normal mode, use `/replyAll` again.**")
            logger.warning("\x1b[31mSwitch to replyAll mode\x1b[0m")

    @client.tree.command(name="replyme", description="Toggle replyAll access for yourself")
    async def replyme(interaction: discord.Interaction):
        global userReplyList
        userReply = os.getenv("USER_REPLY_ALL")
        os.environ["REPLYING_ALL_DISCORD_CHANNEL_ID"] = str(interaction.channel_id)
        await interaction.response.defer(ephemeral=True)
        user = interaction.user.id
        if userReply == "True":
            if user not in userReplyList:  # user not in list so add them
                userReplyList.append(user)
                # os.environ["USER_REPLY_ALL"] = "True"
                await interaction.followup.send(
                    "> **Info: Next, the bot will response to all message in this channel only.If you want to switch back to normal mode, use `/replyMe` again.**")
                logger.warning("\x1b[31mSwitch to replyMe mode for a user.\x1b[0m")
            else:
                if user in userReplyList:  # user already in list, so toggle them off
                    userReplyList.remove(user)
                    await interaction.followup.send(
                        "> **Info: Ok. reply me is now disabled for you.**"
                    )
                    logger.warning("\x1b[31mSwitch to normal mode for user\x1b[0m")
                if len(userReplyList) <= 0:  # if list empty just toggle user reply all to false
                    os.environ["USER_REPLY_ALL"] = "False"
                    await interaction.followup.send(
                        "> **Info: The bot will only response to the slash command `/chat` next. If you want to switch back to replyAll mode, use `/replyMe` again.**")
                    logger.warning("\x1b[31mSwitch to normal mode\x1b[0m")
        elif userReply == "False":
            os.environ["USER_REPLY_ALL"] = "True"
            userReplyList.append(user)
            await interaction.followup.send(
                "> **Info: Next, the bot will response to all message in this channel only.If you want to switch back to normal mode, use `/replyMe` again.**")
            logger.warning("\x1b[31mSwitch to replyMe mode for a user.\x1b[0m")

    @client.tree.command(name="chat-model", description="Switch different chat model")
    @app_commands.choices(choices=[
        app_commands.Choice(name="Official GPT-3.5", value="OFFICIAL"),
        app_commands.Choice(name="Website ChatGPT", value="UNOFFCIAL")
    ])
    async def chat_model(interaction: discord.Interaction, choices: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=False)
        if choices.value == "OFFICIAL":
            os.environ["CHAT_MODEL"] = "OFFICIAL"
            await interaction.followup.send(
                "> **Info: You are now in Official GPT-3.5 model.**\n> You need to set your `OPENAI_API_KEY` in `env` file.")
            logger.warning("\x1b[31mSwitch to OFFICIAL chat model\x1b[0m")
        elif choices.value == "UNOFFCIAL":
            os.environ["CHAT_MODEL"] = "UNOFFICIAL"
            await interaction.followup.send(
                "> **Info: You are now in Website ChatGPT model.**\n> You need to set your `SESSION_TOKEN` or `OPENAI_EMAIL` and `OPENAI_PASSWORD` in `env` file.")
            logger.warning("\x1b[31mSwitch to UNOFFICIAL(Website) chat model\x1b[0m")

    @client.tree.command(name="config", description="Set or clear bot settings")
    @app_commands.choices(choice=[
        app_commands.Choice(name="OpenAI API Token", value="open_ai.api_token"),
        app_commands.Choice(name="OpenAI Chat Model", value="open_ai.chat_model"),
        app_commands.Choice(name="Main Discord Channel", value="discord.channel_id"),
        app_commands.Choice(name="Starting Prompt", value="bot.starting_prompt")
    ])
    async def config_cmd(interaction: discord.Interaction, choice: app_commands.Choice[str], value: str = None):
        await interaction.response.defer(ephemeral=True)
        if choice.value == "open_ai.api_token":
            if value is not None and not verify_token(value):
                await interaction.followup.send("Invalid API token", ephemeral=True)
                return
            config.config["open_ai"]["api_token"] = value
            responses.official_chatbot.api_key = value
        elif choice.value == "open_ai.chat_model":
            if value is None:
                return await interaction.followup.send("Cannot clear the chat model setting", ephemeral=True)
            elif not config.setup_complete():
                return await interaction.followup.send(
                    "Must set an OpenAI API token before changing the model",
                    ephemeral=True
                )
            elif not verify_model(value):
                return await interaction.followup.send(f"Invalid model: {value}", ephemeral=True)
            else:
                config.config["open_ai"]["chat_model"] = value
        elif choice.value == "bot.starting_prompt":
            config.config["bot"]["starting_prompt"] = value
            if value is None:
                return await interaction.followup.send("Cleared the starting prompt", ephemeral=True)
        elif choice.value == "discord.channel_id":
            if value.isdigit() and interaction.guild.get_channel(int(value)):
                config.config["discord"]["channel_id"] = value
            else:
                return await interaction.followup.send(f"Invalid channel id: {value}", ephemeral=True)
        config.save_config()
        if value is None:
            response = f"Reset {choice.name}"
        else:
            response = f"Set {choice.name} to {value}"
        await interaction.followup.send(response, ephemeral=True)

    @client.tree.command(name="reset", description="Complete reset ChatGPT conversation history")
    async def reset(interaction: discord.Interaction):
        chat_model = os.getenv("CHAT_MODEL")
        if chat_model == "OFFICIAL":
            responses.offical_chatbot.reset()
        elif chat_model == "UNOFFICIAL":
            responses.unofficial_chatbot.reset_chat()
        await interaction.response.defer(ephemeral=False)
        await interaction.followup.send("> **Info: I have forgotten everything.**")
        logger.warning(
            "\x1b[31mChatGPT bot has been successfully reset\x1b[0m")
        await send_start_prompt(client)

    @client.tree.command(name="help", description="Show help for the bot")
    async def help(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        await interaction.followup.send(""":star:**BASIC COMMANDS** \n
        - `/chat [message]` Chat with ChatGPT!
        - `/public` ChatGPT switch to public mode
        - `/replyall` ChatGPT switch between replyall mode and default mode
        - `/reset` Clear ChatGPT conversation history\n
        For complete documentation, please visit https://github.com/Zero6992/chatGPT-discord-bot""")
        logger.info(
            "\x1b[31mSomeone need help!\x1b[0m")

    @client.tree.command(name="thread", description="Creates a thread for your use")
    async def thread(interaction: discord.Interaction):
        if isinstance(interaction.channel, discord.TextChannel):
            channel: discord.TextChannel = interaction.channel
            username = str(interaction.user.nick)
            """
            TODO:   - Create thread check to make sure they dont already have a thread
            """
            new_thread = await channel.create_thread(name=username+"'s Thread")
            await interaction.response.send_message(f"Created <#{new_thread.id}>")

            await new_thread.send(interaction.user.mention)

    @client.tree.command(name="stats", description="List stats for users")
    async def stats(interaction: discord.Interaction):
        leaderboard = database.query_leaderboard()
        if len(leaderboard) == 0:
            await interaction.response.send_message("No users have used the bot", ephemeral=True)
            return
        formatted_msg = ""
        for entry in leaderboard:
            formatted_msg += f"<@{entry[0]}>: {entry[1]}\n"
        await interaction.response.send_message(
            formatted_msg,
            ephemeral=False,
            allowed_mentions=discord.AllowedMentions.none()
        )

    @client.event
    async def on_message(message):
        is_reply_all = os.getenv("REPLYING_ALL")

        if is_reply_all == "True" and message.channel.id == int(os.getenv("REPLYING_ALL_DISCORD_CHANNEL_ID")):
            if not config.setup_complete():
                message.channel.send("Setup is not complete")
                return
            if message.author == client.user:
                return
            username = str(message.author)
            user_message = str(message.content)
            channel = str(message.channel)
            logger.info(f"\x1b[31m{username}\x1b[0m : '{user_message}' ({channel})")
            await send_message(message, user_message, is_reply_all)

        userReply = os.getenv("USER_REPLY_ALL")
        global userReplyList
        if userReply == "True" and message.channel.id == int(os.getenv("REPLYING_ALL_DISCORD_CHANNEL_ID")):
            if message.author == client.user:
                return
            if message.author.id in userReplyList:
                username = str(message.author)
                user_message = str(message.content)
                channel = str(message.channel)
                logger.info(f"\x1b[31m{username}\x1b[0m : '{user_message}' ({channel})")
                await send_message(message, user_message, userReply)

        
    @client.tree.command(name="weather", description="Given a city as an argument, grabs weather via api request.")
    async def weather(interaction: discord.Interaction, *, message: str):
        if interaction.user == client.user:
            return
        username = str(interaction.user)
        city = message

        is_reply_all = os.getenv("REPLYING_ALL")
        if is_reply_all == "True":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **Warn: You already on replyAll mode. If you want to use slash command, switch to normal mode, use `/replyall` again**")
            logger.warning("\x1b[31mYou already on replyAll mode, can't use slash command!\x1b[0m")
            return


        channel = str(interaction.channel)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : '{city}' ({channel})")
        
        api_endpoint = "http://api.openweathermap.org/data/2.5/weather"
        api_key = os.getenv('OPENWEATHERMAP_API_KEY')  # Replace with your own API key

        # Make a GET request to the API endpoint with the parameters
        response = requests.get(api_endpoint, params={
            "q": city,
            "appid": api_key,
            "units": "imperial"
        })

        # Check if the response was successful
        if response.status_code == 200:
            # Parse the JSON response to extract the relevant weather data
            json_response = response.json()
            temperature = json_response["main"]["temp"]
            description = json_response["weather"][0]["description"]
            timezone = json_response['timezone']
            hour_diff_timezone = timezone / 3600

        t = time.localtime()
        hour = t.tm_hour
        min = t.tm_min
        sec = t.tm_sec
        overall_time = str(hour) + ":" + str(min) + ":" + str(sec)

        #print(json_response)

        message_to_be_sent = f"Considering the time at UTC 0 is {overall_time}, and we're in the UTC {hour_diff_timezone} timezone and based on the fact that it's {temperature} Fahrenheight and {description} outside,\
        how would you describe the weather in {city}? Tell me the current time and suggest activities appropriate for that time based on the weather"

        await send_message(interaction, message_to_be_sent, is_reply_all)


    TOKEN = os.getenv("DISCORD_BOT_TOKEN")

    client.run(TOKEN)
