import asyncio
import utils
import re
from PyCharacterAI import get_client, exceptions, types
from ruamel.yaml import YAML
import logging

logger = logging.getLogger(__name__)

# Initialize ruamel.yaml with desired settings.
yaml = YAML()
yaml.preserve_quotes = True
yaml.default_flow_style = False
yaml.encoding = "utf-8"

# Load configuration data from the YAML file.
try:
    with open("config.yml", "r", encoding="utf-8") as file:
        data = yaml.load(file)
    logging.info("Configuration file 'config.yml' loaded successfully.")
except Exception as e:
    logging.critical("Failed to load configuration file 'config.yml': %s", e)
    data = {}

# Global variables
chat_restart = data["CAI"].get("new_chat_on_reset", False)
answer = ""
AI_response = ""

async def get_bot_info():
    """
    Retrieves the bot's information (name and avatar URL) from the Character.AI service.
    """
    try:
        client = await get_client(token=data["CAI"]["token"])
        character = await client.character.fetch_character_info(data["CAI"]["character_id"])
    except Exception as e:
        logging.critical("Unable to get character information from C.AI: %s", e)
        input("Press Enter to exit...")
        exit()

    # Extract name and avatar URL from the character info.
    char_dict = types.character.Character.get_dict(character)
    
    return {
        "name": char_dict.get("name"),
        "avatar_url": types.Avatar.get_url(character.avatar),
        "title" : char_dict.get("title"),
        "description" : char_dict.get("description"),
        "visibility": char_dict.get("visibility"),
        "num_interactions" : char_dict.get("num_interactions"),
        "author_username" : char_dict.get("author_username")
    }

async def new_chat_id(create):
    """
    Creates a new chat session if required, or returns the existing chat ID.
    Updates the configuration file if a new chat session is created.
    Returns a tuple: (chat_id, greeting_message_obj).
    If no new chat is created, greeting_message_obj will be None.
    """
    if create or (data["CAI"].get("chat_id", None) == None):
        try:
            client = await get_client(token=data["CAI"]["token"])
            chat, greeting_message_obj = await client.chat.create_chat(data["CAI"]["character_id"])
            logging.debug("New Chat ID created: %s", chat.chat_id)
            
            # Update the chat_id in configuration data and write back to the config file.
            data["CAI"]["chat_id"] = chat.chat_id

            try:
                with open("config.yml", "w", encoding="utf-8") as file:
                    yaml.dump(data, file)
                logging.info("Configuration file updated with new Chat ID.")
            except Exception as e:
                logging.error("Failed to update configuration file with new Chat ID: %s", e)
            
            return chat.chat_id, greeting_message_obj
        except Exception as e:
            logging.error("Error creating new chat session: %s", e)
            return None, None
    else:
        return data["CAI"]["chat_id"], None

async def initialize_messages():
    """
    Initializes and returns the character's first messages.
    If a new chat is created, it uses the greeting message returned from the chat creation.
    Otherwise, it optionally sends a system message.
    """
    global chat_restart
    
    greeting_message = None 
    system_msg_reply = None

    try:
        # Get the client and ensure that we have a valid chat ID.
        client = await get_client(token=data["CAI"]["token"])
        chat_id, greeting_obj = await new_chat_id(chat_restart)
        if chat_id is None:
            logging.critical("No valid chat ID available. Aborting response generation.")
            return "No valid chat ID available. Aborting response generation."
        
        chat = await client.chat.fetch_chat(chat_id)
        chat_restart = False

        # Use the greeting message from the new chat if available.
        if greeting_obj is not None and data["Options"].get("send_the_greeting_message", True):
            greeting_message = greeting_obj.get_primary_candidate().text
            logging.debug("Character greeting message: %s", greeting_message)
            for pattern in data.get("MessageFormatting", {}).get("remove_IA_text_from", []):
                greeting_message = re.sub(pattern, '', greeting_message, flags=re.MULTILINE).strip()
    except Exception as e:
        logging.critical("Error during chat session initialization: %s", e)
        return

    if data["Options"].get("send_the_system_message_reply", True) and data["CAI"].get("system_message", None) is not None:
        try:
            system_reply_obj = await client.chat.send_message(
                data["CAI"]["character_id"], chat.chat_id, data["CAI"]["system_message"]
            )
            system_msg_reply = system_reply_obj.get_primary_candidate().text
            logging.debug("Character response to system prompt: %s", system_msg_reply)
            for pattern in data.get("MessageFormatting", {}).get("remove_IA_text_from", []):
                system_msg_reply = re.sub(pattern, '', system_msg_reply, flags=re.MULTILINE).strip()
        except Exception as e:
            logging.error("Error sending system message: %s", e)
    
    return greeting_message, system_msg_reply

async def cai_response(cache_file):
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

        logging.info("Attempting to generate a C.AI response...")
        formatted_data = utils.format_to_send(cache_file)
        
        MAX_TRIES = data["Options"].get("max_response_attempts", 1)
        if MAX_TRIES <= -1:
            MAX_TRIES = len(cache_file)

        for attempt in range(MAX_TRIES):
            if not cache_file:
                logging.debug("No outstanding messages in cache. Stopping generation attempt.")
                break

            try:
                # Set a timeout for sending the message.
                answer = await asyncio.wait_for(
                    client.chat.send_message(
                        data["CAI"]["character_id"], data["CAI"]["chat_id"], formatted_data
                    ),
                    timeout=10
                )
                AI_response = answer.get_primary_candidate().text
                logging.debug("Formatted input: (%s) | AI response: %s", formatted_data, AI_response)
                return  # Exit loop upon successful generation

            except asyncio.exceptions.TimeoutError:
                logging.debug("Timeout on attempt %d. Retrying...", attempt + 1)
                cache_file.pop(0)  # Remove the oldest message and try again
            except exceptions.SessionClosedError:
                logging.debug("Session closed error on attempt %d. Retrying...", attempt + 1)
                # Optionally remove a message or take other corrective action.
            except Exception as e:
                logging.critical("Unexpected error on attempt %d: %s", attempt + 1, e)
                break

        # If generation fails after all attempts, set a fallback response.
        AI_response = (
            "It was impossible to generate the message after several attempts. "
            "Check the logs. Possible problem with the C.AI filter."
        )
        # Clean up the cache in case of persistent failures.
        utils.write_json(data["Discord"]["messages_cache"], [])
    
    try:
        client = await get_client(token=data["CAI"]["token"])
        chat_id = data["CAI"]["chat_id"]
        if chat_id is None:
            logging.critical("No valid chat ID available. Aborting response generation.")
            return AI_response
        # chat = await client.chat.fetch_chat(chat_id)
        chat_restart = False
    except Exception as e:
        logging.critical("Error during chat session initialization: %s", e)
        return ""

    # Attempt to generate the AI response.
    await try_generate()

    # Clean the AI response using configured regex patterns.
    for pattern in data.get("MessageFormatting", {}).get("remove_IA_text_from", []):
        AI_response = re.sub(pattern, '', AI_response, flags=re.MULTILINE).strip()

    try:
        await client.close_session()
    except Exception as e:
        logging.error("Error closing client session: %s", e)
    
    return AI_response
