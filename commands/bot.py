import time
import asyncio
from typing import Dict, Any, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
import AI.cai as cai


class BotMode(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
            # Update bot's nickname in the server
            me = guild.me
            await me.edit(nick=character_info["name"])
            # Optionally update the bot's global avatar (requires permission)
            if avatar_bytes:
                try:
                    await self.bot.user.edit(avatar=avatar_bytes)
                except Exception:
                    pass  # Ignore if lacking permission
            func.log.info(f"Bot profile updated in guild {guild.id}")
        except Exception as e:
            func.log.error(f"Failed to update bot profile: {e}")

    @app_commands.command(name="setup_bot", description="Setup the AI to respond as the bot (not webhook) in a channel.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to use the AI", character_id="Character ID")
    async def setup_bot(self, interaction: discord.Interaction, channel: discord.TextChannel, character_id: str):
        """
        Configure the channel to use BOT mode (AI responds as the bot itself).
        """
        await interaction.response.defer(ephemeral=True)
        character_info = await cai.get_bot_info(character_id=character_id)
        if character_info is None:
            await interaction.followup.send("Invalid character_id...", ephemeral=True)
            return

        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)

        # Update bot profile in the server
        await self._update_bot_profile(interaction.guild, character_info)

        # Update session.json for bot mode
        # Update or create session data without overwriting old values
        session = func.get_session_data(server_id, channel_id_str) or {}

        session.update({
            "channel_name": channel.name,
            "character_id": character_id,
            "mode": "bot",
            "setup_has_already": False,
            "last_message_time": time.time(),
            "awaiting_response": False,
            "alt_token": session.get("alt_token"),
            "muted_users": session.get("muted_users", []),
            "config": session.get("config", {
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
            })
        })

        await func.update_session_data(server_id, channel_id_str, session)

        # Initialize session messages
        greetings, reply_system = await cai.initialize_session_messages(session, server_id, channel_id_str)
        session = func.get_session_data(server_id, channel_id_str)
        if session:
            session["setup_has_already"] = True
            await func.update_session_data(server_id, channel_id_str, session)

        # Send greeting and system messages as the bot
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

    @app_commands.command(name="remove_bot_mode", description="Remove the AI bot mode from a channel.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Channel to remove bot mode from")
    async def remove_bot_mode(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        Remove bot mode from the channel (the bot stops responding as itself).
        """
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)

        session = func.get_session_data(server_id, channel_id_str)
        if not session or session.get("mode") != "bot":
            await interaction.followup.send(f"No bot mode found in channel {channel.mention}.", ephemeral=True)
            func.log.warning(f"Attempted to remove bot mode from channel {channel_id_str}, but no bot mode was set.")
            return

        await func.remove_session_data(server_id, channel_id_str)
        await interaction.followup.send(f"Bot mode successfully removed from channel {channel.mention}.", ephemeral=True)
        func.log.info(f"Bot mode removed from channel {channel_id_str}")

    @app_commands.command(name="chat_id_bot", description="Setup a chat ID for the AI (bot mode)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="AI Channel",
        chat_id="Chat ID (Leave empty to create a new Chat ID)"
    )
    async def chat_id_bot(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        chat_id: str = None
    ):
        """
        Update the chat_id in bot mode.
        """
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        channel_id_str = str(channel.id)

        session = func.get_session_data(server_id, channel_id_str)
        if session is None or session.get("mode") != "bot":
            await interaction.followup.send(
                "Session data not found or not in bot mode. Please run the setup_bot command first.",
                ephemeral=True
            )
            func.log.warning(f"Attempted to set chat_id in channel {channel_id_str}, but no bot mode was set.")
            return

        session["setup_has_already"] = False
        session["chat_id"] = chat_id if chat_id else None
        await func.update_session_data(server_id, channel_id_str, session)

        greetings, reply_system = await cai.initialize_session_messages(session, server_id, channel_id_str)
        session = func.get_session_data(server_id, channel_id_str)
        if session:
            session["setup_has_already"] = True
            await func.update_session_data(server_id, channel_id_str, session)

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


async def setup(bot):
    await bot.add_cog(BotMode(bot))

    # Start the response queue processor (required for bot mode to work)
    import AI.cai as cai
    asyncio.create_task(cai.process_response_queue())
