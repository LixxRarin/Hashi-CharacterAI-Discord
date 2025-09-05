import time
import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from AI.cai import get_bot_info, get_client
from commands.ai_manager import AIManager # Import AIManager to access its autocomplete


class SlashCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_manager_cog = AIManager(bot) # Instantiate AIManager to access its methods

    @app_commands.command(name="character_info", description="Show Character.AI bot information.")
    @app_commands.describe(
        ai_name="Name of the AI to get info from (optional - shows all if not specified)"
    )
    @app_commands.autocomplete(ai_name=AIManager.ai_name_autocomplete)
    async def character_info(self, interaction: discord.Interaction, ai_name: str = None):
        """
        Fetches bot information from Character.AI and displays it in an embed.
        """
        await interaction.response.defer()  # Defer response while fetching data

        server_id = str(interaction.guild.id)
        channel_id_str = str(interaction.channel.id)
        
        if ai_name:
            # Show info for specific AI
            found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
            
            if not found_ai_data:
                await interaction.followup.send(f"AI '{ai_name}' not found in this server.")
                return
            
            found_channel_id, session = found_ai_data
            character_id = session.get("character_id")
            
            if not character_id:
                await interaction.followup.send(f"AI '{ai_name}' has no character ID configured.")
                return
            
            await self._show_character_info(interaction, character_id, ai_name)
        else:
            # Show info for all AIs in the current channel
            channel_data = func.get_session_data(server_id, channel_id_str)
            
            if not channel_data:
                await interaction.followup.send("There are no AIs configured in this channel.")
                return
            
            embeds = []
            for ai_name_in_channel, ai_data in channel_data.items():
                character_id = ai_data.get("character_id")
                if character_id:
                    embed = await self._get_character_embed(character_id, ai_name_in_channel)
                    if embed:
                        embeds.append(embed)
            
            if not embeds:
                await interaction.followup.send("No valid character information found for any AI in this channel.")
                return
            
            # Send first embed
            await interaction.followup.send(embed=embeds[0])
            
            # Send remaining embeds if any
            for embed in embeds[1:]:
                await interaction.followup.send(embed=embed)

    async def _show_character_info(self, interaction, character_id, ai_name):
        """Show character info for a specific AI"""
        try:
            # Fetch bot info
            bot_data = await get_bot_info(character_id=character_id)
        except Exception as e:
            func.log.error(f"Failed to retrieve bot info: {e}")
            await interaction.followup.send("❌ **Error:** Unable to retrieve bot information. Please try again later.")
            return

        if not bot_data:
            await interaction.followup.send("❌ **Error:** Unable to retrieve bot information. Please try again later.")
            return

        embed = await self._get_character_embed(character_id, ai_name, bot_data)
        
        if embed:
            await interaction.followup.send(embed=embed)

    async def _get_character_embed(self, character_id, ai_name, bot_data=None):
        """Get character embed for display"""
        if not bot_data:
            try:
                bot_data = await get_bot_info(character_id=character_id)
            except Exception as e:
                func.log.error(f"Failed to retrieve bot info: {e}")
                return None
        
        if not bot_data:
            return None

        # Extract relevant details
        name = bot_data.get("name", "Unknown Bot")
        avatar_url = bot_data.get("avatar_url", None)
        title = bot_data.get("title", "No title available.")
        description = bot_data.get("description", "No description provided.").replace("\n", " ")
        visibility = bot_data.get("visibility", "Unknown")
        interactions = bot_data.get("num_interactions", 0)
        author = bot_data.get("author_username", "Unknown Author")

        # Create embed
        embed = discord.Embed(
            title=f"{name} - Character Information ({ai_name})",
            description=f"**{title}**\n\n{description}",
            color=discord.Color.blue()
        )
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.add_field(name="👤 Creator:", value=author, inline=True)
        embed.add_field(name="🔄 Total Interactions:", value=f"{interactions:,}", inline=True)
        embed.add_field(name="🌎 Visibility:", value=visibility.capitalize(), inline=True)
        embed.set_footer(text="Character.AI bots are available on Discord thanks to Hashi!")
        embed.add_field(
            name="🔗 Learn More about Hashi",
            value="[GitHub Repository](https://github.com/LixxRarin/Hashi-CharacterAI-Discord)", inline=False)

        return embed

    @app_commands.command(name="ping", description="Displays latency and possible connection issues.")
    async def ping(self, interaction: discord.Interaction):
        # Measure API ping by timing the message response
        start = time.perf_counter()
        await interaction.response.send_message("Calculating ping...")
        end = time.perf_counter()
        api_ping = round((end - start) * 1000)  # API ping in milliseconds

        # Get the WebSocket (gateway) latency
        gateway_ping = round(self.bot.latency * 1000)

        # Determine connection speed status
        if gateway_ping < 100 and api_ping < 200:
            speed_status = "Your connection is very fast!"
        elif gateway_ping < 200 and api_ping < 350:
            speed_status = "Your connection is stable."
        elif gateway_ping < 300 and api_ping < 500:
            speed_status = "Your connection is somewhat slow."
        else:
            speed_status = "Your connection is very slow! Expect delays."

        # Check for potential connection issues
        warnings = []
        if gateway_ping > 400:
            warnings.append(
                "High gateway latency! The bot may be slow to respond.")
        if api_ping > 700:
            warnings.append(
                "High API latency! Discord's response times may be delayed.")
        if gateway_ping > 500 and api_ping > 800:
            warnings.append(
                "**Severe connection issues detected!** Commands may be very slow.")

        # Format warning message (if any issues exist)
        warning_message = "\n".join(
            warnings) if warnings else "No connection issues detected."

        # Build the final message
        message = (
            f"🏓 **Pong!**\n"
            f"📡 **Gateway Ping:** `{gateway_ping}ms`\n"
            f"⚡ **API Ping:** `{api_ping}ms`\n"
            f"🌐 **Connection Speed:** {speed_status}\n"
            f"🚨 **Warnings:** {warning_message}"
        )

        # Edit the initial response with the final message
        await interaction.edit_original_response(content=message)

    @app_commands.command(name="config", description="Update AI configuration settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to configure",
        use_cai_avatar="Use Character.AI avatar for webhooks",
        use_cai_display_name="Use Character.AI display name for webhooks",
        new_chat_on_reset="Create a new chat session upon reset",
        system_message="System message for Character.AI (Write 'none' for empty)",
        send_the_greeting_message="Send the character's greeting message in the channel",
        send_the_system_message_reply="Send a reply to the system message in the channel",
        send_message_line_by_line="Send messages one line at a time",
        delay_for_generation="Delay (in seconds) before generating a response",
        cache_count_threshold="Number of messages in cache to trigger a response (default: 5)",
        remove_ai_text_from="Comma-separated regex patterns to remove from AI messages (Write 'none' for empty)",
        remove_user_text_from="Comma-separated regex patterns to remove from user messages (Write 'none' for empty)",
        remove_user_emoji="Remove emojis from user messages",
        remove_ai_emoji="Remove emojis from AI messages",
        user_reply_format_syntax="Template for formatting user replies",
        user_format_syntax="Template for formatting user messages"
    )
    @app_commands.autocomplete(ai_name=AIManager.ai_name_autocomplete)
    async def config(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        use_cai_avatar: bool = None,
        use_cai_display_name: bool = None,
        new_chat_on_reset: bool = None,
        system_message: str = None,
        send_the_greeting_message: bool = None,
        send_the_system_message_reply: bool = None,
        send_message_line_by_line: bool = None,
        delay_for_generation: int = None,
        cache_count_threshold: int = None,
        remove_ai_text_from: str = None,
        remove_user_text_from: str = None,
        remove_user_emoji: bool = None,
        remove_ai_emoji: bool = None,
        user_reply_format_syntax: str = None,
        user_format_syntax: str = None
    ):
        # Retrieve server and channel IDs as strings
        server_id = str(interaction.guild.id)
        channel_id = str(interaction.channel.id)
        
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"AI '{ai_name}' not found in this server.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        
        # If the AI is found in a different channel, we need to get the channel_data for that channel
        channel_data = func.get_session_data(server_id, found_channel_id)

        # Shortcut to the configuration dictionary
        config = session.setdefault("config", {})

        # ------------------ Discord Settings ------------------
        # discord_config = config.setdefault("Discord", {})
        if use_cai_avatar is not None:
            config["use_cai_avatar"] = use_cai_avatar
        if use_cai_display_name is not None:
            config["use_cai_display_name"] = use_cai_display_name

        # ---------------- Character_AI Settings ---------------
        # character_ai = config.setdefault("Character_AI", {})
        if new_chat_on_reset is not None:
            config["new_chat_on_reset"] = new_chat_on_reset
        if system_message is not None:
            if system_message.lower() == "none":
                config["system_message"] = None
            else:
                config["system_message"] = system_message

        # ------------------ Options Settings --------------------
        # options = config.setdefault("Options", {})
        if send_the_greeting_message is not None:
            config["send_the_greeting_message"] = send_the_greeting_message
        if send_the_system_message_reply is not None:
            config["send_the_system_message_reply"] = send_the_system_message_reply
        if send_message_line_by_line is not None:
            config["send_message_line_by_line"] = send_message_line_by_line
        if delay_for_generation is not None:
            config["delay_for_generation"] = delay_for_generation
        if cache_count_threshold is not None:
            config["cache_count_threshold"] = cache_count_threshold

        # ---------------- MessageFormatting Settings ------------
        # msg_format = config.setdefault("MessageFormatting", {})
        if remove_ai_text_from is not None:
            # Convert comma-separated string into a list of regex patterns
            if remove_ai_text_from.lower() == "none":
                config["remove_ai_text_from"] = []
            else:
                config["remove_ai_text_from"] = [pattern.strip()
                                                 for pattern in remove_ai_text_from.split(",")]
        if remove_user_text_from is not None:
            if remove_user_text_from.lower() == "none":
                config["remove_user_text_from"] = []
            else:
                config["remove_user_text_from"] = [pattern.strip()
                                                   for pattern in remove_user_text_from.split(",")]
        if remove_user_emoji is not None:
            config["remove_user_emoji"] = remove_user_emoji
        if remove_ai_emoji is not None:
            config["remove_ai_emoji"] = remove_ai_emoji
        if user_reply_format_syntax is not None:
            if user_reply_format_syntax.lower() == "none":
                config["user_reply_format_syntax"] = "{message}"
            else:
                config["user_reply_format_syntax"] = user_reply_format_syntax
        if user_format_syntax is not None:
            if user_format_syntax.lower() == "none":
                config["user_format_syntax"] = "{message}"
            else:
                config["user_format_syntax"] = user_format_syntax
        # Update the specific AI in channel data
        channel_data[ai_name] = session
        
        # Save the updated configuration back to the session
        await func.update_session_data(server_id, channel_id, channel_data)
        await interaction.response.send_message(f"Configuration updated successfully for AI '{ai_name}'!", ephemeral=True)

    @app_commands.command(name="copy_config", description="Copies all settings from one AI to another!")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        from_ai_name="Name of the source AI",
        to_ai_name="Name of the target AI"
    )
    @app_commands.autocomplete(from_ai_name=AIManager.ai_name_autocomplete)
    @app_commands.autocomplete(to_ai_name=AIManager.ai_name_autocomplete)
    async def copy_config(self, interaction: discord.Interaction, from_ai_name: str, to_ai_name: str):
        server_id = str(interaction.guild.id)
        
        from_ai_data = func.get_ai_session_data_from_all_channels(server_id, from_ai_name)
        to_ai_data = func.get_ai_session_data_from_all_channels(server_id, to_ai_name)

        if not from_ai_data:
            await interaction.response.send_message(f"⚠️ AI '{from_ai_name}' not found in this server.", ephemeral=True)
            return
        if not to_ai_data:
            await interaction.response.send_message(f"⚠️ AI '{to_ai_name}' not found in this server.", ephemeral=True)
            return

        from_channel_id, from_session = from_ai_data
        to_channel_id, to_session = to_ai_data

        # Get the full channel data for both source and target channels
        from_channel_data = func.get_session_data(server_id, from_channel_id)
        to_channel_data = func.get_session_data(server_id, to_channel_id)

        # Copy config from source AI to target AI
        to_channel_data[to_ai_name]["config"] = from_channel_data[from_ai_name]["config"].copy()
        
        # Update session data for the target channel
        await func.update_session_data(server_id, to_channel_id, to_channel_data)

        await func.update_session_data(server_id, to_channel_id, to_channel_data)

        await interaction.response.send_message(f"Settings successfully copied from AI '{from_ai_name}' to AI '{to_ai_name}' in this channel!", ephemeral=True)

    @app_commands.command(name="show_config", description="Display AI configuration settings for a specific AI.")
    @app_commands.describe(
        ai_name="Name of the AI to show config for"
    )
    @app_commands.autocomplete(ai_name=AIManager.ai_name_autocomplete)
    async def show_config(self, interaction: discord.Interaction, ai_name: str):
        """
        Retrieves and displays configuration settings for a specific AI.
        """
        # Load session data
        server_id = str(interaction.guild.id)
        
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"❌ AI '{ai_name}' not found in this server.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        
        try:
            # Get AI-specific configuration
            ai_config = session["config"]
        except KeyError:
            func.log.warning(f"No configuration found for AI '{ai_name}' in channel: {found_channel_id}")
            await interaction.response.send_message(f"❌ No configuration found for AI '{ai_name}' in this server.", ephemeral=True)
            return

        # Build embed to display config
        embed = discord.Embed(
            title=f"Configuration for AI '{ai_name}' in {interaction.channel.mention}",
            color=discord.Color.light_gray()
        )

        for key, value in ai_config.items():
            embed.add_field(name=key, value=str(value), inline=False)

        # Send the configuration summary
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="mute", description="Mute a user so the AI does not capture their messages")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to mute user for",
        user="User to mute"
    )
    @app_commands.autocomplete(ai_name=AIManager.ai_name_autocomplete)
    async def mute(self, interaction: discord.Interaction, ai_name: str, user: discord.Member):
        server_id = str(interaction.guild.id)
        
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"AI '{ai_name}' not found in this server.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        
        # Get the full channel data for the found channel
        channel_data = func.get_session_data(server_id, found_channel_id)

        if user.id not in session["muted_users"]:
            session["muted_users"].append(user.id)
            await interaction.response.send_message(f"{user.mention} has been muted for AI '{ai_name}'.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{user.mention} is already muted for AI '{ai_name}'.", ephemeral=True)

        # Update the specific AI in channel data
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)

    @app_commands.command(name="unmute", description="Unmute a user so the AI captures their messages")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to unmute user for",
        user="User to unmute"
    )
    @app_commands.autocomplete(ai_name=AIManager.ai_name_autocomplete)
    async def unmute(self, interaction: discord.Interaction, ai_name: str, user: discord.Member):
        server_id = str(interaction.guild.id)
        
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"AI '{ai_name}' not found in this server.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        
        # Get the full channel data for the found channel
        channel_data = func.get_session_data(server_id, found_channel_id)

        if user.id in session["muted_users"]:
            session["muted_users"].remove(user.id)
            await interaction.response.send_message(f"{user.mention} has been unmuted for AI '{ai_name}'.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{user.mention} is not muted for AI '{ai_name}'.", ephemeral=True)

        # Update the specific AI in channel data
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)

    @app_commands.command(name="list_muted", description="List all muted users for a specific AI")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to list muted users for"
    )
    @app_commands.autocomplete(ai_name=AIManager.ai_name_autocomplete)
    async def list_muted(self, interaction: discord.Interaction, ai_name: str):
        server_id = str(interaction.guild.id)
        
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(f"AI '{ai_name}' not found in this server.", ephemeral=True)
            return
        
        found_channel_id, session = found_ai_data
        
        # Get the full channel data for the found channel
        channel_data = func.get_session_data(server_id, found_channel_id)
        muted_users = session.get("muted_users", [])

        if not muted_users:
            # If there are no muted users, inform the admin
            await interaction.response.send_message(f"No users are currently muted for AI '{ai_name}'.", ephemeral=True)
            return

        # Get user mentions for all muted user IDs
        mentions = [f"<@{user_id}>" for user_id in muted_users]
        muted_list = "\n".join(mentions)

        # Send the list of muted users
        await interaction.response.send_message(f"Muted users for AI '{ai_name}' in {interaction.channel.mention}:\n{muted_list}", ephemeral=True)

    @app_commands.command(name="token", description="Use an alternative token for a specific AI. The host can see your token, so be careful!")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to set token for",
        token="Alternative token (use 'none' to clear)"
    )
    @app_commands.autocomplete(ai_name=AIManager.ai_name_autocomplete)
    async def token(self, interaction: discord.Interaction, ai_name: str, token: str):

        if func.config_yaml["Options"]["enable_alternative_cai_token"]:
            server_id = str(interaction.guild.id)
            
            found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
            
            if not found_ai_data:
                await interaction.response.send_message(f"AI '{ai_name}' not found in this server.", ephemeral=True)
                return
            
            found_channel_id, session = found_ai_data
            
            # Get the full channel data for the found channel
            channel_data = func.get_session_data(server_id, found_channel_id)

            try:
                client = await get_client(token)
            except Exception as e:
                await interaction.response.send_message(f"An error occurred when capturing the token. Error: {e}\nCheck that the token is correct.", ephemeral=True)
                return

            # Set the alternative token or clear it if the user inputs "none"
            session["alt_token"] = None if token.lower() == "none" else token

            # Update the specific AI in channel data
            channel_data[ai_name] = session
            
            # Update session data
            await func.update_session_data(server_id, found_channel_id, channel_data)

            # Confirmation message
            if session["alt_token"] is None:
                await interaction.response.send_message(f"The alternative token has been cleared for AI '{ai_name}'.", ephemeral=True)
            else:
                await interaction.response.send_message(f"The alternative token has been set successfully for AI '{ai_name}'. Remember to change the chat ID with '/chat_id'.", ephemeral=True)
        else:
            await interaction.response.send_message("This bot does not allow the use of alternative tokens.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(SlashCommands(bot))
