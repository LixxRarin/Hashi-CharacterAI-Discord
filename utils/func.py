import asyncio
import datetime
import json
import logging
import re
import socket
import threading
from typing import Any, Dict, Optional, Callable, Awaitable, TypeVar, Union

import yaml
from colorama import Fore, init

# Type definitions
T = TypeVar('T')
SessionData = Dict[str, Any]
CacheData = Dict[str, Dict[str, Dict[str, str]]]


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log messages based on severity level."""

    def format(self, record):
        LOG_COLORS = {
            "DEBUG": Fore.CYAN,
            "INFO": Fore.GREEN,
            "WARNING": Fore.YELLOW,
            "ERROR": Fore.RED,
            "CRITICAL": Fore.RED + "\033[1m",
        }
        log_color = LOG_COLORS.get(record.levelname, Fore.WHITE)

        # Format timestamp using record time
        timestamp = datetime.datetime.fromtimestamp(
            record.created).strftime('%H:%M:%S')
        message = record.getMessage()

        # Display: [HH:MM:SS] LEVEL    [file:line] - message
        return f"{log_color}[{timestamp}] {record.levelname:<8} [{record.filename}:{record.lineno}] {Fore.RESET}- {message}"


def load_config() -> Dict[str, Any]:
    """
    Loads configuration from the YAML file without using logging.

    Returns:
        Dict[str, Any]: Configuration data from config.yml
    """
    try:
        with open("config.yml", "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except Exception:
        data = {}  # Return an empty dictionary on error
    return data


def setup_logging(debug_mode=False) -> logging.Logger:
    """
    Configures logging: sets up a file handler and a console handler with colors.

    Args:
        debug_mode (bool): Whether to enable debug logging to console

    Returns:
        logging.Logger: Configured root logger
    """
    # Initialize colorama with autoreset enabled
    init(autoreset=True)

    # Remove any existing handlers to ensure basicConfig applies correctly
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Configure file logging
    logging.basicConfig(
        level=logging.DEBUG,            # Global logging level
        filename="app.log",             # Log file name
        filemode="a",                   # Append mode
        format="[%(filename)s] %(levelname)s : %(message)s",
        encoding="utf-8",
    )

    # Create a console handler with colors
    console_handler = logging.StreamHandler()

    if debug_mode:
        console_handler.setLevel(logging.DEBUG)
    else:
        console_handler.setLevel(logging.INFO)

    console_handler.setFormatter(ColoredFormatter())

    # Add the console handler to the root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(console_handler)

    return root_logger


# First, load the configuration without logging to avoid premature logger creation
config_yaml = load_config()
debug_mode = config_yaml.get("Options", {}).get("debug_mode", False)

# Next, configure logging
log = setup_logging(debug_mode)

# Session management
session_cache: Dict[str, Any] = {}
session_update_queue = asyncio.Queue()
session_lock = threading.Lock()

# Add this configuration to your config.yml file
config_yaml = load_config()


async def timeout_async(func: Callable[[], Awaitable[T]], timeout: float,
                        on_timeout: Callable[[], Awaitable[None]]) -> None:
    """
    Awaits the execution of 'func' with a specified timeout.
    If a timeout occurs, the 'on_timeout' function is called.

    Args:
        func: Async function to execute
        timeout: Timeout in seconds
        on_timeout: Async function to call if timeout occurs
    """
    try:
        await asyncio.wait_for(func(), timeout=timeout)
    except asyncio.TimeoutError:
        log.warning(
            "Operation timed out after %s seconds. Executing on_timeout handler.", timeout)
        try:
            await on_timeout()
        except Exception as e:
            log.error("Error in on_timeout handler: %s", e)


def remove_emoji(text: str) -> str:
    """
    Removes emoji characters from the given text, including Discord custom emojis.

    Args:
        text: Text to process

    Returns:
        str: Text with emojis removed
    """
    # Regex pattern for Unicode emojis
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"   # Symbols & pictographs
        "\U0001F680-\U0001F6FF"   # Transport & map symbols
        "\U0001F700-\U0001F77F"   # Alchemical symbols
        "\U0001F780-\U0001F7FF"   # Geometric shapes extended
        "\U0001F800-\U0001F8FF"   # Supplemental arrows-C
        "\U0001F900-\U0001F9FF"   # Supplemental symbols and pictographs
        "\U0001FA00-\U0001FA6F"   # Chess symbols, etc.
        "\U0001FA70-\U0001FAFF"   # Symbols and pictographs extended-A
        "\U00002702-\U000027B0"   # Dingbats
        "\U000024C2-\U0001F251"   # Enclosed characters
        "]+", flags=re.UNICODE)

    # Regex pattern for Discord custom emojis (static and animated)
    discord_emoji_pattern = re.compile(r"<a?:\w+:\d+>")

    # Remove all emojis from the text
    text = re.sub(emoji_pattern, "", text)
    text = re.sub(discord_emoji_pattern, "", text)

    return text.strip()


def test_internet() -> bool:
    """
    Tests internet connectivity by attempting to connect to www.google.com.

    Returns:
        bool: True if successful, otherwise False
    """
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        log.debug("Internet connection test succeeded.")
        return True
    except OSError as e:
        log.error("Internet connection test failed: %s", e)
        return False


def is_channel_active(server_id: str, channel_id: str) -> bool:
    """
    Check if a channel is still active in the session data.

    Args:
        server_id: Server ID
        channel_id: Channel ID

    Returns:
        bool: True if the channel is active, False otherwise
    """
    return channel_id in session_cache.get(server_id, {}).get("channels", {})


def capture_message(message_info, reply_message=None) -> None:
    """
    Captures a message from a specified channel and stores it in the messages_cache.json file.
    Prevents duplicate messages from being added to the cache.

    Args:
        message_info: Discord message object
        reply_message: Optional reply message object
    """
    # Skip capturing if the message was sent by a webhook.
    if getattr(message_info, "webhook_id", None):
        return

    # Read existing cache data
    dados = read_json("messages_cache.json")
    if dados is None:
        dados = {}

    # Extract server_id and channel_id from message_info
    server_id = str(message_info.guild.id)
    channel_id = str(message_info.channel.id)

    # Check if the channel is still active before capturing the message
    if not is_channel_active(server_id, channel_id):
        return

    # Ensure server and channel keys exist
    if server_id not in dados:
        dados[server_id] = {}
    if channel_id not in dados[server_id]:
        dados[server_id][channel_id] = {}

    channel_data = get_session_data(server_id, channel_id)
    
    if not channel_data:
        return
    
    # Use the first AI's configuration for message formatting
    # (all AIs in a channel should have the same formatting settings)
    first_ai_name = next(iter(channel_data.keys()))
    session = channel_data[first_ai_name]

    # Retrieve format templates from configuration
    template_syntax = session["config"].get("user_format_syntax", "{message}")
    reply_template_syntax = session["config"].get(
        "user_reply_format_syntax", "{message}")

    # Process message content and author name based on emoji removal configuration
    if session["config"]["remove_user_emoji"]:
        msg_text = remove_emoji(message_info.content)
        msg_name = remove_emoji(
            message_info.author.global_name or message_info.author.name)
    else:
        msg_text = message_info.content
        msg_name = message_info.author.global_name or message_info.author.name

    # Prepare data for formatting
    syntax = {
        "time": datetime.datetime.now().strftime("%H:%M"),
        "username": message_info.author.name,
        "name": msg_name,
        "message": msg_text,
    }

    # Remove unwanted text patterns from message content
    for pattern in session["config"].get("remove_user_text_from", []):
        syntax["message"] = re.sub(
            pattern, '', syntax["message"], flags=re.MULTILINE).strip()

    # Process reply message if provided
    if reply_message:
        if session["config"]["remove_user_emoji"]:
            reply_text = remove_emoji(reply_message.content)
            reply_name = remove_emoji(
                reply_message.author.global_name or reply_message.author.name)
        else:
            reply_text = reply_message.content
            reply_name = reply_message.author.global_name or reply_message.author.name

        syntax.update({
            "reply_username": reply_message.author.name,
            "reply_name": reply_name,
            "reply_message": reply_text,
        })
        for pattern in session["config"].get("remove_user_text_from", []):
            syntax["reply_message"] = re.sub(
                pattern, '', syntax["reply_message"], flags=re.MULTILINE).strip()

    # Group messages if the last one was from the same user
    try:
        channel_data = dados[server_id][channel_id]

        if reply_message is None and msg_text not in [None, ""]:
            formatted_message = template_syntax.format(**syntax)

            # Check if this exact message already exists in the cache
            message_already_exists = False
            for key, existing_message in channel_data.items():
                if existing_message == formatted_message:
                    message_already_exists = True
                    log.debug(
                        "Skipping duplicate message for channel %s", channel_id)
                    break

            if not message_already_exists:
                last_key = list(channel_data.keys()
                                )[-1] if channel_data else None
                last_message = channel_data.get(last_key, "")

                # If the last message is from the same user (checked via message ending), group the message.
                if last_key and "Message" in last_key and last_message.endswith(syntax["name"]):
                    dados[server_id][channel_id][last_key] += f"\n{formatted_message}"
                else:
                    new_key = f"Message{len(channel_data) + 1}"
                    dados[server_id][channel_id][new_key] = formatted_message
                log.debug("Captured new message for channel %s: %s",
                          channel_id, formatted_message)

        elif reply_message is not None:
            formatted_reply = reply_template_syntax.format(**syntax)
            # Check if this reply already exists
            if "Reply" not in channel_data or channel_data["Reply"] != formatted_reply:
                dados[server_id][channel_id]["Reply"] = formatted_reply
                log.debug("Captured reply message for channel %s: %s",
                          channel_id, formatted_reply)

    except Exception as e:
        log.error(
            "Error while saving message to cache for channel %s: %s", channel_id, e)

    write_json("messages_cache.json", dados)


def format_to_send(cache_data: CacheData, server_id: str, channel_id: str) -> str:
    """
    Aggregates cached messages from a specific channel in a specific server into a single string.

    Args:
        cache_data: Dictionary containing cached data
        server_id: Server ID
        channel_id: Channel ID

    Returns:
        str: Combined messages from the specified channel
    """
    formatted_messages = []
    try:
        server_data = cache_data.get(str(server_id))
        if not server_data:
            log.error("No cache data found for server_id: %s", server_id)
            return ""

        channel_data = server_data.get(str(channel_id))
        if not channel_data:
            log.error(
                "No cache data found for channel_id: %s in server %s", channel_id, server_id)
            return ""

        for key, text in channel_data.items():
            if isinstance(text, str):
                formatted_messages.append(text)

    except Exception as e:
        log.error("Error formatting cached messages: %s", e)
        return ""

    combined_message = "\n".join(formatted_messages)
    log.debug("Formatted message to send for server %s, channel %s: %s",
              server_id, channel_id, combined_message[:100] + "..." if len(combined_message) > 100 else combined_message)
    return combined_message


def read_json(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Reads and returns the content of a JSON file.

    Args:
        file_path: Path to the JSON file

    Returns:
        Optional[Dict[str, Any]]: JSON content or None if error
    """
    with session_lock:
        try:
            with open(file_path, 'r', encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            log.warning(
                "JSON file '%s' not found. Creating new file.", file_path)
            write_json(file_path, {})
            return {}
        except json.JSONDecodeError:
            log.error(
                "Error decoding JSON file '%s'. Creating new file.", file_path)
            write_json(file_path, {})
            return {}
        except Exception as e:
            log.error("Error reading JSON file '%s': %s", file_path, e)
            return None


def write_json(file_path: str, data: Dict[str, Any]) -> None:
    """
    Writes the provided data to a JSON file.

    Args:
        file_path: Path to the JSON file
        data: Data to write
    """
    with session_lock:
        try:
            with open(file_path, 'w', encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
        except Exception as e:
            log.error("Error saving JSON file '%s': %s", file_path, e)


async def load_session_cache() -> None:
    """Loads session data from session.json into memory cache"""
    global session_cache
    session_cache = await asyncio.to_thread(read_json, "session.json") or {}
    log.info(f"Loaded session cache with {len(session_cache)} servers")


async def process_session_updates() -> None:
    """Background task to process session updates from the queue"""
    log.info("Starting session update processor")
    while True:
        try:
            server_id, channel_id, new_data = await session_update_queue.get()
            log.debug(
                f"Processing session update for server {server_id}, channel {channel_id}")

            session_data = await asyncio.to_thread(read_json, "session.json") or {}

            if server_id not in session_data:
                session_data[server_id] = {"channels": {}}
            if "channels" not in session_data[server_id]:
                session_data[server_id]["channels"] = {}

            session_data[server_id]["channels"][channel_id] = new_data

            await asyncio.to_thread(write_json, "session.json", session_data)

            # Update in-memory cache
            if server_id not in session_cache:
                session_cache[server_id] = {"channels": {}}
            if "channels" not in session_cache[server_id]:
                session_cache[server_id]["channels"] = {}
            session_cache[server_id]["channels"][channel_id] = new_data

            session_update_queue.task_done()
            log.debug(
                f"Completed session update for server {server_id}, channel {channel_id}")
        except Exception as e:
            log.error(f"Error in process_session_updates: {e}")
            # Ensure the queue item is marked as done even on error
            session_update_queue.task_done()


async def update_session_data(server_id: str, channel_id: str, new_data: Dict[str, Any]) -> None:
    """
    Updates the session data for a specific server and channel.

    Args:
        server_id: Server ID
        channel_id: Channel ID
        new_data: New session data
    """
    # Update in-memory cache immediately
    if server_id not in session_cache:
        session_cache[server_id] = {"channels": {}}
    if "channels" not in session_cache[server_id]:
        session_cache[server_id]["channels"] = {}
    session_cache[server_id]["channels"][channel_id] = new_data

    # Queue the update for persistent storage
    await session_update_queue.put((server_id, channel_id, new_data))
    log.debug(
        f"Queued session update for server {server_id}, channel {channel_id}")


def get_session_data(server_id: str, channel_id: str) -> Optional[Dict[str, Any]]:
    """
    Gets session data for a specific server and channel from the in-memory cache.

    Args:
        server_id: Server ID
        channel_id: Channel ID

    Returns:
        Optional[Dict[str, Any]]: Session data or None if not found
    """
    return session_cache.get(server_id, {}).get("channels", {}).get(channel_id)


async def clear_message_cache(server_id: str, channel_id: str) -> None:
    """
    Limpa o cache de mensagens para um canal específico.

    Args:
        server_id: ID do servidor
        channel_id: ID do canal
    """
    cache_data = await asyncio.to_thread(read_json, "messages_cache.json")
    if cache_data and server_id in cache_data and channel_id in cache_data[server_id]:
        del cache_data[server_id][channel_id]
        await asyncio.to_thread(write_json, "messages_cache.json", cache_data)
        log.info(
            f"Cleared message cache for server {server_id}, channel {channel_id}")


async def remove_session_data(server_id: str, channel_id: str) -> None:
    """
    Remove os dados da sessão para um canal específico.

    Args:
        server_id: ID do servidor
        channel_id: ID do canal
    """
    global session_cache
    if server_id in session_cache and channel_id in session_cache[server_id].get("channels", {}):
        del session_cache[server_id]["channels"][channel_id]
        await update_session_data(server_id, channel_id, None)
        log.info(
            f"Removed session data for server {server_id}, channel {channel_id}")

    # Limpa o cache de mensagens
    await clear_message_cache(server_id, channel_id)


async def remove_sent_messages_from_cache(server_id: str, channel_id: str) -> None:
    """
    Remove sent messages from cache for a specific channel.
    Only removes messages that have been processed by the AI.

    Args:
        server_id: Server ID
        channel_id: Channel ID
    """
    cache_data = await asyncio.to_thread(read_json, "messages_cache.json")
    if cache_data and server_id in cache_data and channel_id in cache_data[server_id]:
        # Instead of keeping only the last message, we'll clear the cache completely
        # This is because the AI has already processed all messages in the cache
        cache_data[server_id][channel_id] = {}
        await asyncio.to_thread(write_json, "messages_cache.json", cache_data)
        log.info(
            f"Removed processed messages from cache for server {server_id}, channel {channel_id}")
