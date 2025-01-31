import asyncio
import logging
import platform
import discord
import AI_utils
import yaml
from discord.ext import commands

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(
    level=logging.DEBUG,
    filename="app.log",
    format="[%(filename)s] %(levelname)s : %(message)s",
    encoding="utf-8",
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Define o nível do console
console_handler.setFormatter(
    logging.Formatter("[%(filename)s] %(levelname)s : %(message)s")
)
logging.getLogger().addHandler(console_handler)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="!", intents=intents)

try:
    with open("config.yml", "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
except FileNotFoundError:
    logging.critical("The configuration file ‘config.yml’ does not exist.")

try:
    with open(data["Discord"]["messages_cache"], encoding="utf-8"):
        logging.debug(f"Archive {data["Discord"]["messages_cache"]} exists.")
except FileNotFoundError:
    with open(data["Discord"]["messages_cache"], 'x') as file:
        file.write("[]")

AI = AI_utils.discord_AI_bot()

@client.event
async def on_ready():
    await AI.sync_config(client)
    logging.info(f"Logged in as {client.user}!")


@client.event
async def on_typing(channel, user, when):
    AI.time_typing(channel, user, client)


@client.event
async def on_message(message):

    asyncio.create_task(AI.read_channel_messages(message, client))
    asyncio.ensure_future(AI.monitor_inactivity(client, message))

try:
    client.run(data["Discord"]["token"])
except Exception as e:
    logging.critical(f"{e}")
    input()
    exit()