import asyncio
import utils
import yaml
import time
import json
import cai
import aiohttp
import logging

# Configure logging: both file and console with clear formatting.
logging.basicConfig(
    level=logging.DEBUG,
    filename="app.log",
    format='[%(filename)s] %(levelname)s : %(message)s',
    encoding="utf-8"
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Set console log level
console_handler.setFormatter(logging.Formatter('[%(filename)s] %(levelname)s : %(message)s'))
#logging.getLogger().addHandler(console_handler)

# Load configuration from the YAML file.
try:
    with open("config.yml", "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    logging.info("Configuration file 'config.yml' loaded successfully.")
except Exception as e:
    logging.critical("Failed to load configuration file 'config.yml': %s", e)
    data = {}  # Fallback to an empty dict (or consider exiting)

class discord_AI_bot:
    def __init__(self):
        # Initialize the bot's tracking variables.
        self.last_message_time = time.time()
        self.awaiting_response = False
        self.response_lock = asyncio.Lock()

    async def sync_config(self, client):
        """
        Synchronize the bot's profile (username and avatar) with the AI info from cai.
        """
        try:
            info = await cai.get_bot_info()
        except Exception as e:
            logging.error("Failed to get bot info from cai: %s", e)
            return

        # Update username if the configuration allows it.
        if data.get("Discord", {}).get("use_cai_display_name", False):
            try:
                await client.user.edit(username=info["name"])
                logging.info("Username updated to '%s'.", info["name"])
            except Exception as e:
                logging.error("Failed to update username: %s", e)

        # Update avatar if the configuration allows it.
        if data.get("Discord", {}).get("use_cai_avatar", False):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(info["avatar_url"]) as response:
                        if response.status == 200:
                            image_bytes = await response.read()
                            await client.user.edit(avatar=image_bytes)
                            logging.info("Profile picture updated successfully.")
                        else:
                            logging.error("Failed to update profile picture. HTTP status code: %s", response.status)
            except Exception as e:
                logging.error("Error while updating profile picture: %s", e)

    def time_typing(self, channel, user, client):
        """
        Update the last_message_time if a user (other than the bot) is typing in the specified channels.
        """
        try:
            if channel.id in data.get("Discord", {}).get("channel_bot_chat", []) and user != client.user:
                self.last_message_time = time.time()
                logging.info("User %s is typing in channel %s; last_message_time updated.", user, channel)
        except Exception as e:
            logging.error("Error in time_typing: %s", e)

    async def read_channel_messages(self, message, client):
        """
        Process a message from a channel specified in the configuration.
        Captures the message and (if applicable) the referenced reply message.
        """
        try:
            # Check if message is in a monitored channel and not from the bot.
            if (message.channel.id in data.get("Discord", {}).get("channel_bot_chat", [])) and \
               (message.author.id != client.user.id) and \
               (not message.content.startswith(("#", "//"))):
                logging.info("Reading message from channel: %s", message.channel)

                if message.reference is not None:
                    try:
                        channel = message.channel
                        ref_message = await channel.fetch_message(message.reference.message_id)
                        # Capture message with a reply.
                        utils.capture_message(
                            data["Discord"]["messages_cache"],
                            {
                                "username": message.author,
                                "name": message.author.global_name,
                                "message": message.content
                            },
                            reply_message={
                                "username": ref_message.author,
                                "name": ref_message.author.global_name,
                                "message": ref_message.content
                            }
                        )
                    except Exception as e:
                        logging.error("Error fetching reference message: %s", e)
                else:
                    # Capture message without a reply.
                    utils.capture_message(
                        data["Discord"]["messages_cache"],
                        {
                            "username": message.author,
                            "name": message.author.global_name,
                            "message": message.content
                        }
                    )
                self.last_message_time = time.time()
        except Exception as e:
            logging.error("Error in read_channel_messages: %s", e)

    async def AI_send_message(self, client):
        """
        Sends a message generated by the AI.
        Reads cached messages, calls the AI response function, and sends the response line-by-line (if configured).
        """
        self.awaiting_response = True
        response_channel_id = data.get("Discord", {}).get("channel_bot_chat", [None])[0]
        response_channel = client.get_channel(response_channel_id)
        
        async with self.response_lock:
            if utils.test_internet():
                try:
                    async with response_channel.typing():
                        # Read cached messages.
                        cached_data = utils.read_json(data["Discord"]["messages_cache"])
                        if not cached_data:
                            logging.info("No cached messages found.")
                            return

                        # Get AI response based on cached data.
                        response = await cai.cai_response(cached_data)
                        logging.debug("AI response received: %s", response)

                        # Send the response in the configured channel.
                        if response_channel is not None:
                            if data.get("Options", {}).get("send_message_line_by_line", False):
                                for line in response.split("\n"):
                                    if line.strip():
                                        await response_channel.send(line)
                                        logging.debug("Sent line: %s", line)
                            else:
                                await response_channel.send(response)
                                logging.debug("Sent full response.")
                        else:
                            logging.critical("Response channel with ID %s not found.", response_channel_id)
                except Exception as e:
                    logging.error("An error occurred while sending AI message: %s", e)
                finally:
                    # Reset state and clean up cache.
                    self.awaiting_response = False
                    self.last_message_time = time.time()
                    try:
                        # Remove messages that have been processed.
                        current_cache = utils.read_json(data["Discord"]["messages_cache"])
                        # Assuming 'dados' refers to the cached data used before.
                        remove_messages = [x for x in current_cache if x not in cached_data]
                        utils.write_json(data["Discord"]["messages_cache"], remove_messages)
                        logging.info("Cache updated after sending AI message.")
                    except Exception as e:
                        logging.error("Error updating message cache: %s", e)
            else:
                logging.warning("No internet access detected. AI message not sent.")
                self.awaiting_response = False

    async def monitor_inactivity(self, client, message):
        """
        Monitors inactivity by checking every 3 seconds.
        If a specified inactivity time or a threshold number of cached messages is reached,
        the bot triggers the AI_send_message method.
        """
        while True:
            await asyncio.sleep(3)
            if not self.awaiting_response:
                try:
                    # Load the cache and count the number of cached message dictionaries.
                    with open("messages_cache.json", 'r', encoding="utf-8") as file:
                        cached_data = json.load(file)
                    cache_count = len(cached_data)

                    # Check if either inactivity time or a message count threshold is reached.
                    if (time.time() - self.last_message_time >= 7 or cache_count >= 5) and cache_count >= 1:
                        logging.info("Inactivity threshold reached (or cache count >= 5). Triggering AI_send_message.")
                        await self.AI_send_message(client)
                except Exception as e:
                    logging.error("Error in monitor_inactivity: %s", e)
