import socket
import json
import re
import asyncio
import datetime
import yaml
import logging

logger = logging.getLogger(__name__)

# Load configuration from the YAML file.
try:
    with open("config.yml", "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    logging.info("Configuration file 'config.yml' loaded successfully.")
except Exception as e:
    logging.error("Failed to load configuration file 'config.yml': %s", e)
    data = {}  # Fallback to empty dict (or you can choose to exit here)

# --------------------
# Asynchronous Timeout Function
# --------------------
async def timeout_async(func, timeout, on_timeout):
    """
    Awaits the execution of 'func' with a specified timeout.
    If a timeout occurs, the 'on_timeout' function is called.
    """
    try:
        await asyncio.wait_for(func(), timeout=timeout)
    except asyncio.TimeoutError:
        logging.warning("Operation timed out after %s seconds. Executing on_timeout handler.", timeout)
        try:
            await on_timeout()
        except Exception as e:
            logging.error("Error in on_timeout handler: %s", e)

# --------------------
# Emoji Removal Function
# --------------------
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

# --------------------
# Internet Connection Test
# --------------------
def test_internet():
    """
    Tests internet connectivity by attempting to connect to www.google.com.
    Returns True if successful, otherwise False.
    """
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        logging.info("Internet connection test succeeded.")
        return True
    except OSError as e:
        logging.error("Internet connection test failed: %s", e)
        return False

# --------------------
# Capture Message Function
# --------------------
def capture_message(cache_file, message_info, reply_message=None):
    """
    Captures a message from a specified channel and saves it in the cache file.
    It applies formatting based on the configuration and supports both normal and reply messages.
    """
    # Read existing cache data
    dados = read_json(cache_file)
    if dados is None:
        dados = []
    
    # Retrieve format templates from configuration
    template_syntax = data.get("MessageFormatting", {}).get("user_format_syntax", "{message}")
    reply_template_syntax = data.get("MessageFormatting", {}).get("user_reply_format_syntax", "{message}")

    # Remove user emojis (if true)
    if data["MessageFormatting"]["remove_emojis"]["user"]:
        message_info["message"] = remove_emoji(message_info["message"])
        message_info["name"] = remove_emoji(message_info["name"])
    
        if reply_message is not None:
            reply_message["message"] = remove_emoji(reply_message["message"])
            reply_message["name"] = remove_emoji(reply_message["name"])

    # Prepare data for formatting
    syntax = {
        "time": datetime.datetime.now().strftime("%H:%M"),
        "username": message_info.get("username", ""),
        "name": message_info.get("name", ""),
        "message": message_info.get("message", ""),
    }

    # Remove unwanted text patterns from the message using regex patterns from config.
    for pattern in data.get("MessageFormatting", {}).get("remove_user_text_from", []):
        syntax["message"] = re.sub(pattern, '', syntax["message"], flags=re.MULTILINE).strip()

    # Process reply message if provided.
    if reply_message:
        syntax.update({
            "reply_username": reply_message.get("username", ""),
            "reply_name": reply_message.get("name", ""),
            "reply_message": reply_message.get("message", ""),
        })
        # Clean reply message text using same patterns.
        for pattern in data.get("MessageFormatting", {}).get("remove_user_text_from", []):
            syntax["reply_message"] = re.sub(pattern, '', syntax["reply_message"], flags=re.MULTILINE).strip()

    # Attempt to format and store the message.
    try:
        if reply_message is None:
            msg = template_syntax.format(**syntax)
            dados.append({"Message": msg})
            logging.info("Captured new message: %s", msg)
        else:
            # Format as a reply
            formatted_message = template_syntax.format(**syntax)
            formatted_reply = reply_template_syntax.format(**syntax)
            dados.append({"Reply": formatted_reply})
            logging.info("Captured reply message: %s", formatted_reply)
        
        write_json(cache_file, dados)
    except Exception as e:
        logging.error("Error while saving message to cache: %s", e)

# --------------------
# Format Message for Sending
# --------------------
def format_to_send(cache_data):
    """
    Aggregates cached messages into a single string separated by newline characters.
    """
    formatted_messages = []
    for entry in cache_data:
        if isinstance(entry, dict):
            if "Message" in entry:
                formatted_messages.append(entry["Message"])
            elif "Reply" in entry:
                formatted_messages.append(entry["Reply"])
    combined_message = "\n".join(formatted_messages)
    logging.debug("Formatted message to send: %s", combined_message)
    return combined_message

# --------------------
# JSON File Operations
# --------------------
def read_json(file_path):
    """
    Reads and returns the content of a JSON file.
    If an error occurs, logs the error and returns an empty list.
    """
    try:
        with open(file_path, 'r', encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        logging.error("Error decoding JSON file '%s': %s", file_path, e)
        return []  # Return an empty list on failure

def write_json(file_path, data):
    """
    Writes the provided data to a JSON file.
    Logs any errors that occur during the write operation.
    """
    try:
        with open(file_path, 'w', encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        logging.info("JSON file '%s' written successfully.", file_path)
    except Exception as e:
        logging.error("Error saving JSON file '%s': %s", file_path, e)