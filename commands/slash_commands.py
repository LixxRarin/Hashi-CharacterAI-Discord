import time

import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from AI.cai import get_bot_info, get_client


class SlashCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="character_info", description="Show Character.AI bot information.")
    async def character_info(self, interaction: discord.Integration, channel: discord.TextChannel):
        """
        Fetches bot information from Character.AI and displays it in an embed.
        """

        session_data = func.read_json("session.json")
        character_id = None

        try:
            character_id = session_data[str(
                channel.guild.id)]["channels"][str(channel.id)]["character_id"]
        except:
            func.log.warning(
                f"There is no character available for this channel: {channel.id}")

        await interaction.response.defer()  # Defer response while fetching data

        if character_id is None:
            await interaction.followup.send("There is no character available for this channel. (Try create)")
        else:
            try:
                # Fetch bot info
                bot_data = await get_bot_info(character_id=character_id)
            except Exception as e:
                func.log.error(f"Failed to retrieve bot info: {e}")
                await interaction.followup.send("❌ **Error:** Unable to retrieve bot information. Please try again later.")
                return

            # Extract relevant details
            name = bot_data.get("name", "Unknown Bot")
            # Fix: Use None instead of discord.Embed.Empty
            avatar_url = bot_data.get("avatar_url", None)
            title = bot_data.get("title", "No title available.")
            description = bot_data.get(
                "description", "No description provided.").replace("\n", " ")
            visibility = bot_data.get("visibility", "Unknown")
            interactions = bot_data.get("num_interactions", 0)
            author = bot_data.get("author_username", "Unknown Author")

            # Create embed
            embed = discord.Embed(
                title=f"{name} - Character Information",
                description=f"**{title}**\n\n{description}",
                color=discord.Color.blue()
            )
            if avatar_url:  # Only set thumbnail if a valid URL exists
                embed.set_thumbnail(url=avatar_url)

            embed.add_field(name="👤 Creator:", value=author, inline=True)
            embed.add_field(name="🔄 Total Interactions:",
                            value=f"{interactions:,}", inline=True)
            embed.add_field(name="🌎 Visibility:",
                            value=visibility.capitalize(), inline=True)
            embed.set_footer(
                text="Character.AI bots are available on Discord thanks to Hashi!")
            embed.add_field(
                name="🔗 Learn More about Hashi",
                value="[GitHub Repository](https://github.com/LixxRarin/Hashi-Character_AI-Discord)", inline=False)

            # Send the embed
            await interaction.followup.send(embed=embed)

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

    @app_commands.command(name="config", description="Update bot configuration settings")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        use_cai_avatar="Use Character.AI avatar for webhooks",
        use_cai_display_name="Use Character.AI display name for webhooks",
        new_chat_on_reset="Create a new chat session upon reset",
        system_message="System message for Character.AI",
        send_the_greeting_message="Send the character's greeting message in the channel",
        send_the_system_message_reply="Send a reply to the system message in the channel",
        send_message_line_by_line="Send messages one line at a time",
        delay_for_generation="Delay (in seconds) before generating a response",
        remove_ai_text_from="Comma-separated regex patterns to remove from AI messages",
        remove_user_text_from="Comma-separated regex patterns to remove from user messages",
        remove_user_emoji="Remove emojis from user messages",
        remove_ai_emoji="Remove emojis from AI messages",
        user_reply_format_syntax="Template for formatting user replies",
        user_format_syntax="Template for formatting user messages"
    )
    async def config(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        use_cai_avatar: bool = None,
        use_cai_display_name: bool = None,
        new_chat_on_reset: bool = None,
        system_message: str = None,
        send_the_greeting_message: bool = None,
        send_the_system_message_reply: bool = None,
        send_message_line_by_line: bool = None,
        delay_for_generation: int = None,
        remove_ai_text_from: str = None,
        remove_user_text_from: str = None,
        remove_user_emoji: bool = None,
        remove_ai_emoji: bool = None,
        user_reply_format_syntax: str = None,
        user_format_syntax: str = None
    ):
        # Retrieve server and channel IDs as strings
        server_id = str(interaction.guild.id)
        channel_id = str(channel.id)

        # Get the current session configuration for this server and channel
        session = func.get_session_data(server_id, channel_id)

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
            config["remove_user_emoji"][
                "user"] = remove_user_emoji
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
        # Save the updated configuration back to the session
        await func.update_session_data(server_id, channel_id, session)
        await interaction.response.send_message("Configuration updated successfully!", ephemeral=True)

    @app_commands.command(name="copy_config", description="Copies all settings from one AI to another!")
    @app_commands.default_permissions(administrator=True)
    async def copy_config(self, interaction: discord.Integration, from_channel: discord.TextChannel, to_channel: discord.TextChannel):

        from_channel_session = func.get_session_data(
            str(from_channel.guild.id), str(from_channel.id))
        to_channel_session = func.get_session_data(
            str(to_channel.guild.id), str(to_channel.id))

        if from_channel_session is None:
            await interaction.response.send_message(f"⚠️ No configured AI found in {from_channel.mention}, try `/setup`.", ephemeral=True)
            return
        if to_channel_session is None:
            await interaction.response.send_message(f"⚠️ No configured AI found in {to_channel.mention}, try `/setup`.", ephemeral=True)
            return

        to_channel_session["config"] = from_channel_session["config"]

        func.update_session_data(str(to_channel.guild.id), str(
            to_channel.id), to_channel_session)

        await interaction.response.send_message(f"Settings successfully copied from {from_channel} to {to_channel}!", ephemeral=True)

    @app_commands.command(name="show_config", description="Display all AI configuration settings for a specific channel.")
    async def show_config(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        Retrieves and displays all configuration settings from session.json for a given channel.
        """
        # Load session data
        session = func.get_session_data(str(channel.guild.id), str(channel.id))

        try:
            # Get channel-specific configuration
            channel_config = session["config"]
        except KeyError:
            func.log.warning(
                f"No configuration found for channel: {channel.id}")
            await interaction.response.send_message("❌ No configuration found for this channel.", ephemeral=True)
            return

        # Build embed to display config
        embed = discord.Embed(
            title=f"Configuration for the channel: {channel.mention}",
            color=discord.Color.light_gray()
        )

        for key, value in channel_config.items():
            embed.add_field(name=key, value=str(value), inline=False)

        # Send the configuration summary
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="mute", description="Mute a user so the AI does not capture their messages")
    @app_commands.default_permissions(administrator=True)
    async def mute(self, interaction: discord.Interaction, channel: discord.TextChannel, user: discord.Member):

        session = func.get_session_data(str(channel.guild.id), str(channel.id))

        if user.id not in session["muted_users"]:
            session["muted_users"].append(user.id)
            await interaction.response.send_message(f"{user.mention} has been muted.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{user.mention} is already muted.", ephemeral=True)

        await func.update_session_data(str(channel.guild.id), str(channel.id), session)

    @app_commands.command(name="unmute", description="Unmute a user so the AI captures their messages")
    @app_commands.default_permissions(administrator=True)
    async def unmute(self, interaction: discord.Interaction, channel: discord.TextChannel, user: discord.Member):

        session = func.get_session_data(str(channel.guild.id), str(channel.id))

        if user.id in session["muted_users"]:
            session["muted_users"].remove(user.id)
            await interaction.response.send_message(f"{user.mention} has been unmuted.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{user.mention} is not muted.", ephemeral=True)

        await func.update_session_data(str(channel.guild.id), str(channel.id), session)

    @app_commands.command(name="list_muted", description="List all muted users in a channel")
    @app_commands.default_permissions(administrator=True)
    async def list_muted(self, interaction: discord.Interaction, channel: discord.TextChannel):

        # Retrieve session data for the given guild and channel
        session = func.get_session_data(str(channel.guild.id), str(channel.id))
        muted_users = session.get("muted_users", [])

        if not muted_users:
            # If there are no muted users, inform the admin
            await interaction.response.send_message("No users are currently muted.", ephemeral=True)
            return

        # Get user mentions for all muted user IDs
        mentions = [f"<@{user_id}>" for user_id in muted_users]
        muted_list = "\n".join(mentions)

        # Send the list of muted users
        await interaction.response.send_message(f"Muted users in {channel.mention}:\n{muted_list}", ephemeral=True)

    @app_commands.command(name="token", description="Use an alternative token for a channel. The host can see your token, so be careful.!")
    @app_commands.default_permissions(administrator=True)
    async def token(self, interaction: discord.Interaction, channel: discord.TextChannel, token: str):

        if func.config_yaml["Options"]["enable_alternative_cai_token"]:

            session = func.get_session_data(
                str(channel.guild.id), str(channel.id))

            try:
                client = await get_client(token)
            except Exception as e:
                await interaction.response.send_message(f"An error occurred when capturing the token. Error: {e}\nCheck that the token is correct.", ephemeral=True)
                return

            # Set the alternative token or clear it if the user inputs "none"
            session["alt_token"] = None if token.lower() == "none" else token

            # Update session data
            await func.update_session_data(str(channel.guild.id), str(channel.id), session)

            # Confirmation message
            if session["alt_token"] is None:
                await interaction.response.send_message("The alternative token has been cleared.", ephemeral=True)
            else:
                await interaction.response.send_message("The alternative token has been set successfully. Remember to change the chat ID with '/chat_id'.", ephemeral=True)
        else:
            await interaction.response.send_message("This bot does not allow the use of alternative tokens.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(SlashCommands(bot))
