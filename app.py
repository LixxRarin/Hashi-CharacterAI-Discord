import boot
import AI_utils
import asyncio
import logging
import platform
import discord
import yaml
from discord.ext import commands
from colorama import init, Fore

# Initialize colorama for cross-platform color support
init(autoreset=True)

# Define colors for different log levels
LOG_COLORS = {
    "DEBUG": Fore.CYAN,      # Light Blue
    "INFO": Fore.GREEN,      # Green
    "WARNING": Fore.YELLOW,  # Yellow
    "ERROR": Fore.RED,       # Red
    "CRITICAL": Fore.RED + "\033[1m",  # Bold Red
}

class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log messages based on severity level."""
    def format(self, record):
        log_color = LOG_COLORS.get(record.levelname, Fore.WHITE)  # Default to white
        return f"{log_color}[{record.filename}] {record.levelname} : {Fore.RESET}{record.message}"

# For Windows compatibility with asyncio
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Configure logging for file output
logging.basicConfig(
    level=logging.DEBUG,
    filename="app.log",
    format="[%(filename)s] %(levelname)s : %(message)s",
    encoding="utf-8",
)

# Configure console logging with colors
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Set console log level
console_handler.setFormatter(ColoredFormatter())  # Apply color formatting

# Set up Discord intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Create both a discord.Client and a commands.Bot instance
client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="!", intents=intents)

# Load configuration from config.yml
try:
    with open("config.yml", "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    logging.info("Configuration file 'config.yml' loaded successfully.")
except FileNotFoundError as e:
    logging.critical("The configuration file 'config.yml' does not exist: %s", e)
    exit()

if data["Options"]["debug_mode"]:
    logging.getLogger().addHandler(console_handler)

# Ensure the messages cache file exists; if not, create it.
cache_path = data.get("Discord", {}).get("messages_cache", "messages_cache.json")
try:
    with open(cache_path, "r", encoding="utf-8"):
        logging.debug("Cache file '%s' exists.", cache_path)
except FileNotFoundError:
    try:
        with open(cache_path, "x", encoding="utf-8") as file:
            file.write("[]")
        logging.info("Cache file '%s' created successfully.", cache_path)
    except Exception as e:
        logging.critical("Failed to create cache file '%s': %s", cache_path, e)
        exit()

# Initialize the AI bot helper class from AI_utils
AI = AI_utils.discord_AI_bot()

@client.event
async def on_ready():
    """
    Event handler for when the bot is ready.
    Synchronizes the bot's profile with the AI configuration.
    """
    try:
        await AI.sync_config(client)
        logging.info("Logged in as %s!", client.user)
    except Exception as e:
        logging.error("Error during on_ready event: %s", e)

@client.event
async def on_typing(channel, user, when):
    """
    Event handler triggered when a user is typing in a channel.
    Updates the last message time.
    """
    try:
        AI.time_typing(channel, user, client)
    except Exception as e:
        logging.error("Error in on_typing event: %s", e)

@client.event
async def on_message(message):
    """
    Event handler for processing incoming messages.
    Starts asynchronous tasks for capturing channel messages and monitoring inactivity.
    """
    try:
        asyncio.create_task(AI.read_channel_messages(message, client))
        asyncio.ensure_future(AI.monitor_inactivity(client, message))
    except Exception as e:
        logging.error("Error in on_message event: %s", e)

# Start the client using the Discord token from the configuration
try:
    client.run(data["Discord"]["token"])
except Exception as e:
    logging.critical("Error while running the client: %s", e)
    input("Press Enter to exit...")
    exit()
