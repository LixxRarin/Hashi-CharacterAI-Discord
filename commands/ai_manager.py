import time
import asyncio
from typing import Dict, Any, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
import AI.cai as cai

# Note: session_data is now managed through func.session_cache

class AIManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.webhook_locks: Dict[str, asyncio.Lock] = {}

    def _generate_unique_ai_name(self, base_name: str, existing_names: set) -> str:
        """
        Generate a unique AI name by adding a suffix if the name already exists.
        
        Args:
            base_name: The desired AI name
            existing_names: Set of existing AI names in the channel
            
        Returns:
            str: A unique AI name
        """
        if base_name not in existing_names:
            return base_name
        
        # Try adding _2, _3, etc. until we find a unique name
        counter = 2
        while f"{base_name}_{counter}" in existing_names:
            counter += 1
        
        return f"{base_name}_{counter}"

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

    @app_commands.command(name="setup", description="Setup an AI for a channel (bot or webhook mode).")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to use the AI",
        character_id="Character ID",
        ai_name="Name for this AI instance (e.g., 'Amelia', 'Outra_IA')",
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
        ai_name: str,
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
        
        # Get the channel's AI configurations
        channel_data = func.get_session_data(server_id, channel_id_str) or {}
        
        # Generate a unique AI name if the requested name already exists
        existing_names = set(channel_data.keys())
        unique_ai_name = self._generate_unique_ai_name(ai_name, existing_names)
        
        # Notify user if the name was changed
        if unique_ai_name != ai_name:
            await interaction.followup.send(f"AI name '{ai_name}' already exists. Using '{unique_ai_name}' instead.", ephemeral=True)
        
        ai_name = unique_ai_name
        
        # Create new AI session
        session = {}

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
                # Create webhook for this AI instance
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

                # Add this AI to the channel's AI configurations
                channel_data[ai_name] = session
                await func.update_session_data(server_id, channel_id_str, channel_data)
                
                greetings, reply_system = await cai.initialize_session_messages(session, server_id, channel_id_str)
                if greetings:
                    try:
                        await webhook_send(WB_url, greetings, session)
                        func.log.info("Greeting message sent via webhook for AI %s in channel %s", ai_name, channel_id_str)
                    except Exception as e:
                        func.log.error("Error sending greeting via webhook for AI %s in channel %s: %s", ai_name, channel_id_str, e)
                if reply_system:
                    try:
                        await webhook_send(WB_url, reply_system, session)
                        func.log.info("System message sent via webhook for AI %s in channel %s", ai_name, channel_id_str)
                    except Exception as e:
                        func.log.error("Error sending system message via webhook for AI %s in channel %s: %s", ai_name, channel_id_str, e)
                
                # Mark setup as complete
                channel_data[ai_name]["setup_has_already"] = True
                await func.update_session_data(server_id, channel_id_str, channel_data)
                
                await interaction.followup.send(
                    f"Setup successful!\n**AI name:** {ai_name}\n**Character name:** {character_info['name']}\n**Character ID:** `{character_id}`\n**Channel:** {channel.mention}\n**Mode:** Webhook",
                    ephemeral=True
                )
        else:
            # Bot mode setup - only allow one bot per channel
            existing_bot = None
            for ai_name_existing, ai_data in channel_data.items():
                if ai_data.get("mode") == "bot":
                    existing_bot = ai_name_existing
                    break
            
            if existing_bot:
                await interaction.followup.send(f"Bot mode is already configured for AI '{existing_bot}' in this channel. Only one bot per channel is allowed.", ephemeral=True)
                return
            
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
            
            # Add this AI to the channel's AI configurations
            channel_data[ai_name] = session
            await func.update_session_data(server_id, channel_id_str, channel_data)
            
            greetings, reply_system = await cai.initialize_session_messages(session, server_id, channel_id_str)
            if greetings:
                try:
                    await channel.send(greetings)
                    func.log.info(f"Greeting message sent as bot for AI {ai_name} in channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Error sending greeting as bot: {e}")
            if reply_system:
                try:
                    await channel.send(reply_system)
                    func.log.info(f"System message sent as bot for AI {ai_name} in channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Error sending system message as bot: {e}")
            
            # Mark setup as complete
            channel_data[ai_name]["setup_has_already"] = True
            await func.update_session_data(server_id, channel_id_str, channel_data)
            
            await interaction.followup.send(
                f"Setup successful!\n**AI name:** {ai_name}\n**Character name:** {character_info['name']}\n**Character ID:** `{character_id}`\n**Channel:** {channel.mention}\n**Mode:** Bot",
                ephemeral=True
            )

    @app_commands.command(name="chat_id", description="Setup a chat ID for a specific AI")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="AI Channel",
        ai_name="Name of the AI to configure",
        chat_id="Chat ID (Leave empty to create a new Chat ID)"
    )
    async def chat_id(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        ai_name: str,
        chat_id: str = None
    ):
        """
        Updates the chat_id in session.json and initializes session messages for a specific AI.
        """
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)
        channel_data = func.get_session_data(server_id, channel_id_str)
        
        if channel_data is None or ai_name not in channel_data:
            await interaction.followup.send(
                f"AI '{ai_name}' not found in this channel. Please run the setup command first.",
                ephemeral=True
            )
            return
        
        session = channel_data[ai_name]
        session["setup_has_already"] = False
        session["chat_id"] = chat_id if chat_id else None
        
        # Update the specific AI in channel data
        channel_data[ai_name] = session
        await func.update_session_data(server_id, channel_id_str, channel_data)
        
        greetings, reply_system = await cai.initialize_session_messages(session, server_id, channel_id_str)
        
        # Mark setup as complete
        channel_data[ai_name]["setup_has_already"] = True
        await func.update_session_data(server_id, channel_id_str, channel_data)
        
        if session.get("mode") == "webhook":
            WB_url = session.get("webhook_url")
            if not WB_url:
                func.log.error(f"Webhook URL not found in session data for AI {ai_name} in channel {channel_id_str}.")
                await interaction.followup.send(
                    "Webhook URL not found in session data.",
                    ephemeral=True
                )
                return
            if greetings and WB_url:
                try:
                    await webhook_send(WB_url, greetings, session)
                    func.log.info("Greeting message sent via webhook for AI %s in channel %s", ai_name, channel_id_str)
                except Exception as e:
                    func.log.error("Error sending greeting via webhook for AI %s in channel %s: %s", ai_name, channel_id_str, e)
            if reply_system and WB_url:
                try:
                    await webhook_send(WB_url, reply_system, session)
                    func.log.info("System message sent via webhook for AI %s in channel %s", ai_name, channel_id_str)
                except Exception as e:
                    func.log.error("Error sending system message via webhook for AI %s in channel %s: %s", ai_name, channel_id_str, e)
        else:
            channel_obj = interaction.guild.get_channel(int(channel_id_str))
            if greetings and channel_obj:
                try:
                    await channel_obj.send(greetings)
                    func.log.info(f"Greeting message sent as bot for AI {ai_name} in channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Error sending greeting as bot: {e}")
            if reply_system and channel_obj:
                try:
                    await channel_obj.send(reply_system)
                    func.log.info(f"System message sent as bot for AI {ai_name} in channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Error sending system message as bot: {e}")
        await interaction.followup.send(
            f"Chat ID configuration successful for AI '{ai_name}'! Current chat ID: `{session['chat_id']}`",
            ephemeral=True
        )

    @app_commands.command(name="remove_ai", description="Remove a specific AI from a channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to remove AI from",
        ai_name="Name of the AI to remove"
    )
    async def remove_ai(self, interaction: discord.Interaction, channel: discord.TextChannel, ai_name: str):
        """
        Remove a specific AI (bot or webhook) from the channel.
        """
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)
        channel_data = func.get_session_data(server_id, channel_id_str)
        
        if not channel_data or ai_name not in channel_data:
            await interaction.followup.send(f"AI '{ai_name}' not found in channel {channel.mention}.", ephemeral=True)
            func.log.warning(f"Attempted to remove AI '{ai_name}' from channel {channel_id_str}, but AI was not found.")
            return
        
        session = channel_data[ai_name]
        if session.get("mode") == "webhook":
            webhook_url = session.get("webhook_url")
            if webhook_url:
                try:
                    async with aiohttp.ClientSession() as aio_session:
                        webhook_obj = discord.Webhook.from_url(webhook_url, session=aio_session)
                        await webhook_obj.delete(reason=f"AI '{ai_name}' removed from channel")
                    func.log.info(f"Deleted webhook for AI '{ai_name}' in channel {channel_id_str}")
                except Exception as e:
                    func.log.error(f"Failed to delete webhook for AI '{ai_name}': {e}")
        
        # Remove the specific AI from channel data
        del channel_data[ai_name]
        
        # If no more AIs in the channel, remove the entire channel data
        if not channel_data:
            await func.remove_session_data(server_id, channel_id_str)
        else:
            await func.update_session_data(server_id, channel_id_str, channel_data)
        
        await interaction.followup.send(f"AI '{ai_name}' successfully removed from channel {channel.mention}.", ephemeral=True)
        func.log.info(f"AI '{ai_name}' removed from channel {channel_id_str}")

    @app_commands.command(name="list_ais", description="List all AIs configured in a channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to list AIs from"
    )
    async def list_ais(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        List all AIs configured in the specified channel.
        """
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)
        channel_data = func.get_session_data(server_id, channel_id_str)
        
        if not channel_data:
            await interaction.followup.send(f"No AIs configured in channel {channel.mention}.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"AIs in {channel.mention}",
            color=discord.Color.blue()
        )
        
        for ai_name, ai_data in channel_data.items():
            character_id = ai_data.get("character_id", "Unknown")
            mode = ai_data.get("mode", "Unknown")
            chat_id = ai_data.get("chat_id", "Not set")
            setup_status = "✅ Set up" if ai_data.get("setup_has_already", False) else "❌ Not set up"
            
            embed.add_field(
                name=f"🤖 {ai_name}",
                value=f"**Character ID:** `{character_id}`\n**Mode:** {mode}\n**Chat ID:** `{chat_id}`\n**Status:** {setup_status}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

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