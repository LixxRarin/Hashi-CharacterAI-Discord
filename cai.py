import asyncio
import json
import re

from PyCharacterAI import exceptions, get_client, types
from ruamel.yaml import YAML

import utils

# Set up ruamel.yaml in round-trip mode (preserves order and comments)
yaml = YAML(typ='rt')
yaml.preserve_quotes = True
yaml.encoding = "utf-8"


# Global variables
chat_restart = utils.config_yaml["Character_AI"].get(
    "new_chat_on_reset", False)
answer = ""
AI_response = ""


async def get_bot_info(token=utils.config_yaml["Character_AI"]["token"], character_id=utils.config_yaml["Character_AI"]["character_id"]):
    """
    Retrieves the bot's information (name and avatar URL) from the Character.AI service.
    """
    try:
        client = await get_client(token)
        character = await client.character.fetch_character_info(character_id)
    except Exception as e:
        utils.log.critical(
            "Unable to get character information from C.AI: %s", e)
        return None

    # Extract name and avatar URL from the character info.
    char_dict = types.character.Character.get_dict(character)

    return {
        "name": char_dict.get("name"),
        "avatar_url": types.Avatar.get_url(character.avatar),
        "title": char_dict.get("title"),
        "description": char_dict.get("description"),
        "visibility": char_dict.get("visibility"),
        "num_interactions": char_dict.get("num_interactions"),
        "author_username": char_dict.get("author_username")
    }


async def new_chat_id(create):
    """
    Creates a new chat session if required, or returns the existing chat ID.
    Searches for an existing chat in "cache.json" instead of modifying "config.yml".
    Returns a tuple: (chat_id, greeting_message_obj).
    If no new chat is created, greeting_message_obj will be None.
    """
    try:
        # Load cache data from "cache.json"
        cache_data = utils.read_json("cache.json")

        chat_id = cache_data.get("chat_id")

        if create or chat_id is None:
            client = await get_client(token=utils.config_yaml["Character_AI"]["token"])
            chat, greeting_message_obj = await client.chat.create_chat(utils.config_yaml["Character_AI"]["character_id"])
            utils.log.debug("New Chat ID created: %s", chat.chat_id)

            # Update cache.json with new chat_id
            cache_data["chat_id"] = chat.chat_id
            cache_data["setup"] = False

            try:
                with open("cache.json", "w", encoding="utf-8") as file:
                    json.dump(cache_data, file, indent=4)
                utils.log.info("Cache file updated with new Chat ID.")
            except Exception as e:
                utils.log.error(
                    "Failed to update cache file with new Chat ID: %s", e)

            return chat.chat_id, greeting_message_obj
        else:
            return chat_id, None

    except Exception as e:
        utils.log.error("Error handling chat session: %s", e)
        return None, None


async def initialize_messages():
    """
    Initializes and returns the character's first messages.
    If a new chat is created, it uses the greeting message returned from the chat creation.
    Otherwise, it optionally sends a system message.
    """
    global chat_restart

    greeting_message = None
    system_msg_reply = None

    cache_data = utils.read_json("cache.json")

    if not cache_data.get("setup", False):
        try:
            # Get the client and ensure that we have a valid chat ID.
            client = await get_client(token=utils.config_yaml["Character_AI"]["token"])
            chat_id, greeting_obj = await new_chat_id(chat_restart)
            if chat_id is None:
                utils.log.critical(
                    "No valid chat ID available. Aborting response generation.")
                return "No valid chat ID available. Aborting response generation."

            chat = await client.chat.fetch_chat(chat_id)
            chat_restart = False

            # Use the greeting message from the new chat if available.
            if greeting_obj is not None and utils.config_yaml["Options"].get("send_the_greeting_message"):
                greeting_message = greeting_obj.get_primary_candidate().text
                utils.log.debug(
                    "Character greeting message: %s", greeting_message)
                for pattern in utils.config_yaml.get("MessageFormatting", {}).get("remove_IA_text_from", []):
                    greeting_message = re.sub(
                        pattern, '', greeting_message, flags=re.MULTILINE).strip()
        except Exception as e:
            utils.log.critical(
                "Error during chat session initialization: %s", e)
            return

        if utils.config_yaml["Options"].get("send_the_system_message_reply", True) and utils.config_yaml["Character_AI"].get("system_message", None) is not None:
            try:
                cache_data = utils.read_json("cache.json")

                system_reply_obj = await client.chat.send_message(
                    utils.config_yaml["Character_AI"]["character_id"], chat.chat_id, utils.config_yaml["Character_AI"]["system_message"]
                )
                system_msg_reply = system_reply_obj.get_primary_candidate().text
                utils.log.debug(
                    "Character response to system prompt: %s", system_msg_reply)
                for pattern in utils.config_yaml.get("MessageFormatting", {}).get("remove_IA_text_from", []):
                    system_msg_reply = re.sub(
                        pattern, '', system_msg_reply, flags=re.MULTILINE).strip()

            except Exception as e:
                utils.log.error("Error sending system message: %s", e)

    cache_data["setup"] = True
    utils.write_json("cache.json", cache_data)

    return greeting_message, system_msg_reply


async def cai_response(cache_file, message):
    """
    Generates a response from Character.AI based on the cached messages.
    Retries for a number of attempts defined in the configuration and cleans the cache upon failure.
    """
    global chat_restart, AI_response

    async def try_generate():
        """
        Attempts to generate a response from the AI using cached messages.
        Retries up to MAX_TRIES times.
        """
        nonlocal client  # use client from outer scope
        global answer, AI_response

        utils.log.info("Attempting to generate a C.AI response...")
        formatted_data = utils.format_to_send(
            cache_file, message.guild.id, message.channel.id)

        MAX_TRIES = utils.config_yaml["Options"].get(
            "max_response_attempts", 1)
        if MAX_TRIES <= -1:
            MAX_TRIES = len(cache_file)

        for attempt in range(MAX_TRIES):
            if not cache_file:
                utils.log.debug(
                    "No outstanding messages in cache. Stopping generation attempt.")
                break

            try:
                # Set a timeout for sending the message.
                answer = await asyncio.wait_for(
                    client.chat.send_message(
                        utils.config_yaml["Character_AI"]["character_id"], utils.config_yaml["Character_AI"]["chat_id"], formatted_data
                    ),
                    timeout=10
                )
                AI_response = answer.get_primary_candidate().text
                utils.log.debug(
                    "Formatted input: (%s) | AI response: %s", formatted_data, AI_response)
                return  # Exit loop upon successful generation

            except asyncio.exceptions.TimeoutError:
                utils.log.debug(
                    "Timeout on attempt %d. Retrying...", attempt + 1)
                cache_file.pop(0)  # Remove the oldest message and try again
            except exceptions.SessionClosedError:
                utils.log.debug(
                    "Session closed error on attempt %d. Retrying...", attempt + 1)
                # Optionally remove a message or take other corrective action.
            except Exception as e:
                utils.log.critical(
                    "Unexpected error on attempt %d: %s", attempt + 1, e)
                break

        # If generation fails after all attempts, set a fallback response.
        AI_response = (
            "It was impossible to generate the message after several attempts. "
            "Check the logs. Possible problem with the C.AI filter."
        )
        # Clean up the cache in case of persistent failures.
        utils.write_json(utils.config_yaml["Discord"]["messages_cache"], [])

    try:
        client = await get_client(token=utils.config_yaml["Character_AI"]["token"])
        chat_id = utils.config_yaml["Character_AI"]["chat_id"]
        if chat_id is None:
            utils.log.critical(
                "No valid chat ID available. Aborting response generation.")
            return AI_response
        # chat = await client.chat.fetch_chat(chat_id)
        chat_restart = False
    except Exception as e:
        utils.log.critical("Error during chat session initialization: %s", e)
        return ""

    # Attempt to generate the AI response.
    await try_generate()

    # Clean the AI response using configured regex patterns.
    for pattern in utils.config_yaml.get("MessageFormatting", {}).get("remove_IA_text_from", []):
        AI_response = re.sub(pattern, '', AI_response,
                             flags=re.MULTILINE).strip()

    try:
        await client.close_session()
    except Exception as e:
        utils.log.error("Error closing client session: %s", e)

    return AI_response
