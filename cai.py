import asyncio
import re
import aiohttp
from typing import Dict, Any, Tuple, Optional, Callable, Awaitable, TypeVar, Union, List

from PyCharacterAI import exceptions, get_client, types

import utils

T = TypeVar('T')

# Global response variables
answer = ""
AI_response = ""

# Response queue for handling multiple concurrent requests
response_queue = asyncio.Queue()
# Active response tasks by channel ID
active_response_tasks: Dict[str, asyncio.Task] = {}
# Semaphore to limit concurrent API calls to Character.AI
api_semaphore = asyncio.Semaphore(3)  # Allow up to 3 concurrent API calls


async def retry_with_backoff(func: Callable[[], Awaitable[T]], max_retries: int = 3,
                             base_delay: float = 1) -> T:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds between retries

    Returns:
        T: Result of the function call

    Raises:
        Exception: The last exception encountered after all retries
    """
    for attempt in range(max_retries):
        try:
            return await func()
        except (aiohttp.ClientError, asyncio.TimeoutError, exceptions.SessionClosedError) as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            utils.log.warning(
                f"Attempt {attempt + 1} failed. Retrying in {delay} seconds. Error: {str(e)}")
            await asyncio.sleep(delay)


async def get_bot_info(token: Optional[str] = None,
                       character_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves the bot's information (name and avatar URL) from the Character.AI service.

    Args:
        token: The Character.AI API token
        character_id: The specific character ID to fetch info for

    Returns:
        Optional[Dict[str, Any]]: Dictionary with character information or None if failed
    """
    if not token:
        token = utils.config_yaml["Character_AI"]["token"]

    if not character_id:
        utils.log.error("No character_id provided to get_bot_info")
        return None

    try:
        async with api_semaphore:
            client = await get_client(token)
            character = await client.character.fetch_character_info(character_id)

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
    except Exception as e:
        utils.log.critical(
            "Unable to get character information from C.AI: %s", e)
        return None


async def new_chat_id(create_new: bool, session: Dict[str, Any],
                      server_id: str, channel_id_str: str) -> Tuple[Optional[str], Optional[Any]]:
    """
    Creates a new chat session if required for the given session.
    Uses session.json for storing individual session data.

    Args:
        create_new: Boolean flag to force creation of a new chat
        session: The session data for this channel
        server_id: The Discord server ID
        channel_id_str: The Discord channel ID

    Returns:
        Tuple[Optional[str], Optional[Any]]: (chat_id, greeting_message_obj)
    """
    character_id = session.get("character_id")
    if not character_id:
        utils.log.error(
            "No character_id found in session for channel %s", channel_id_str)
        return None, None

    # Check if we already have a valid chat_id and don't need to create a new one
    existing_chat_id = session.get("chat_id")
    if existing_chat_id and not create_new:
        utils.log.info("Using existing chat_id for channel %s: %s",
                       channel_id_str, existing_chat_id)
        return existing_chat_id, None

    # If we need to create a new chat (either forced or no existing chat_id)
    try:
        async with api_semaphore:
            client = await get_client(token=utils.config_yaml["Character_AI"]["token"])
            chat, greeting_message_obj = await client.chat.create_chat(character_id)
            utils.log.info("New Chat ID created for channel %s: %s",
                           channel_id_str, chat.chat_id)

            session["chat_id"] = chat.chat_id
            session["setup_has_already"] = False

            # Update session data
            await utils.update_session_data(server_id, channel_id_str, session)

            return chat.chat_id, greeting_message_obj
    except Exception as e:
        utils.log.error(
            "Failed to create new chat session for channel %s: %s", channel_id_str, e)
        return None, None


async def initialize_session_messages(session: Dict[str, Any], server_id: str,
                                      channel_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Initializes and returns the greeting and system messages for a given session,
    using the session's own character_id and chat_id.

    Args:
        session: The session data for this channel
        server_id: The Discord server ID
        channel_id: The Discord channel ID

    Returns:
        Tuple[Optional[str], Optional[str]]: (greeting_message, system_msg_reply)
    """
    greeting_message = None
    system_msg_reply = None

    character_id = session.get("character_id")
    if not character_id:
        utils.log.error(
            "No character_id found in session for channel %s", channel_id)
        return None, None

    # Skip if setup has already been done
    if session.get("setup_has_already", False):
        utils.log.debug(
            "Session for channel %s already set up, skipping initialization", channel_id)
        return None, None

    # Use existing chat_id or create a new one
    create_new_chat = utils.config_yaml["Character_AI"].get(
        "new_chat_on_reset", False)
    chat_id, greeting_obj = await new_chat_id(create_new_chat, session, server_id, channel_id)

    if chat_id is None:
        utils.log.critical(
            "No valid chat ID available for channel %s", channel_id)
        return None, None

    try:
        async with api_semaphore:
            client = await get_client(token=utils.config_yaml["Character_AI"]["token"])
            chat = await client.chat.fetch_chat(chat_id)

            if greeting_obj is not None and utils.config_yaml["Options"].get("send_the_greeting_message"):
                greeting_message = greeting_obj.get_primary_candidate().text
                utils.log.debug(
                    "Character greeting message for channel %s: %s", channel_id, greeting_message)
                for pattern in utils.config_yaml.get("MessageFormatting", {}).get("remove_IA_text_from", []):
                    greeting_message = re.sub(
                        pattern, '', greeting_message, flags=re.MULTILINE).strip()
    except Exception as e:
        utils.log.critical(
            "Error during chat session initialization for channel %s: %s", channel_id, e)
        return None, None

    if utils.config_yaml["Options"].get("send_the_system_message_reply", True) and utils.config_yaml["Character_AI"].get("system_message", None) is not None:
        try:
            async with api_semaphore:
                client = await get_client(token=utils.config_yaml["Character_AI"]["token"])
                system_reply_obj = await client.chat.send_message(
                    character_id, chat.chat_id, utils.config_yaml["Character_AI"]["system_message"]
                )
                system_msg_reply = system_reply_obj.get_primary_candidate().text
                utils.log.debug(
                    "Character response to system prompt for channel %s: %s", channel_id, system_msg_reply)
                for pattern in utils.config_yaml.get("MessageFormatting", {}).get("remove_IA_text_from", []):
                    system_msg_reply = re.sub(
                        pattern, '', system_msg_reply, flags=re.MULTILINE).strip()
        except Exception as e:
            utils.log.error(
                "Error sending system message for channel %s: %s", channel_id, e)

    session["setup_has_already"] = True
    await utils.update_session_data(server_id, channel_id, session)

    return greeting_message, system_msg_reply


async def cai_response(messages: Dict[str, Any], message,
                       chat_id: Optional[str] = None,
                       character_id: Optional[str] = None) -> str:
    """
    Generates a response from Character.AI based on the cached messages.

    Args:
        messages: The cached messages to send to the AI
        message: The Discord message object
        chat_id: The Character.AI chat ID
        character_id: The Character.AI character ID

    Returns:
        str: The AI's response
    """
    global AI_response

    if not chat_id or not character_id:
        utils.log.error("Missing chat_id or character_id for AI response")
        return "Error: Missing chat configuration. Please check the logs."

    client = None

    try:
        utils.log.info(
            f"Initializing Character.AI client for character_id: {character_id}, chat_id: {chat_id}")

        async with api_semaphore:
            client = await get_client(token=utils.config_yaml["Character_AI"]["token"])

            async def try_generate():
                nonlocal client
                global answer, AI_response

                formatted_data = utils.format_to_send(
                    messages, message.guild.id, message.channel.id)
                if not formatted_data:
                    utils.log.warning("No formatted data to send to AI")
                    AI_response = "I couldn't process your message. Please try again."
                    return

                utils.log.debug(
                    "Sending message to Character.AI: %s",
                    formatted_data[:100] +
                    "..." if len(formatted_data) > 100 else formatted_data
                )

                try:
                    answer = await client.chat.send_message(
                        character_id, chat_id, formatted_data
                    )

                    AI_response = answer.get_primary_candidate().text
                    utils.log.debug(
                        "AI response received (character_id: %s): %s",
                        character_id, AI_response[:100] +
                        "..." if len(AI_response) > 100 else AI_response
                    )
                except Exception as e:
                    utils.log.error(f"Error in try_generate: {e}")
                    raise

            await retry_with_backoff(try_generate, max_retries=3, base_delay=2)

            if not AI_response or AI_response.isspace():
                utils.log.warning("Received empty response from Character.AI")
                AI_response = "I'm sorry, but I couldn't generate a response. Please try again."

    except exceptions.SessionClosedError:
        utils.log.error(
            "Session closed error. Attempting to create a new chat.")
        try:
            async with api_semaphore:
                if client is None:
                    client = await get_client(token=utils.config_yaml["Character_AI"]["token"])
                new_chat, _ = await client.chat.create_chat(character_id)
                chat_id = new_chat.chat_id
                utils.log.info(f"New chat created with ID: {chat_id}")

                # Update session with new chat_id
                server_id = str(message.guild.id)
                channel_id = str(message.channel.id)
                session = utils.get_session_data(server_id, channel_id)
                if session:
                    session["chat_id"] = chat_id
                    await utils.update_session_data(server_id, channel_id, session)

                await retry_with_backoff(try_generate, max_retries=2, base_delay=2)
        except Exception as e:
            utils.log.error(f"Failed to create new chat: {str(e)}")
            AI_response = "I'm having trouble connecting. Please try again later."

    except Exception as e:
        utils.log.error(f"Error generating AI response: {str(e)}")
        AI_response = "An error occurred while generating a response. Please try again later."

    finally:
        # Clean up the response by removing unwanted patterns
        for pattern in utils.config_yaml.get("MessageFormatting", {}).get("remove_IA_text_from", []):
            AI_response = re.sub(pattern, '', AI_response,
                                 flags=re.MULTILINE).strip()
        try:
            if client:
                await client.close_session()
        except Exception as e:
            utils.log.error(f"Error closing client session: {str(e)}")

    utils.log.info(f"Final AI response: {AI_response[:100]}...")
    return AI_response


async def process_response_queue():
    """
    Background task to process the response queue.
    Ensures that multiple responses are handled in order without overwhelming the API.
    """
    utils.log.info("Starting response queue processor")
    while True:
        try:
            task_data = await response_queue.get()
            server_id = task_data["server_id"]
            channel_id = task_data["channel_id"]
            message = task_data["message"]
            chat_id = task_data["chat_id"]
            character_id = task_data["character_id"]
            callback = task_data["callback"]

            utils.log.debug(f"Processing response for channel {channel_id}")
            utils.log.debug(
                f"Generating AI response with chat_id: {chat_id}, character_id: {character_id}")

            try:
                # Get cached messages
                cached_data = await asyncio.to_thread(utils.read_json, "messages_cache.json") or {}

                # Generate response
                response = await cai_response(
                    cached_data,
                    message,
                    chat_id=chat_id,
                    character_id=character_id
                )

                # Execute callback with response
                await callback(response)
            except Exception as e:
                utils.log.error(
                    f"Error processing response for channel {channel_id}: {e}")
                # Try to notify the callback about the error
                try:
                    await callback(f"I'm sorry, but I encountered an error: {str(e)}")
                except Exception:
                    pass
            finally:
                # Mark task as done
                response_queue.task_done()
                utils.log.debug(f"Completed response for channel {channel_id}")

                # Small delay to prevent API rate limiting
                await asyncio.sleep(0.5)

        except Exception as e:
            utils.log.error(f"Critical error in process_response_queue: {e}")
            try:
                response_queue.task_done()
            except Exception:
                pass
            # Add a small delay to prevent CPU spinning in case of repeated errors
            await asyncio.sleep(1)


async def queue_response(server_id: str, channel_id: str, message,
                         chat_id: str, character_id: str,
                         callback: Callable[[str], Awaitable[None]]) -> None:
    """
    Queue a response request to be processed.

    Args:
        server_id: Server ID
        channel_id: Channel ID
        message: Discord message object
        chat_id: Character.AI chat ID
        character_id: Character.AI character ID
        callback: Async function to call with the response
    """
    await response_queue.put({
        "server_id": server_id,
        "channel_id": channel_id,
        "message": message,
        "chat_id": chat_id,
        "character_id": character_id,
        "callback": callback
    })
    utils.log.debug(f"Queued response request for channel {channel_id}")
