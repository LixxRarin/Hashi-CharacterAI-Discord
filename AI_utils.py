import asyncio
import json
import time
from typing import Dict, Any, Optional, Set, List

import aiohttp
import discord

import cai
import utils
import webhook
from utils import update_session_data, get_session_data


class discord_AI_bot:
    def __init__(self):
        """Initialize the bot's tracking variables."""
        self.response_lock = asyncio.Lock()
        # Track active response tasks by channel ID
        self.active_tasks: Dict[str, asyncio.Task] = {}
        # Set of channels currently being processed
        self.processing_channels: Set[str] = set()
        # Locks for each channel
        self.channel_locks: Dict[str, asyncio.Lock] = {}

    async def sync_config(self, client):
        """
        Synchronize each webhook's profile (name and avatar) with the AI info from C.AI,
        using the character_id stored in each session.

        Args:
            client: The Discord client
        """
        utils.log.info(
            "Synchronizing webhook configurations with Character.AI")
        for server_id, server_info in webhook.session_data.items():
            for channel_id, session_data in server_info.get("channels", {}).items():
                character_id = session_data.get("character_id")
                if not character_id:
                    utils.log.error(
                        "No character_id found for channel %s in server %s", channel_id, server_id)
                    continue

                try:
                    info = await cai.get_bot_info(character_id=character_id)
                    if not info:
                        utils.log.error(
                            "Failed to get bot info for character_id %s", character_id)
                        continue
                    utils.log.debug(
                        "Fetched bot info for character_id %s: %s", character_id, info["name"])
                except Exception as e:
                    utils.log.error(
                        "Failed to get bot info from C.AI for character_id %s: %s", character_id, e)
                    continue

                webhook_url = session_data.get("webhook_url")
                if webhook_url:
                    try:
                        async with aiohttp.ClientSession() as http_session:
                            async with http_session.get(info["avatar_url"]) as resp:
                                image_bytes = await resp.read() if resp.status == 200 else b""
                            webhook_obj = discord.Webhook.from_url(
                                webhook_url, session=http_session)
                            await webhook_obj.edit(name=info["name"], avatar=image_bytes, reason="Sync webhook info")
                            utils.log.info(
                                "Updated webhook for channel %s with new info from character_id %s", channel_id, character_id)
                    except Exception as e:
                        utils.log.error(
                            "Failed to update webhook for channel %s: %s", channel_id, e)

    def time_typing(self, channel, user, client):
        """
        Update the last_message_time in the session if a user (other than the bot) is typing.

        Args:
            channel: The Discord channel
            user: The Discord user
            client: The Discord client
        """
        try:
            # Skip if not in a guild or if the user is the bot
            if not hasattr(channel, "guild") or not channel.guild or user == client.user:
                return

            server_id = str(channel.guild.id)
            channel_id_str = str(channel.id)

            # Check if this channel has a session
            session = get_session_data(server_id, channel_id_str)

            if session:
                session["last_message_time"] = time.time()
                utils.log.debug(
                    "User %s is typing in channel %s; updated session last_message_time.", user, channel)
        except Exception as e:
            utils.log.error("Error in time_typing: %s", e)

    async def read_channel_messages(self, message, client):
        """
        Process a message from a monitored channel.
        Captures the message and (if applicable) the referenced reply message.

        Args:
            message: The Discord message
            client: The Discord client
        """
        try:
            if not message.guild or message.author.id == client.user.id:
                return

            if message.content.startswith(("#", "//")):
                return

            server_id = str(message.guild.id)

            # Get all channels that need to process this message
            channels_to_process = []
            server_channels = utils.session_cache.get(
                server_id, {}).get("channels", {})

            for channel_id, session in server_channels.items():
                if session:
                    channels_to_process.append(channel_id)

            utils.log.info(
                f"Processing message for {len(channels_to_process)} channels in server {server_id}")

            # Process all channels concurrently
            tasks = [
                self._process_channel_message(
                    client, message, server_id, target_channel_id)
                for target_channel_id in channels_to_process
            ]
            await asyncio.gather(*tasks)

        except Exception as e:
            utils.log.error(f"Error in read_channel_messages: {e}")

    async def _process_channel_message(self, client, message, server_id, channel_id_str):
        """
        Process a message for a specific channel.

        Args:
            client: The Discord client
            message: The Discord message
            server_id: The server ID
            channel_id_str: The channel ID
        """
        try:
            # Get or create a lock for this channel
            if channel_id_str not in self.channel_locks:
                self.channel_locks[channel_id_str] = asyncio.Lock()

            # Try to acquire the lock with a timeout
            try:
                # Use a short timeout to prevent deadlocks
                async with asyncio.timeout(5.0):
                    await self.channel_locks[channel_id_str].acquire()
            except asyncio.TimeoutError:
                utils.log.warning(
                    f"Timeout acquiring lock for channel {channel_id_str}")
                return

            try:
                session = utils.get_session_data(server_id, channel_id_str)
                if not session:
                    return

                utils.log.debug(
                    "Processing message for channel %s: %s",
                    channel_id_str,
                    message.content[:50] if message.content else "No content"
                )

                # Capture message
                if not message.webhook_id:
                    if message.reference:
                        try:
                            ref_message = await message.channel.fetch_message(message.reference.message_id)
                            utils.capture_message(message, ref_message)
                        except Exception as e:
                            utils.log.error(
                                "Error fetching reference message: %s", e)
                    else:
                        utils.capture_message(message)

                # Update session data
                session["last_message_time"] = time.time()
                session["awaiting_response"] = False
                await utils.update_session_data(server_id, channel_id_str, session)

                # Create new task for AI response
                task_key = f"ai_response_{server_id}_{channel_id_str}"
                self.active_tasks[task_key] = asyncio.create_task(
                    self.AI_send_message(client, message, channel_id_str)
                )
            finally:
                # Always release the lock
                self.channel_locks[channel_id_str].release()

        except Exception as e:
            utils.log.error(
                f"Error in _process_channel_message for channel {channel_id_str}: {e}")
            # Make sure to release the lock in case of error
            if channel_id_str in self.channel_locks and self.channel_locks[channel_id_str].locked():
                self.channel_locks[channel_id_str].release()

    async def AI_send_message(self, client, message, target_channel_id):
        """
        Generates and sends an AI response through the appropriate webhook.

        Args:
            client: The Discord client
            message: The Discord message
            target_channel_id: The target channel ID to send the response
        """
        server_id = str(message.guild.id)
        channel_id_str = target_channel_id

        # Skip if channel is already being processed
        channel_key = f"{server_id}_{channel_id_str}"
        if channel_key in self.processing_channels:
            utils.log.debug(
                f"Channel {channel_id_str} is already being processed, skipping")
            return

        # Mark channel as being processed
        self.processing_channels.add(channel_key)

        try:
            session = utils.get_session_data(server_id, channel_id_str)

            if not session:
                utils.log.error(
                    "No session data for channel %s in server %s", channel_id_str, server_id)
                return

            if not session.get("chat_id"):
                create_new_chat = utils.config_yaml["Character_AI"].get(
                    "new_chat_on_reset", False)
                session["chat_id"], _ = await cai.new_chat_id(create_new_chat, session, server_id, channel_id_str)
                await utils.update_session_data(server_id, channel_id_str, session)

            session["awaiting_response"] = True
            session["last_message_time"] = time.time()
            await utils.update_session_data(server_id, channel_id_str, session)

            # Get cached messages for this channel
            cached_data = await asyncio.to_thread(utils.read_json, "messages_cache.json") or {}

            # Check if there are any messages to respond to
            if not cached_data.get(server_id, {}).get(channel_id_str, {}):
                utils.log.info(
                    "No cached messages for channel %s", channel_id_str)
                session["awaiting_response"] = False
                await utils.update_session_data(server_id, channel_id_str, session)
                self.processing_channels.discard(channel_key)
                return

            # Queue response generation
            utils.log.info("Queueing AI response for channel %s (character_id: %s, chat_id: %s)",
                           channel_id_str, session["character_id"], session["chat_id"])

            # Define callback to handle the response
            async def handle_response(response):
                try:
                    # Process response
                    if utils.config_yaml["MessageFormatting"]["remove_emojis"]["AI"]:
                        response = utils.remove_emoji(response)

                    # Check if response is empty or only whitespace
                    if not response or response.isspace():
                        utils.log.warning(
                            "Received empty response from AI for channel %s", channel_id_str)
                        response = "I'm sorry, but I don't have a response at the moment. Could you please try again?"

                    # Send response via webhook
                    webhook_url = session.get("webhook_url")
                    if webhook_url:
                        await webhook.webhook_send(webhook_url, response)
                        utils.log.info(
                            "Sent AI response via webhook for channel %s", channel_id_str)

                        # Clear the message cache for this channel after successful response
                        cached_data = await asyncio.to_thread(utils.read_json, "messages_cache.json") or {}
                        if cached_data.get(server_id, {}).get(channel_id_str):
                            cached_data[server_id][channel_id_str] = {}
                            await asyncio.to_thread(utils.write_json, "messages_cache.json", cached_data)
                            utils.log.debug(
                                "Cleared message cache for channel %s", channel_id_str)
                    else:
                        utils.log.error(
                            "Webhook URL not found for channel %s", channel_id_str)

                    # Update session
                    current_session = utils.get_session_data(
                        server_id, channel_id_str)
                    if current_session:
                        current_session["awaiting_response"] = False
                        current_session["last_message_time"] = time.time()
                        await utils.update_session_data(server_id, channel_id_str, current_session)

                except Exception as e:
                    utils.log.error(f"Error in response handler: {e}")
                finally:
                    # Mark channel as no longer being processed
                    self.processing_channels.discard(channel_key)

            # Queue the response with a timeout
            try:
                # Set a timeout for the queue operation
                # 10 second timeout for queueing
                async with asyncio.timeout(10.0):
                    await cai.queue_response(
                        server_id,
                        channel_id_str,
                        message,
                        session["chat_id"],
                        session["character_id"],
                        handle_response
                    )
            except asyncio.TimeoutError:
                utils.log.error(
                    f"Timeout queueing response for channel {channel_id_str}")
                self.processing_channels.discard(channel_key)
                session["awaiting_response"] = False
                await utils.update_session_data(server_id, channel_id_str, session)

        except Exception as e:
            utils.log.error(
                "Error in AI_send_message for channel %s: %s", channel_id_str, e)
            # Mark channel as no longer being processed
            self.processing_channels.discard(channel_key)

            # Update session
            session = utils.get_session_data(server_id, channel_id_str)
            if session:
                session["awaiting_response"] = False
                await utils.update_session_data(server_id, channel_id_str, session)

    async def monitor_inactivity(self, client, message):
        """
        Checks if a channel has been inactive and triggers AI response if needed.

        Args:
            client: The Discord client
            message: The Discord message
        """
        # Skip if not in a guild
        server = message.guild or (
            hasattr(message.channel, "guild") and message.channel.guild)
        if not server:
            return

        server_id = str(server.id)
        channel_id_str = str(message.channel.id)

        # Get the session for this channel
        session = get_session_data(server_id, channel_id_str)

        if not session:
            return

        # Create a unique task name for this monitor
        task_name = f"monitor_{server_id}_{channel_id_str}"

        # Check if a monitor task is already running for this channel
        if task_name in self.active_tasks and not self.active_tasks[task_name].done():
            # Task already running, no need to start another
            return

        # Start a new monitor task
        self.active_tasks[task_name] = asyncio.create_task(
            self._monitor_channel_inactivity(
                client, message, server_id, channel_id_str, session)
        )

    async def _monitor_channel_inactivity(self, client, message, server_id, channel_id_str, session):
        """
        Internal method to monitor channel inactivity.

        Args:
            client: The Discord client
            message: The Discord message
            server_id: The Discord server ID
            channel_id_str: The Discord channel ID
            session: The session data for this channel
        """
        try:
            while True:
                await asyncio.sleep(3)

                # Reload session data to get latest status
                current_session = get_session_data(server_id, channel_id_str)

                # Skip if session no longer exists
                if not current_session:
                    utils.log.debug(
                        "Session no longer exists for channel %s, stopping monitor", channel_id_str)
                    break

                # Skip if already awaiting response
                if current_session.get("awaiting_response", False):
                    continue

                # Skip if channel is already being processed
                channel_key = f"{server_id}_{channel_id_str}"
                if channel_key in self.processing_channels:
                    continue

                # Check for inactivity or message threshold
                cached_data = await asyncio.to_thread(utils.read_json, "messages_cache.json") or {}
                channel_messages = cached_data.get(
                    server_id, {}).get(channel_id_str, {})
                cache_count = len(channel_messages)

                time_since_last = time.time() - current_session.get("last_message_time", 0)

                if ((time_since_last >= 7 or cache_count >= 5) and cache_count > 0):
                    utils.log.debug(
                        "Inactivity detected for channel %s (%d seconds, %d messages). Triggering AI response.",
                        channel_id_str, time_since_last, cache_count
                    )

                    # Cancel any existing response task
                    task_key = f"{server_id}_{channel_id_str}"
                    if task_key in self.active_tasks and not self.active_tasks[task_key].done():
                        self.active_tasks[task_key].cancel()
                        try:
                            await self.active_tasks[task_key]
                        except asyncio.CancelledError:
                            pass

                    # Create a new response task
                    self.active_tasks[task_key] = asyncio.create_task(
                        self.AI_send_message(client, message, channel_id_str)
                    )

                    # Wait for the response to complete
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            utils.log.debug(
                "Monitor task for channel %s was cancelled", channel_id_str)
        except Exception as e:
            utils.log.error(
                "Error in monitor_inactivity for channel %s: %s", channel_id_str, e)
