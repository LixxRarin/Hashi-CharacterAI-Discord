import asyncio
import time
from typing import Dict, Any, Optional, Set, List

import aiohttp
import discord

import AI.cai as cai
import utils.func as func
import commands.webhook as webhook


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
        func.log.info(
            "Synchronizing webhook configurations with Character.AI")
        for server_id, server_info in webhook.session_data.items():
            for channel_id, session_data in server_info.get("channels", {}).items():
                character_id = session_data.get("character_id")
                if not character_id:
                    func.log.error(
                        "No character_id found for channel %s in server %s", channel_id, server_id)
                    continue

                try:
                    info = await cai.get_bot_info(character_id=character_id)
                    if not info:
                        func.log.error(
                            "Failed to get bot info for character_id %s", character_id)
                        continue
                    func.log.debug(
                        "Fetched bot info for character_id %s: %s", character_id, info["name"])
                except Exception as e:
                    func.log.error(
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
                            func.log.info(
                                "Updated webhook for channel %s with new info from character_id %s", channel_id, character_id)
                    except Exception as e:
                        func.log.error(
                            "Failed to update webhook for channel %s: %s", channel_id, e)

    def time_typing(self, channel, user, client):
        """
        Continuously update last_message_time while user is typing to keep session active.

        Args:
            channel: Discord channel object
            user: Discord user object
            client: Discord client instance
        """
        try:
            # Ignore DMs and bot's own typing
            if not hasattr(channel, "guild") or not channel.guild or user == client.user:
                return

            server_id = str(channel.guild.id)
            channel_id_str = str(channel.id)

            # Only process if session exists
            if session := func.get_session_data(server_id, channel_id_str):
                current_time = time.time()

                # Always update timestamp and persist
                session["last_message_time"] = current_time
                asyncio.create_task(
                    func.update_session_data(
                        server_id, channel_id_str, session)
                )

                func.log.debug(
                    f"Typing activity from {user} in {channel.name}, "
                    f"session extended to {current_time}"
                )

        except Exception as e:
            func.log.error(f"Typing handler error: {str(e)}", exc_info=True)

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

            session = func.get_session_data(
                str(message.guild.id), str(message.channel.id))

            if message.author.id in session["muted_users"]:
                return

            server_id = str(message.guild.id)

            # Get all channels that need to process this message
            channels_to_process = []
            server_channels = func.session_cache.get(
                server_id, {}).get("channels", {})

            for channel_id, session in server_channels.items():
                if session:
                    channels_to_process.append(channel_id)

            func.log.info(
                f"Processing message for {len(channels_to_process)} channels in server {server_id}")

            # Process all channels concurrently
            tasks = [
                self._process_channel_message(
                    client, message, server_id, target_channel_id)
                for target_channel_id in channels_to_process
            ]
            await asyncio.gather(*tasks)

        except Exception as e:
            func.log.error(f"Error in read_channel_messages: {e}")

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
                func.log.warning(
                    f"Timeout acquiring lock for channel {channel_id_str}")
                return

            try:
                session = func.get_session_data(server_id, channel_id_str)
                if not session:
                    return

                func.log.debug(
                    "Processing message for channel %s: %s",
                    channel_id_str,
                    message.content[:50] if message.content else "No content"
                )

                # Capture message
                if not message.webhook_id:
                    if message.reference:
                        try:
                            ref_message = await message.channel.fetch_message(message.reference.message_id)
                            func.capture_message(message, ref_message)
                        except Exception as e:
                            func.log.error(
                                "Error fetching reference message: %s", e)
                    else:
                        func.capture_message(message)

                # Update session data
                session["last_message_time"] = time.time()
                session["awaiting_response"] = False
                await func.update_session_data(server_id, channel_id_str, session)

                # Create new task for AI response
                # task_key = f"ai_response_{server_id}_{channel_id_str}"
                # self.active_tasks[task_key] = asyncio.create_task(
                #    self.AI_send_message(client, message, channel_id_str)
                # )
            finally:
                # Always release the lock
                self.channel_locks[channel_id_str].release()

        except Exception as e:
            func.log.error(
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
            func.log.debug(
                f"Channel {channel_id_str} is already being processed, skipping")
            return

        # Mark channel as being processed
        self.processing_channels.add(channel_key)

        try:
            session = func.get_session_data(server_id, channel_id_str)

            if not session:
                func.log.error(
                    f"No session data for channel {channel_id_str} in server {server_id}")
                return

            if not session.get("chat_id"):
                create_new_chat = session["config"].get(
                    "new_chat_on_reset", False)
                session["chat_id"], _ = await cai.new_chat_id(create_new_chat, session, server_id, channel_id_str)
                await func.update_session_data(server_id, channel_id_str, session)

            session["awaiting_response"] = True
            session["last_message_time"] = time.time()
            await func.update_session_data(server_id, channel_id_str, session)

            # Get cached messages for this channel
            cached_data = await asyncio.to_thread(func.read_json, "messages_cache.json") or {}

            # Check if there are any messages to respond to
            if not cached_data.get(server_id, {}).get(channel_id_str, {}):
                func.log.info(
                    "No cached messages for channel %s", channel_id_str)
                session["awaiting_response"] = False
                await func.update_session_data(server_id, channel_id_str, session)
                self.processing_channels.discard(channel_key)
                return

            # Wait a bit to see if the user is still typing (3 seconds delay)
            # This helps prevent responding while the user is still typing
            await asyncio.sleep(3)

            # Check if last_message_time has been updated during our wait
            # If it has, it means the user is still typing or sent another message
            current_session = func.get_session_data(server_id, channel_id_str)
            if current_session and current_session.get("last_message_time", 0) > session.get("last_message_time", 0):
                func.log.debug(
                    f"User still typing or sent new message in channel {channel_id_str}, delaying response")
                self.processing_channels.discard(channel_key)
                return

            # Queue response generation
            func.log.info(
                f"Queueing AI response for channel {channel_id_str} (character_id: {session['character_id']}, chat_id: {session['chat_id']})")

            async def handle_response(response):

                try:

                    session = func.get_session_data(server_id, channel_id_str)

                    # func.log.debug(f"Session data: {session}")
                    # Process the response
                    if session["config"]["remove_ai_emoji"]:
                        response = func.remove_emoji(response)

                    # Check if the response is empty or just whitespace
                    if not response or response.isspace():
                        func.log.warning(
                            f"Received empty response from AI for channel {channel_id_str}")
                        response = "I'm sorry, but I don't have a response at the moment. Could you please try again?"

                    # Send the response via webhook
                    webhook_url = session.get("webhook_url")
                    if webhook_url:
                        # Send message immediately without typing simulation
                        await webhook.webhook_send(webhook_url, response, session)
                        func.log.info(
                            f"Sent AI response via webhook for channel {channel_id_str}")

                        # Clear the processed messages from cache
                        await func.remove_sent_messages_from_cache(server_id, channel_id_str)
                    else:
                        func.log.error(
                            f"Webhook URL not found for channel {channel_id_str}")

                    # Update the session
                    current_session = func.get_session_data(
                        server_id, channel_id_str)
                    if current_session:
                        current_session["awaiting_response"] = False
                        current_session["last_message_time"] = time.time()
                        await func.update_session_data(server_id, channel_id_str, current_session)

                except Exception as e:
                    func.log.error(
                        f"Error in response handler: {e}")
                finally:
                    # Mark the channel as no longer being processed
                    self.processing_channels.discard(channel_key)

            # Queue the response with a timeout
            async with message.channel.typing():
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
                    func.log.error(
                        f"Timeout queueing response for channel {channel_id_str}")
                    self.processing_channels.discard(channel_key)
                    session["awaiting_response"] = False
                    await func.update_session_data(server_id, channel_id_str, session)

        except Exception as e:
            func.log.error(
                "Error in AI_send_message for channel %s: %s", channel_id_str, e)
            # Mark channel as no longer being processed
            self.processing_channels.discard(channel_key)

            # Update session
            session = func.get_session_data(server_id, channel_id_str)
            if session:
                session["awaiting_response"] = False
                await func.update_session_data(server_id, channel_id_str, session)

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
        session = func.get_session_data(server_id, channel_id_str)

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
                await asyncio.sleep(0.5)

                # Reload session data to get latest status
                current_session = func.get_session_data(
                    server_id, channel_id_str)

                # Skip if session no longer exists
                if not current_session:
                    func.log.debug(
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
                cached_data = await asyncio.to_thread(func.read_json, "messages_cache.json") or {}
                channel_messages = cached_data.get(
                    server_id, {}).get(channel_id_str, {})
                cache_count = len(channel_messages)

                time_since_last = time.time() - current_session.get("last_message_time", 0)
                delay = session["config"].get("delay_for_generation", 5)

                if ((time_since_last >= delay or cache_count >= 5) and cache_count > 0):
                    func.log.debug(
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
            func.log.debug(
                "Monitor task for channel %s was cancelled", channel_id_str)
        except Exception as e:
            func.log.error(
                "Error in monitor_inactivity for channel %s: %s", channel_id_str, e)
