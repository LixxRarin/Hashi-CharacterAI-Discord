import asyncio
import platform
import os
from typing import Dict, Any, Optional, List

import discord
from colorama import init
from discord.ext import commands

import updater
import AI_utils
import utils
from cai import initialize_session_messages
import webhook  # Import webhook to access session_data and webhook_send
from utils import load_session_cache, process_session_updates

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
        # Load extensions
        if os.path.exists("slash_commands.py"):
            await self.load_extension('slash_commands')
        await self.load_extension('webhook')

        # Ensure session.json exists
        if not os.path.exists("session.json"):
            utils.write_json("session.json", {})

        # Ensure messages_cache.json exists
        if not os.path.exists("messages_cache.json"):
            utils.write_json("messages_cache.json", {})

        # Load session cache
        await load_session_cache()

        # Start session update processor
        self.update_processor = asyncio.create_task(process_session_updates())

        # Sync AI configurations for each webhook
        await AI.sync_config(self)

    async def close(self):
        """Cleanup when bot is shutting down"""
        # Cancel the update processor task
        if hasattr(self, 'update_processor'):
            self.update_processor.cancel()
            try:
                await self.update_processor
            except asyncio.CancelledError:
                pass

        # Ensure all pending updates are processed
        await utils.session_update_queue.join()

        await super().close()

    async def on_ready(self):
        """Bot ready event handler"""
        if not self.synced:
            await self.tree.sync()  # Sync slash commands
            self.synced = True
            utils.log.info("Logged in as %s!", self.user)

            # Initialize all webhooks with their respective character configurations
            await self._initialize_all_webhooks()

    async def _initialize_all_webhooks(self):
        """Initialize all webhooks with their respective character configurations"""
        utils.log.info("Initializing all webhooks...")

        # Iterate over all sessions (each webhook) in session.json
        for server_id, server_data in webhook.session_data.items():
            channels = server_data.get("channels", {})
            for channel_id, session in channels.items():
                # Skip if already set up
                if session.get("setup_has_already", False):
                    utils.log.debug(
                        "Channel %s in server %s already set up, skipping initialization",
                        channel_id, server_id
                    )
                    continue

                # Get the channel object (if available)
                channel = self.get_channel(int(channel_id))
                if not channel:
                    utils.log.error(
                        "Channel with ID %s not found.", channel_id)
                    continue

                # Initialize session messages for this webhook using its own character_id
                utils.log.info(
                    "Initializing webhook for channel %s (character_id: %s)",
                    channel_id, session.get("character_id")
                )

                greetings, reply_system = await initialize_session_messages(session, server_id, channel_id)

                if not session.get("webhook_url"):
                    utils.log.error(
                        "No webhook URL found for channel %s in server %s", channel_id, server_id)
                    continue

                # Send greeting message if available
                if greetings:
                    try:
                        await webhook.webhook_send(session["webhook_url"], greetings)
                        utils.log.info(
                            "Greeting message sent via webhook for channel %s", channel_id)
                    except Exception as e:
                        utils.log.error(
                            "Error sending greeting via webhook for channel %s: %s", channel_id, e)

                # Send system message if available
                if reply_system:
                    try:
                        await webhook.webhook_send(session["webhook_url"], reply_system)
                        utils.log.info(
                            "System message sent via webhook for channel %s", channel_id)
                    except Exception as e:
                        utils.log.error(
                            "Error sending system message via webhook for channel %s: %s", channel_id, e)


# Initialize the AI bot helper class from AI_utils
AI = AI_utils.discord_AI_bot()

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
        # Skip messages from the bot itself
        if message.author.id == bot.user.id:
            return

        # Process the message for AI response
        await AI.read_channel_messages(message, bot)

        # Start monitoring for inactivity
        await AI.monitor_inactivity(bot, message)

        # Process traditional commands
        await bot.process_commands(message)
    except Exception as e:
        utils.log.error("Message processing error: %s", e)


# Start the bot
if __name__ == "__main__":
    try:
        bot.run(utils.config_yaml["Discord"]["token"])
    except discord.LoginFailure:
        utils.log.critical("Invalid authentication token!")
    except Exception as e:
        utils.log.critical("Fatal runtime error: %s", e)
    finally:
        input("Press Enter to exit...")
