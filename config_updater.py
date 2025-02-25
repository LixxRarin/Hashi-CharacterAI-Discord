import os

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from packaging import version

import utils

# Set up ruamel.yaml in round-trip mode (preserves order and comments)
yaml = YAML(typ='rt')
yaml.preserve_quotes = True
yaml.encoding = "utf-8"

# Default configuration content
DEFAULT_CONFIG_CONTENT = r"""version: "1.1.0" # Don't touch here

# Discord Bot Configuration
Discord:
  token: "YOUR_DISCORD_BOT_TOKEN"
  # This is the token used to authenticate your bot with Discord.
  # Keep this token secure and do not share it publicly.

  channel_bot_chat: [12345678]  # The ID of the channel where the bot responds.
  # Use the Discord channel ID where you want the bot to send messages.
  # The bot will listen and send messages to this channel.

  use_cai_avatar: true  # Whether to use the Character.AI profile picture for the bot.
  # If set to true, the bot will display the avatar from Character.AI.

  use_cai_display_name: true  # Whether to use the Character.AI display name for the bot.
  # If true, the bot's name will be replaced by the display name of the Character.AI character.

  messages_cache: "messages_cache.json"  # Path to the file where messages are cached.
  # This file stores the chat history for the bot.
  # It is used to keep track of conversations and ensure consistency.
  # If you have a lot of data, this file could grow in size.

# Character.AI Configuration
Character_AI:
  token: "YOUR_CHARACTER_AI_TOKEN"
  # This is the token for authenticating your bot with Character.AI.
  # Like the Discord token, keep this token private and do not share it.

  character_id: "7OQWCw72T2hHr8JwNIjXd8KpTy663wI_piz4XCHbeZ4"  # The ID of the Character.AI character.
  # This is the unique identifier for the character you want the bot to use.
  # The default ID is from Neuro-Sama

  chat_id: "79c6b54e-717f-4fc2-97bd-57620baa4b47"
  # This is the ID of the specific chat session you want the bot to join.
  # It allows the bot to maintain continuity in its interactions with users.
  # Use “null” if you don't have a chat ID, the program will automatically fill "cache.json" in a new ID.

  new_chat_on_reset: false  # Whether to create a new chat session when resetting.
  # If set to true, a new chat session will be created each time the bot is reset.
  # If set to false, the bot will continue the current chat session after a reset.

  system_message: >
    [DO NOT RESPOND TO THIS MESSAGE!]

    You are connected to a Discord channel, 
    where several people may be present. Your objective is to interact with them in the chat.

    Greet the participants and introduce yourself by fully translating your message into English.

    Now, send your message introducing yourself in the chat, following the language of this message!
  # A system message is the first message that will be sent to your character
  # Use 'system_message: null' to not use a system message

# Bot Interaction Settings
Options:
  auto_update: true # If true, the program will check for a new update every time it starts up
  #If true, the program will automatically search for an update
  # For realases or commits, this depends on how you run Bridge

  repo_url: "git@github.com:LixxRarin/CharacterAI-Discord-Bridge.git" # Repository url
  # This is the repository where the program will check and update.
  # Only touch this if you know what you're doing here!

  repo_branch: "main" 
  # This is the branch where the program will check and update.
  # Only touch this if you know what you're doing here!
  
  send_the_greeting_message: true
  # Send the character first greeting message

  send_the_system_message_reply: true
  # Send the character reply to the system message
  # This is ignored if the system message is null

  max_response_attempts: -1  # Set the number of response attempts, -1 for automatic retries.
  # The bot will try to respond a maximum of this many times. If set to -1, the bot will keep retrying until a valid response is received.
  # If it is still not possible to generate a message, the bot will send an error message

  send_message_line_by_line: true  # Whether to send bot messages one line at a time.
  # If true, the bot will send each message in the chat as separate lines, rather than sending everything at once.
  # This can make the interaction feel more natural or less overwhelming.

  debug_mode: true  # Enable debug mode for troubleshooting.
  # When true, the bot will log detailed information about its processes in the console, which is helpful for debugging.
  # This mode should be off in production to avoid excessive logging.

# Message Formatting Rules
MessageFormatting:
  remove_IA_text_from: ['\*[^*]*\*', '\[[^\]]*\]', '"']
  remove_user_text_from: ['\*[^*]*\*', '\[[^\]]*\]']
  # Remove certain patterns from the AI and user messages.
  # This removes text enclosed in asterisks (often used for emphasis or actions),
  # any text in square brackets (often for OOC), and any quotation marks.
  # Adjust these patterns as needed based on the format of your messages.

  remove_emojis:
    user: false
    AI: false
  # Whether to remove emojis from user or/and AI messages.
  # If set to true, emojis will be stripped from user messages before they are processed.
  # Setting to false keeps emojis in the conversation.

  user_reply_format_syntax: |
    ┌──[🔁 Replying to @{reply_username} - {reply_name}]
    │   ├─ 📝 Reply: {reply_message}
    │   └─ ⏳ {time} ~ @{username} - {name}
    |   └─ 📢 Message: {message}
    └───────────────────────────────────────
  user_format_syntax: |
    ┌──[💬]
    │   ├─ ⏳ {time} ~ @{username} - {name}
    │   └─ 📢 Message: {message}
    └───────────────────────────────────────
  # This is the syntax that messages will be sent from the Discord channel to the Character.AI character
  # Modify it to your advantage
"""


def merge_ordered(user_cfg, default_cfg):
    """
    Merges two CommentedMaps while preserving the order defined in default_cfg.

    For each key in default_cfg:
      - If the key exists in user_cfg, use its value.
      - If both values are dictionaries, merge them recursively.
      - Otherwise, fall back to the default value.

    Extra keys present in user_cfg that are not in default_cfg are discarded.

    Additionally, comment attributes (if present) are preserved from either configuration.
    """
    merged = CommentedMap()
    for key, default_val in default_cfg.items():
        # If the user configuration contains the key, process its value
        if key in user_cfg:
            user_val = user_cfg[key]
            # If both default and user values are dictionaries, merge them recursively
            if isinstance(default_val, dict) and isinstance(user_val, dict):
                merged[key] = merge_ordered(user_val, default_val)
            else:
                # Use the user's value if it's not a dictionary or cannot be merged recursively
                merged[key] = user_val
        else:
            # If the key is missing in the user configuration, use the default value
            merged[key] = default_val

        # Preserve comment attributes if available in user_cfg; otherwise, fall back to default_cfg comments
        if hasattr(user_cfg, 'ca') and key in user_cfg.ca.items:
            merged.ca.items[key] = user_cfg.ca.items.get(key)
        elif hasattr(default_cfg, 'ca') and key in default_cfg.ca.items:
            merged.ca.items[key] = default_cfg.ca.items.get(key)
    return merged


class ConfigManager:
    def __init__(self, config_file="config.yml"):
        """
        Initializes the configuration manager.

        - Loads the default configuration from DEFAULT_CONFIG_CONTENT.
        - Attempts to load the user configuration from the given file.
        """
        self.config_file = config_file
        self.default_config = yaml.load(DEFAULT_CONFIG_CONTENT)
        self.user_config = self.load_user_config()

    def load_user_config(self):
        """
        Loads the user configuration from the file.

        Returns:
            The parsed configuration if the file exists and is valid,
            otherwise returns None.
        """
        if not os.path.exists(self.config_file):
            return None
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return yaml.load(f)
        except Exception as e:
            # Log error if loading the configuration fails
            utils.log.error("Error loading user configuration: %s", e)
            return None

    def is_version_outdated(self):
        """
        Checks whether the user configuration is outdated compared to the default configuration.

        Returns:
            True if:
              - The user configuration does not have a version.
              - The user's version is less than the default version.
            False otherwise.
        """
        user_version = self.user_config.get(
            "version") if self.user_config else None
        default_version = self.default_config.get("version")
        if user_version is None:
            # Log a warning if no version is found in the user configuration
            utils.log.warning(
                "No version found in user configuration. Assuming outdated.")
            return True
        return version.parse(user_version) < version.parse(default_version)

    def merge_configs(self):
        """
        Merges the user configuration with the default configuration.

        This method:
          - Preserves the order of keys as defined in the default configuration.
          - Discards any extra keys that are not present in the default configuration.
          - Updates the root "version" key to match the default configuration.
        """
        if self.user_config is None:
            return self.default_config
        merged = merge_ordered(self.user_config, self.default_config)
        # Ensure the "version" key is updated to the default version
        merged["version"] = self.default_config.get("version")
        return merged

    async def check_and_update(self):
        """
        Checks if the configuration file exists and whether it is up-to-date.

        This method performs the following:
          - If the configuration file does not exist, it creates one using the default configuration.
          - If the user configuration is outdated (based on version comparison), it updates the file.
          - Logs all actions including successes, warnings, and errors.
        """
        if self.user_config is None:
            utils.log.warning(
                "Configuration file '%s' not found. Creating a new one...", self.config_file)
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    yaml.dump(self.default_config, f)
                utils.log.info(
                    "Configuration file '%s' created successfully!", self.config_file)
            except Exception as e:
                utils.log.critical(
                    "Failed to create configuration file: %s", e)
            return

        if self.is_version_outdated():
            utils.log.warning("Updating configuration '%s' to version %s",
                              self.config_file, self.default_config.get("version"))
            updated_config = self.merge_configs()
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    yaml.dump(updated_config, f)
                utils.log.info(
                    "Configuration file '%s' updated successfully!", self.config_file)
            except Exception as e:
                utils.log.critical(
                    "Failed to update configuration file: %s", e)
        else:
            utils.log.info(
                "Configuration file '%s' is up-to-date.", self.config_file)
