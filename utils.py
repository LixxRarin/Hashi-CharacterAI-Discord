import asyncio
import datetime
import json
import logging
import re
import socket

import yaml
from colorama import Fore, init


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

        # Formata o timestamp usando a hora do registro
        timestamp = datetime.datetime.fromtimestamp(
            record.created).strftime('%H:%M:%S')
        message = record.getMessage()

        # Exibe: [HH:MM:SS] NÍVEL    [arquivo:linha] - mensagem
        return f"{log_color}[{timestamp}] {record.levelname:<8} [{record.filename}:{record.lineno}] {Fore.RESET}- {message}"


def load_config():
    """
    Loads configuration from the YAML file without using logging.
    """
    try:
        with open("config.yml", "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except Exception as e:
        data = {}  # Return an empty dictionary on error
    return data


def setup_logging(debug_mode=False):
    """
    Configures logging: sets up a file handler and a console handler with colors.
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

    # Debug mode does not require additional configuration here
    return root_logger


# First, load the configuration without logging to avoid premature logger creation
config_yaml = load_config()
debug_mode = config_yaml.get("Options", {}).get("debug_mode", False)

# Next, configure logging
log = setup_logging(debug_mode)


async def timeout_async(func, timeout, on_timeout):
    """
    Awaits the execution of 'func' with a specified timeout.
    If a timeout occurs, the 'on_timeout' function is called.
    """
    try:
        await asyncio.wait_for(func(), timeout=timeout)
    except asyncio.TimeoutError:
        logging.warning(
            "Operation timed out after %s seconds. Executing on_timeout handler.", timeout)
        try:
            await on_timeout()
        except Exception as e:
            logging.error("Error in on_timeout handler: %s", e)


def remove_emoji(text):
    """
    Removes emoji characters from the given text, including Discord custom emojis.
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


def test_internet():
    """
    Tests internet connectivity by attempting to connect to www.google.com.
    Returns True if successful, otherwise False.
    """
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        log.debug("Internet connection test succeeded.")
        return True
    except OSError as e:
        log.error("Internet connection test failed: %s", e)
        return False


def capture_message(cache_file, message_info, reply_message=None):
    """
    Captures a message from a specified channel and stores it in a structured cache file.
    """
    # Read existing cache data and convert legacy list format to dict if necessary.
    dados = read_json(cache_file)
    if dados is None or not isinstance(dados, dict):
        dados = {}

    # Extract server_id and channel_id from message_info
    server_id = str(message_info.guild.id)
    channel_id = str(message_info.channel.id)

    # Ensure server and channel keys exist
    if server_id not in dados:
        dados[server_id] = {}
    if channel_id not in dados[server_id]:
        dados[server_id][channel_id] = {}

    # Retrieve format templates from configuration
    template_syntax = config_yaml.get("MessageFormatting", {}).get(
        "user_format_syntax", "{message}")
    reply_template_syntax = config_yaml.get("MessageFormatting", {}).get(
        "user_reply_format_syntax", "{message}")

    # Process message content and author name based on emoji removal configuration
    if config_yaml["MessageFormatting"]["remove_emojis"]["user"]:
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
    for pattern in config_yaml.get("MessageFormatting", {}).get("remove_user_text_from", []):
        syntax["message"] = re.sub(
            pattern, '', syntax["message"], flags=re.MULTILINE).strip()

    # Process reply message if provided
    if reply_message:
        if config_yaml["MessageFormatting"]["remove_emojis"]["user"]:
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
        for pattern in config_yaml.get("MessageFormatting", {}).get("remove_user_text_from", []):
            syntax["reply_message"] = re.sub(
                pattern, '', syntax["reply_message"], flags=re.MULTILINE).strip()

    # Group messages if the last one was from the same user
    try:
        channel_data = dados[server_id][channel_id]
        last_key = list(channel_data.keys())[-1] if channel_data else None
        last_message = channel_data.get(last_key, "")

        if reply_message is None and msg_text not in [None, ""]:
            formatted_message = template_syntax.format(**syntax)
            # Se a última mensagem é do mesmo usuário (verificado pelo final do texto), agrupa a mensagem.
            if last_key and "Message" in last_key and last_message.endswith(syntax["name"]):
                dados[server_id][channel_id][last_key] += f"\n{formatted_message}"
            else:
                new_key = f"Message{len(channel_data) + 1}"
                dados[server_id][channel_id][new_key] = formatted_message
            logging.debug("Captured new message: %s", formatted_message)

        elif reply_message is not None:
            formatted_reply = reply_template_syntax.format(**syntax)
            dados[server_id][channel_id]["Reply"] = formatted_reply
            logging.debug("Captured reply message: %s", formatted_reply)

        write_json(cache_file, dados)
    except Exception as e:
        logging.error("Error while saving message to cache: %s", e)


def format_to_send(cache_data, server_id, channel_id):
    """
    Aggregates cached messages from a specific channel in a specific server into a single string separated by newline characters.

    Parameters:
        cache_data (dict): Dicionário com os dados de cache.
        server_id (str): ID do servidor.
        channel_id (str): ID do canal.

    Returns:
        str: Mensagens combinadas do canal especificado.
    """
    formatted_messages = []
    try:
        channel_data = cache_data[str(server_id)][str(channel_id)]
        for key, text in channel_data.items():
            if isinstance(text, str):
                formatted_messages.append(text)
    except KeyError:
        logging.error(
            "No cache data found for server_id: %s and channel_id: %s", server_id, channel_id)
        return ""

    combined_message = "\n".join(formatted_messages)
    logging.debug("Formatted message to send for server %s, channel %s: %s",
                  server_id, channel_id, combined_message)
    return combined_message


def read_json(file_path):
    """
    Reads and returns the content of a JSON file.
    If an error occurs, logs the error and returns an empty list.
    """
    try:
        with open(file_path, 'r', encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        log.error("Error decoding JSON file '%s': %s", file_path, e)
        return []  # Return an empty list on failure


def write_json(file_path, data):
    """
    Writes the provided data to a JSON file.
    Logs any errors that occur during the write operation.
    """
    try:
        with open(file_path, 'w', encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error("Error saving JSON file '%s': %s", file_path, e)
