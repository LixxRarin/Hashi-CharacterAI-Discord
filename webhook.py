import time
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

import utils
import cai

session_data = utils.read_json("session.json")


class WebHook(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Configura uma IA para o servidor.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="Canal para a IA monitorar", character_id="ID do personagem")
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel, character_id: str):

        character_info = await cai.get_bot_info(character_id=character_id)
        if character_info is not None:
            # Atualizar/Adicionar configuração do servidor
            server_id = str(interaction.guild.id)
            session_data[server_id] = {
                "server_name": interaction.guild.name,
            }
            session_data[server_id][channel.id] = {
                "channel_name": channel.name,
                "character_id": character_id,
                "chat_id": None,
                "setup_has_already": False
            }

            # Salvar no arquivo JSON
            utils.write_json("session.json", session_data)

            await interaction.response.send_message(
                f"Configurado com sucesso!\nCanal: {channel.mention}, Character ID: `{character_id}`.\nAI name: {character_info["name"]}",
                ephemeral=True
            )

        else:
            await interaction.response.send_message(f"Seu character_id é invalido...", ephemeral=True)


async def setup(bot):
    await bot.add_cog(WebHook(bot))
