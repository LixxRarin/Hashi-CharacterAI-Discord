import asyncio
import platform

import discord
from colorama import init
from discord.ext import commands

import updater
import AI_utils
import utils
from cai import initialize_messages

# Initialize colorama for colored logs
init(autoreset=True)

# For Windows compatibility with asyncio
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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
        await self.load_extension('slash_commands')  # Load slash commands
        await AI.sync_config(self)  # Sync AI configurations

    async def on_ready(self):
        """Bot ready event handler"""
        if not self.synced:
            await self.tree.sync()  # Sync slash commands
            self.synced = True
            utils.log.info("Logged in as %s!", self.user)

            greetings, reply_system = await initialize_messages()

            channel_id = utils.config_yaml["Discord"]["channel_bot_chat"][0]
            channel = bot.get_channel(channel_id)

            if greetings is not None:
                await channel.send(greetings)
                utils.log.info("Greeting message sent")
            if reply_system is not None:
                await channel.send(reply_system)
                utils.log.info("System message reply message sent")


# Initialize the AI bot helper class from AI_utils
AI = AI_utils.discord_AI_bot()


# Ensure the messages cache file exists
cache_path = utils.config_yaml.get("Discord", {}).get(
    "messages_cache", "messages_cache.json")
try:
    with open(cache_path, "r", encoding="utf-8"):
        utils.log.debug("Cache file '%s' verified", cache_path)
except FileNotFoundError:
    try:
        with open(cache_path, "x", encoding="utf-8") as file:
            file.write("[]")
        utils.log.info("Created new cache file at '%s'", cache_path)
    except Exception as e:
        utils.log.critical(
            "Failed to initialize cache file '%s': %s", cache_path, e)
        exit()

# Initialize bot instance
bot = BridgeBot()


@bot.event
async def on_typing(channel, user, when):
    """Handle user typing events"""
    try:
        AI.time_typing(channel, user, bot)
    except Exception as e:
        utils.log.error("Typing event error: %s", e)


@bot.event
async def on_message(message):
    """Process incoming messages"""
    try:
        asyncio.create_task(AI.read_channel_messages(message, bot))
        asyncio.ensure_future(AI.monitor_inactivity(bot, message))
        await bot.process_commands(message)  # Process traditional commands
    except Exception as e:
        utils.log.error("Message processing error: %s", e)

# Start the bot
try:
    bot.run(utils.config_yaml["Discord"]["token"])
except discord.LoginFailure:
    utils.log.critical("Invalid authentication token!")
except Exception as e:
    utils.log.critical("Fatal runtime error: %s", e)
finally:
    input("Press Enter to exit...")
