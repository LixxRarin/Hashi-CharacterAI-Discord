import time
import asyncio
from typing import Dict, Any, Optional, List

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
import AI.cai as cai

# Global session data
session_data: Dict[str, Any] = {}


class WebHook(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.webhook_locks: Dict[str, asyncio.Lock] = {}

    async def _fetch_avatar(self, url: str) -> Optional[bytes]:
        """
        Fetch avatar image from URL.

        Args:
            url: Avatar URL

        Returns:
            Optional[bytes]: Avatar image data or None if failed
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.read()
                return None

    async def _create_webhook(self, interaction: discord.Interaction,
                              channel: discord.TextChannel,
                              character_info: Dict[str, Any]) -> Optional[str]:
        """
        Create a webhook in the specified channel.

        Args:
            interaction: Discord interaction
            channel: Discord channel
            character_info: Character information

        Returns:
            Optional[str]: Webhook URL or None if failed
        """
        if interaction.guild.me.guild_permissions.manage_webhooks:
            try:
                avatar_bytes = await self._fetch_avatar(character_info["avatar_url"])
                if avatar_bytes is None:
                    avatar_bytes = b""
                webhook_obj = await channel.create_webhook(
                    name=character_info["name"],
                    avatar=avatar_bytes,
                    reason=f"Webhook - {character_info['name']}"
                )
                func.log.debug("Created webhook with URL: %s",
                               webhook_obj.url)
                return webhook_obj.url
            except discord.Forbidden:
                await interaction.followup.send(
                    "I do not have permission to create webhooks in this channel.",
                    ephemeral=True
                )
                return None
            except discord.HTTPException as e:
                await interaction.followup.send(
                    f"An error occurred while creating the webhook: {e}",
                    ephemeral=True
                )
                return None
            except Exception as e:
                await interaction.followup.send(
                    f"Error: {e}",
                    ephemeral=True
                )
                return None
        else:
            await interaction.followup.send(
                "I do not have permission to manage webhooks in this server.",
                ephemeral=True
            )
            return None

    @app_commands.command(name="chat_id", description="Setup a chat ID for the AI")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="AI Channel",
        chat_id="Chat ID (Leave empty to create a new Chat ID)"
    )
    async def chat_id(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        chat_id: str = None
    ):
        """
        Updates the chat_id in session.json and initializes session messages.
        If chat_id is left empty, cai.initialize_session_messages() will create one automatically.

        Args:
            interaction: Discord interaction.
            channel: Discord channel for the AI.
            chat_id: Chat ID to set (optional).
        """
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)

        # Retrieve the session data for the channel.
        session = func.get_session_data(server_id, channel_id_str)

        if session is None:
            func.log.error(
                f"No session data found for channel {channel_id_str}. Run setup first.")
            await interaction.followup.send(
                "Session data not found. Please run the setup command first.",
                ephemeral=True
            )
            return

        session["setup_has_already"] = False
        # Update the chat_id in session data (set to None if empty so that it auto-creates)
        session["chat_id"] = chat_id if chat_id else None
        await func.update_session_data(server_id, channel_id_str, session)
        func.log.info(
            f"Updated chat ID for channel {channel_id_str} to {session['chat_id']}"
        )

        # Initialize session messages, which will also create a chat_id automatically if needed.
        greetings, reply_system = await cai.initialize_session_messages(session, server_id, channel_id_str)

        # Update session data with new chat_id flag
        session = func.get_session_data(server_id, channel_id_str)
        if session:
            session["setup_has_already"] = True
            await func.update_session_data(server_id, channel_id_str, session)

        # Get the webhook URL from session data to send messages.
        WB_url = session.get("webhook_url")
        if not WB_url:
            func.log.error(
                f"Webhook URL not found in session data for channel {channel_id_str}.")
            await interaction.followup.send(
                "Webhook URL not found in session data.",
                ephemeral=True
            )
            return

        # Send greeting message via webhook if available.
        if greetings:
            try:
                await webhook_send(WB_url, greetings, session)
                func.log.info(
                    "Greeting message sent via webhook for channel %s", channel_id_str)
            except Exception as e:
                func.log.error(
                    "Error sending greeting via webhook for channel %s: %s", channel_id_str, e)

        # Send system message via webhook if available.
        if reply_system:
            try:
                await webhook_send(WB_url, reply_system, session)
                func.log.info(
                    "System message sent via webhook for channel %s", channel_id_str)
            except Exception as e:
                func.log.error(
                    "Error sending system message via webhook for channel %s: %s", channel_id_str, e)

        await interaction.followup.send(
            f"Chat ID configuration successful! Current chat ID: `{session['chat_id']}`",
            ephemeral=True
        )

    @app_commands.command(name="setup", description="Setup an AI for the server.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to monitor for the IA", character_id="Character ID")
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel, character_id: str):
        """
        Setup command to configure an AI for a server channel.

        Args:
            interaction: Discord interaction
            channel: Discord channel
            character_id: Character.AI character ID
        """
        await interaction.response.defer(ephemeral=True)

        # Get character info
        character_info = await cai.get_bot_info(character_id=character_id)
        if character_info is None:
            await interaction.followup.send("Invalid character_id...", ephemeral=True)
            return

        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)

        func.log.info(
            f"Setting up webhook for server {server_id}, channel {channel_id_str}")

        # Get or create webhook lock for this channel
        if channel_id_str not in self.webhook_locks:
            self.webhook_locks[channel_id_str] = asyncio.Lock()

        # Acquire lock to prevent concurrent webhook operations on the same channel
        async with self.webhook_locks[channel_id_str]:
            # Check if webhook already exists
            session = func.get_session_data(server_id, channel_id_str)

            if session and "webhook_url" in session:
                # Update existing webhook
                WB_url = session["webhook_url"]
                try:
                    async with aiohttp.ClientSession() as session:
                        webhook_obj = discord.Webhook.from_url(
                            WB_url, session=session)
                        avatar_bytes = await self._fetch_avatar(character_info["avatar_url"])
                        if avatar_bytes is None:
                            avatar_bytes = b""
                        await webhook_obj.edit(
                            name=character_info["name"],
                            avatar=avatar_bytes,
                            reason=f"Updating Webhook - {character_info['name']}"
                        )
                    func.log.info(
                        f"Updated existing webhook for channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Failed to update webhook: {e}")
                    # If update fails, create a new webhook
                    WB_url = await self._create_webhook(interaction, channel, character_info)
                    if WB_url is None:
                        await interaction.followup.send("Failed to create webhook.", ephemeral=True)
                        return
            else:
                # Create a new webhook
                WB_url = await self._create_webhook(interaction, channel, character_info)
                if WB_url is None:
                    func.log.error(
                        f"Failed to create webhook for channel {channel_id_str}")
                    return

            # Update session data
            new_session_data = {
                "channel_name": channel.name,
                "character_id": character_id,
                "webhook_url": WB_url,
                "chat_id": None,
                "setup_has_already": False,
                "last_message_time": time.time(),
                "awaiting_response": False,
                "config": {
                    "use_cai_avatar": True,
                    "use_cai_display_name": True,
                    "new_chat_on_reset": False,
                    "system_message": """[DO NOT RESPOND TO THIS MESSAGE!]
You are connected to a Discord channel, where several people may be present. Your objective is to interact with them in the chat.
Greet the participants and introduce yourself by fully translating your message into English.
Now, send your message introducing yourself in the chat, following the language of this message!""",
                    "send_the_greeting_message": True,
                    "send_the_system_message_reply": True,
                    "send_message_line_by_line": True,
                    "delay_for_generation": 5,
                    "remove_ai_text_from": [r'\*[^*]*\*', r'\[[^\]]*\]', '"'],
                    "remove_user_text_from": [r'\*[^*]*\*', r'\[[^\]]*\]'],
                    "remove_user_emoji": True,
                    "remove_ai_emoji": True,
                    "user_reply_format_syntax": """┌──[🔁 Replying to @{reply_username} - {reply_name}]
│   ├─ 📝 Reply: {reply_message}
│   └─ ⏳ {time} ~ @{username} - {name}
|   └─ 📢 Message: {message}
└───────────────────────────────────────""",
                    "user_format_syntax": """┌──[💬]
│   ├─ ⏳ {time} ~ @{username} - {name}
│   └─ 📢 Message: {message}
└───────────────────────────────────────"""
                }
            }
            await func.update_session_data(server_id, channel_id_str, new_session_data)

            # Initialize session messages
            greetings, reply_system = await cai.initialize_session_messages(new_session_data, server_id, channel_id_str)

            # Update session data with new chat_id
            session = func.get_session_data(server_id, channel_id_str)
            if session:
                session["setup_has_already"] = True
                await func.update_session_data(server_id, channel_id_str, session)

            # Send greeting and system messages
            if greetings:
                try:
                    await webhook_send(WB_url, greetings, session)
                    func.log.info(
                        "Greeting message sent via webhook for channel %s", channel_id_str)
                except Exception as e:
                    func.log.error(
                        "Error sending greeting via webhook for channel %s: %s", channel_id_str, e)

            if reply_system:
                try:
                    await webhook_send(WB_url, reply_system, session)
                    func.log.info(
                        "System message sent via webhook for channel %s", channel_id_str)
                except Exception as e:
                    func.log.error(
                        "Error sending system message via webhook for channel %s: %s", channel_id_str, e)

            await interaction.followup.send(
                f"Configuration successful!\nChannel: {channel.mention}\nCharacter ID: `{character_id}`.\nAI name: {character_info['name']}\nWebhook: {WB_url}",
                ephemeral=True
            )

    @app_commands.command(name="remove_bot", description="Remove a bot and its webhook from the system.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel from which to remove the bot")
    async def remove_bot(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        Remove a bot and its associated webhook from the system.

        Args:
            interaction: Discord interaction
            channel: Discord channel from which to remove the bot
        """
        await interaction.response.defer(ephemeral=True)

        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)

        func.log.info(
            f"Removing bot from server {server_id}, channel {channel_id_str}")

        # Get or create webhook lock for this channel
        if channel_id_str not in self.webhook_locks:
            self.webhook_locks[channel_id_str] = asyncio.Lock()

        # Acquire lock to prevent concurrent webhook operations on the same channel
        async with self.webhook_locks[channel_id_str]:
            # Check if session exists for this channel
            session = func.get_session_data(server_id, channel_id_str)

            if not session:
                await interaction.followup.send(f"No bot found in channel {channel.mention}.", ephemeral=True)
                return

            # Remove webhook
            webhook_url = session.get("webhook_url")
            if webhook_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        webhook = discord.Webhook.from_url(
                            webhook_url, session=session)
                        await webhook.delete(reason="Bot removed from channel")
                    func.log.info(
                        f"Deleted webhook for channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Failed to delete webhook: {e}")

            # Remove session data
            await func.remove_session_data(server_id, channel_id_str)

            # Não é mais necessário chamar clear_message_cache separadamente,
            # pois já está incluído em remove_session_data

            await interaction.followup.send(f"Bot successfully removed from channel {channel.mention}.", ephemeral=True)


async def load_session_data():
    """Load session data from session.json"""
    global session_data
    session_data = await asyncio.to_thread(func.read_json, "session.json") or {}
    func.log.info(
        f"Loaded webhook session data with {len(session_data)} servers")


async def webhook_send(url: str, message: str, session_config: str) -> None:
    """
    Send a message via webhook.

    Args:
        url: Webhook URL
        message: Message to send
    """
    async with aiohttp.ClientSession() as session:
        webhook_obj = discord.Webhook.from_url(url, session=session)

        if session_config["config"].get("send_message_line_by_line", False):
            lines = message.split('\n')
            for line in lines:
                if line.strip():  # Skip empty lines
                    await webhook_obj.send(line)
        else:
            await webhook_obj.send(message)


async def setup(bot):
    """Setup function for the webhook cog"""
    await bot.add_cog(WebHook(bot))

    # Start the response queue processor
    asyncio.create_task(cai.process_response_queue())
