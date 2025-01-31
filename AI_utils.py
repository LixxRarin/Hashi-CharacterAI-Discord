import asyncio
import utils
import yaml
import time
import json
import cai 
import aiohttp
import logging

logging.basicConfig(level=logging.DEBUG, filename="app.log", format='[%(filename)s] %(levelname)s : %(message)s', encoding="utf-8")
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Define o nível do console
console_handler.setFormatter(logging.Formatter('[%(filename)s] %(levelname)s : %(message)s'))

with open("config.yml", "r", encoding="utf-8") as file:
    data = yaml.safe_load(file)

class discord_AI_bot:
    def __init__(self):
        self.last_message_time = time.time()
        self.awaiting_response = False
        self.response_lock = asyncio.Lock()

    async def sync_config(self, client):
        info = await cai.get_bot_info()
        
        if data["Discord"]["use_cai_display_name"]:
            await client.user.edit(username=info["name"])

        if data["Discord"]["use_cai_avatar"]:
            async with aiohttp.ClientSession() as session:
                async with session.get(info["avatar_url"]) as response:
                    if response.status == 200:
                        imagem_bytes = await response.read()

                        await client.user.edit(avatar=imagem_bytes)
                        logging.info("Profile picture updated successfully.")
                    else:
                        logging.error(f"Failed to update profile picture. Status code: {response.status}")
    
    def time_typing(self, channel, user, client):
        if channel.id in data["Discord"]["channel_bot_chat"] and not user == client.user:
            self.last_message_time = time.time()
            logging.info(f"User {user} is typing on channel {channel}. The waiting time has been updated.")
            #await asyncio.sleep(3)

    async def read_channel_messages(self, message, client):
        if (message.channel.id in data["Discord"]["channel_bot_chat"] and message.author.id != client.user.id) and not message.content.startswith(("#", "//")):
            logging.info(f"Reading messages from the channel: {message.channel}")
            
            if message.reference is not None:

                channel = message.channel
                ref_message = await channel.fetch_message(message.reference.message_id)
                
                utils.capture_message(data["Discord"]["messages_cache"], 
                                      {"username" : message.author, "name": message.author.global_name, "message": message.content},
                                      reply_message={"username" : ref_message.author, "name": ref_message.author.global_name, "message": ref_message.content})
            else:
                
                utils.capture_message(data["Discord"]["messages_cache"], 
                                      {"username" : message.author, "name": message.author.global_name, "message": message.content})

            self.last_message_time = time.time()

    async def AI_send_message(self, client):
        self.awaiting_response = True
        
        response_channel_id = data["Discord"]["channel_bot_chat"][0]
        response_channel = client.get_channel(response_channel_id)
        
        async with self.response_lock:
            if utils.test_internet():
                async with response_channel.typing():
                    response = ""
                    try:
                        dados = utils.read_json(data["Discord"]["messages_cache"])

                        response = await cai.cai_response(dados)

                        # Pegue o canal de resposta do config.yml
                        
                        if response_channel is not None:
                                if data["Options"]["send_message_line_by_line"]:
                                    for line in response.split("\n"):  # Divide a resposta por linha
                                        if line.strip():  # Evita enviar mensagens vazias
                                            await response_channel.send(line)
                                else:
                                    await response_channel.send(response)
                        else:
                            logging.critical(f"Channel with ID {response_channel_id} not found.")

                    except Exception as e:
                        logging.error(f"An error occurred: {e}")
                    finally:
                        self.awaiting_response = False
                        self.last_message_time = time.time()
                        remove_messages = [x for x in utils.read_json(data["Discord"]["messages_cache"]) if x not in dados]
                        utils.write_json(data["Discord"]["messages_cache"], remove_messages)
            else:
                logging.warning("No internet access!")


    async def monitor_inactivity(self, client,message):
        while True:
            await asyncio.sleep(3)
            if not self.awaiting_response:

                quantidade_dicionarios = 0
                with open("messages_cache.json", 'r', encoding="utf-8") as file:
                    dados = json.load(file)

                quantidade_dicionarios = len(dados)

                if (time.time() - self.last_message_time >= 7 or quantidade_dicionarios >= 5) and quantidade_dicionarios >= 1 and not self.awaiting_response:
                    await self.AI_send_message(client)
