# app.py
import boot
import AI_utils
from cai import initialize_messages
import discord
import asyncio
import logging
import platform
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
    """Custom formatter to add colors to log messages based on severity level"""
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

class BridgeBot(commands.Bot):
    """Custom bot class with synchronization control"""
    def __init__(self):
        super().__init__(
            command_prefix="/",
            intents=intents,
            help_command=None
        )
        self.synced = False  # Sync control flag

    async def setup_hook(self):
        """Initial async setup"""
        await self.load_extension('commands')  # Load slash commands
        await AI.sync_config(self)  # Sync AI configurations

    async def on_ready(self):
        """Bot ready event handler"""
        if not self.synced:
            await self.tree.sync()  # Sync slash commands
            self.synced = True
            logging.info("Logged in as %s!", self.user)

            greetings, reply_system = await initialize_messages()

            channel_id = data["Discord"]["channel_bot_chat"][0]
            channel = bot.get_channel(channel_id)

            if greetings is not None:
                await channel.send(greetings)
                logging.info("Greeting message sent")
            if reply_system is not None:
                await channel.send(reply_system)
                logging.info("System message reply message sent")

# Load configuration from config.yml
try:
    with open("config.yml", "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    logging.info("Configuration file 'config.yml' loaded successfully.")
except FileNotFoundError as e:
    logging.critical("Missing configuration file 'config.yml': %s", e)
    exit()

# Initialize the AI bot helper class from AI_utils
AI = AI_utils.discord_AI_bot()

# Configure debug mode
if data["Options"]["debug_mode"]:
    logging.getLogger().addHandler(console_handler)

# Ensure the messages cache file exists
cache_path = data.get("Discord", {}).get("messages_cache", "messages_cache.json")
try:
    with open(cache_path, "r", encoding="utf-8"):
        logging.debug("Cache file '%s' verified", cache_path)
except FileNotFoundError:
    try:
        with open(cache_path, "x", encoding="utf-8") as file:
            file.write("[]")
        logging.info("Created new cache file at '%s'", cache_path)
    except Exception as e:
        logging.critical("Failed to initialize cache file '%s': %s", cache_path, e)
        exit()

# Initialize bot instance
bot = BridgeBot()

@bot.event
async def on_typing(channel, user, when):
    """Handle user typing events"""
    try:
        AI.time_typing(channel, user, bot)
    except Exception as e:
        logging.error("Typing event error: %s", e)

@bot.event
async def on_message(message):
    """Process incoming messages"""
    try:
        asyncio.create_task(AI.read_channel_messages(message, bot))
        asyncio.ensure_future(AI.monitor_inactivity(bot, message))
        await bot.process_commands(message)  # Process traditional commands
    except Exception as e:
        logging.error("Message processing error: %s", e)

# Start the bot
try:
    bot.run(data["Discord"]["token"])
except discord.LoginFailure:
    logging.critical("Invalid authentication token!")
except Exception as e:
    logging.critical("Fatal runtime error: %s", e)
finally:
    input("Press Enter to exit...")