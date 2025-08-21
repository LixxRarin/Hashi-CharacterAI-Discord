import time
import asyncio
from typing import Dict, Any, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
import AI.cai as cai

class AIManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.webhook_locks: Dict[str, asyncio.Lock] = {}

    async def _fetch_avatar(self, url: str) -> Optional[bytes]:
        """Fetch avatar image from URL."""
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
                func.log.debug("Created webhook with URL: %s", webhook_obj.url)
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

    async def _update_bot_profile(self, guild: discord.Guild, character_info: Dict[str, Any]):
        """
        Update the bot's nickname and avatar in the server to match the selected character.
        """
        try:
            avatar_bytes = None
            async with aiohttp.ClientSession() as session:
                async with session.get(character_info["avatar_url"]) as response:
                    if response.status == 200:
                        avatar_bytes = await response.read()
            me = guild.me
            await me.edit(nick=character_info["name"])
            if avatar_bytes:
                try:
                    await self.bot.user.edit(avatar=avatar_bytes)
                except Exception:
                    pass
            func.log.info(f"Bot profile updated in guild {guild.id}")
        except Exception as e:
            func.log.error(f"Failed to update bot profile: {e}")

    @app_commands.command(name="setup", description="Setup the AI for a channel (bot or webhook mode).")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to use the AI",
        character_id="Character ID",
        mode="Mode: bot or webhook"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Webhook", value="webhook"),
        app_commands.Choice(name="Bot", value="bot")
    ])
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        character_id: str,
        mode: app_commands.Choice[str]
    ):
        """
        Setup command to configure an AI for a server channel (bot or webhook mode).
        """
        await interaction.response.defer(ephemeral=True)
        character_info = await cai.get_bot_info(character_id=character_id)
        if character_info is None:
            await interaction.followup.send("Invalid character_id...", ephemeral=True)
            return

        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)
        session = func.get_session_data(server_id, channel_id_str) or {}

        config_default = {
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

        if mode.value == "webhook":
            # Webhook setup
            if channel_id_str not in self.webhook_locks:
                self.webhook_locks[channel_id_str] = asyncio.Lock()
            async with self.webhook_locks[channel_id_str]:
                WB_url = session.get("webhook_url")
                if session and "webhook_url" in session:
                    # Try to update existing webhook
                    try:
                        async with aiohttp.ClientSession() as aio_session:
                            webhook_obj = discord.Webhook.from_url(WB_url, session=aio_session)
                            avatar_bytes = await self._fetch_avatar(character_info["avatar_url"])
                            if avatar_bytes is None:
                                avatar_bytes = b""
                            await webhook_obj.edit(
                                name=character_info["name"],
                                avatar=avatar_bytes,
                                reason=f"Updating Webhook - {character_info['name']}"
                            )
                        func.log.info(f"Updated existing webhook for channel {channel_id_str}")
                    except Exception as e:
                        func.log.error(f"Failed to update webhook: {e}")
                        WB_url = await self._create_webhook(interaction, channel, character_info)
                        if WB_url is None:
                            await interaction.followup.send("Failed to create webhook.", ephemeral=True)
                            return
                else:
                    WB_url = await self._create_webhook(interaction, channel, character_info)
                    if WB_url is None:
                        func.log.error(f"Failed to create webhook for channel {channel_id_str}")
                        return

                session.update({
                    "channel_name": channel.name,
                    "character_id": character_id,
                    "webhook_url": WB_url,
                    "mode": "webhook",
                    "setup_has_already": False,
                    "last_message_time": time.time(),
                    "awaiting_response": False,
                    "alt_token": session.get("alt_token"),
                    "muted_users": session.get("muted_users", []),
                    "config": session.get("config", config_default)
                })

                await func.update_session_data(server_id, channel_id_str, session)
                greetings, reply_system = await cai.initialize_session_messages(session, server_id, channel_id_str)
                session = func.get_session_data(server_id, channel_id_str)
                if session:
                    session["setup_has_already"] = True
                    await func.update_session_data(server_id, channel_id_str, session)
                if greetings:
                    try:
                        await webhook_send(WB_url, greetings, session)
                        func.log.info("Greeting message sent via webhook for channel %s", channel_id_str)
                    except Exception as e:
                        func.log.error("Error sending greeting via webhook for channel %s: %s", channel_id_str, e)
                if reply_system:
                    try:
                        await webhook_send(WB_url, reply_system, session)
                        func.log.info("System message sent via webhook for channel %s", channel_id_str)
                    except Exception as e:
                        func.log.error("Error sending system message via webhook for channel %s: %s", channel_id_str, e)
                await interaction.followup.send(
                    f"Setup successful!\n**AI name:** {character_info['name']}\n**Character ID:** `{character_id}`\n**Channel:** {channel.mention}\n**Mode:** Webhook",
                    ephemeral=True
                )
        else:
            # Bot mode setup
            await self._update_bot_profile(interaction.guild, character_info)
            session.update({
                "channel_name": channel.name,
                "character_id": character_id,
                "mode": "bot",
                "setup_has_already": False,
                "last_message_time": time.time(),
                "awaiting_response": False,
                "alt_token": session.get("alt_token"),
                "muted_users": session.get("muted_users", []),
                "config": session.get("config", config_default)
            })
            await func.update_session_data(server_id, channel_id_str, session)
            greetings, reply_system = await cai.initialize_session_messages(session, server_id, channel_id_str)
            session = func.get_session_data(server_id, channel_id_str)
            if session:
                session["setup_has_already"] = True
                await func.update_session_data(server_id, channel_id_str, session)
            if greetings:
                try:
                    await channel.send(greetings)
                    func.log.info(f"Greeting message sent as bot in channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Error sending greeting as bot: {e}")
            if reply_system:
                try:
                    await channel.send(reply_system)
                    func.log.info(f"System message sent as bot in channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Error sending system message as bot: {e}")
            await interaction.followup.send(
                f"Setup successful!\n**AI name:** {character_info['name']}\n**Character ID:** `{character_id}`\n**Channel:** {channel.mention}\n**Mode:** Bot",
                ephemeral=True
            )

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
        """
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)
        session = func.get_session_data(server_id, channel_id_str)
        if session is None:
            await interaction.followup.send(
                "Session data not found. Please run the setup command first.",
                ephemeral=True
            )
            return
        session["setup_has_already"] = False
        session["chat_id"] = chat_id if chat_id else None
        await func.update_session_data(server_id, channel_id_str, session)
        greetings, reply_system = await cai.initialize_session_messages(session, server_id, channel_id_str)
        session = func.get_session_data(server_id, channel_id_str)
        if session:
            session["setup_has_already"] = True
            await func.update_session_data(server_id, channel_id_str, session)
        if session.get("mode") == "webhook":
            WB_url = session.get("webhook_url")
            if not WB_url:
                func.log.error(f"Webhook URL not found in session data for channel {channel_id_str}.")
                await interaction.followup.send(
                    "Webhook URL not found in session data.",
                    ephemeral=True
                )
                return
            if greetings and WB_url:
                try:
                    await webhook_send(WB_url, greetings, session)
                    func.log.info("Greeting message sent via webhook for channel %s", channel_id_str)
                except Exception as e:
                    func.log.error("Error sending greeting via webhook for channel %s: %s", channel_id_str, e)
            if reply_system and WB_url:
                try:
                    await webhook_send(WB_url, reply_system, session)
                    func.log.info("System message sent via webhook for channel %s", channel_id_str)
                except Exception as e:
                    func.log.error("Error sending system message via webhook for channel %s: %s", channel_id_str, e)
        else:
            channel_obj = interaction.guild.get_channel(int(channel_id_str))
            if greetings and channel_obj:
                try:
                    await channel_obj.send(greetings)
                    func.log.info(f"Greeting message sent as bot in channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Error sending greeting as bot: {e}")
            if reply_system and channel_obj:
                try:
                    await channel_obj.send(reply_system)
                    func.log.info(f"System message sent as bot in channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Error sending system message as bot: {e}")
        await interaction.followup.send(
            f"Chat ID configuration successful! Current chat ID: `{session['chat_id']}`",
            ephemeral=True
        )

    @app_commands.command(name="remove_ai", description="Remove the AI from a channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to remove AI from"
    )
    async def remove_ai(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        Remove the AI (bot or webhook) from the channel.
        """
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)
        session = func.get_session_data(server_id, channel_id_str)
        if not session:
            await interaction.followup.send(f"No AI found in channel {channel.mention}.", ephemeral=True)
            func.log.warning(f"Attempted to remove AI from channel {channel_id_str}, but no session was set.")
            return
        if session.get("mode") == "webhook":
            webhook_url = session.get("webhook_url")
            if webhook_url:
                try:
                    async with aiohttp.ClientSession() as aio_session:
                        webhook_obj = discord.Webhook.from_url(webhook_url, session=aio_session)
                        await webhook_obj.delete(reason="AI removed from channel")
                    func.log.info(f"Deleted webhook for channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Failed to delete webhook: {e}")
        await func.remove_session_data(server_id, channel_id_str)
        await interaction.followup.send(f"AI successfully removed from channel {channel.mention}.", ephemeral=True)
        func.log.info(f"AI removed from channel {channel_id_str}")

async def webhook_send(url: str, message: str, session_config: dict) -> None:
    """
    Send a message via webhook.
    """
    async with aiohttp.ClientSession() as session:
        webhook_obj = discord.Webhook.from_url(url, session=session)
        if session_config["config"].get("send_message_line_by_line", False):
            lines = message.split('\n')
            for line in lines:
                if line.strip():
                    await webhook_obj.send(line)
        else:
            await webhook_obj.send(message)

async def setup(bot):
    await bot.add_cog(AIManager(bot))
    asyncio.create_task(cai.process_response_queue())