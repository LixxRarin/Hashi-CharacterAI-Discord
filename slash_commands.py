import discord
from discord.ext import commands
from discord import app_commands
import time
from cai import get_bot_info
import logging

logger = logging.getLogger(__name__)

class SlashCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="character_info", description="Show Character.AI bot information.")
    async def character_info(self, interaction: discord.Integration):
        """
        Fetches bot information from Character.AI and displays it in an embed.
        """
        await interaction.response.defer()  # Defer response while fetching data

        try:
            bot_data = await get_bot_info()  # Fetch bot info
        except Exception as e:
            logging.error(f"Failed to retrieve bot info: {e}")
            await interaction.followup.send("❌ **Error:** Unable to retrieve bot information. Please try again later.")
            return

        # Extract relevant details
        name = bot_data.get("name", "Unknown Bot")
        avatar_url = bot_data.get("avatar_url", None)  # Fix: Use None instead of discord.Embed.Empty
        title = bot_data.get("title", "No title available.")
        description = bot_data.get("description", "No description provided.").replace("\n", " ")
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
        embed.add_field(name="🔄 Total Interactions:", value=f"{interactions:,}", inline=True)
        embed.add_field(name="🌎 Visibility:", value=visibility.capitalize(), inline=True)
        embed.set_footer(text="Character.AI bots are available on Discord thanks to Bridge. :3")  
        embed.add_field(name="🔗 Learn More about Bridge", value="[GitHub Repository](https://github.com/LixxRarin/CharacterAI-Discord-Bridge)", inline=False)

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
            warnings.append("High gateway latency! The bot may be slow to respond.")
        if api_ping > 700:
            warnings.append("High API latency! Discord's response times may be delayed.")
        if gateway_ping > 500 and api_ping > 800:
            warnings.append("**Severe connection issues detected!** Commands may be very slow.")

        # Format warning message (if any issues exist)
        warning_message = "\n".join(warnings) if warnings else "No connection issues detected."

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

async def setup(bot):
    await bot.add_cog(SlashCommands(bot))