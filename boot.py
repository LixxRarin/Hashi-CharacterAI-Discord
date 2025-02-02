import os
import time
from colorama import init, Fore, Style
import logging
from ruamel.yaml import YAML

logging.basicConfig(
    level=logging.DEBUG,
    filename="app.log",
    format='[%(filename)s] %(levelname)s : %(message)s',
    encoding="utf-8"
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Set console log level
console_handler.setFormatter(logging.Formatter('[%(filename)s] %(levelname)s : %(message)s'))

yaml = YAML()
yaml.preserve_quotes = True

yaml.encoding = "utf-8"

config_content = r"""version: "1.0.1" # Don't touch here

# Discord Bot Configuration
Discord:
  token: "YOUR_DISCORD_BOT_TOKEN"
  # This is the token used to authenticate your bot with Discord.
  # Keep this token secure and do not share it publicly.

  channel_bot_chat: [12345678]  # The ID of the channel where the bot responds.
  # Use the Discord channel ID where you want the bot to send messages.
  # The bot will listen and send messages to this channel.

  admin_role: [12345678]  # The ID of the administrator role in Discord.
  # Only users with this role will have administrator commands privileges.
  # This option is not yet available!!!

  use_cai_avatar: true  # Whether to use the Character.AI profile picture for the bot.
  # If set to true, the bot will display the avatar from Character.AI.

  use_cai_display_name: true  # Whether to use the Character.AI display name for the bot.
  # If true, the bot's name will be replaced by the display name of the Character.AI character.

  messages_cache: "messages_cache.json"  # Path to the file where messages are cached.
  # This file stores the chat history for the bot.
  # It is used to keep track of conversations and ensure consistency.
  # If you have a lot of data, this file could grow in size.

# Character.AI Configuration
CAI:
  token: "YOUR_CHARACTER_AI_TOKEN"
  # This is the token for authenticating your bot with Character.AI.
  # Like the Discord token, keep this token private and do not share it.

  character_id: "7OQWCw72T2hHr8JwNIjXd8KpTy663wI_piz4XCHbeZ4"  # The ID of the Character.AI character.
  # This is the unique identifier for the character you want the bot to use.
  # The default ID is from Neuro-Sama

  chat_id: "---"
  # This is the ID of the specific chat session you want the bot to join.
  # It allows the bot to maintain continuity in its interactions with users.
  # Use “---” if you don't have a chat ID, the program will automatically fill in a new ID.

  new_chat_on_reset: true  # Whether to create a new chat session when resetting.
  # If set to true, a new chat session will be created each time the bot is reset.
  # If set to false, the bot will continue the current chat session after a reset.

  system_message: >
    [DO NOT RESPOND TO THIS MESSAGE!]

    You are connected to a Discord channel, 
    where several people may be present. Your objective is to interact with them in the chat.

    Greet the participants and introduce yourself by fully translating your message into English.

    Now, send your message introducing yourself in the chat, following the language of this message!

# Bot Interaction Settings
Options:
  max_response_attempts: -1  # Set the number of response attempts, -1 for automatic retries.
  # The bot will try to respond a maximum of this many times. If set to -1, the bot will keep retrying until a valid response is received.

  send_message_line_by_line: true  # Whether to send bot messages one line at a time.
  # If true, the bot will send each message in the chat as separate lines, rather than sending everything at once.
  # This can make the interaction feel more natural or less overwhelming.

  debug_mode: true  # Enable debug mode for troubleshooting.
  # When true, the bot will log detailed information about its processes in the console, which is helpful for debugging.
  # This mode should be off in production to avoid excessive logging.
  # This option is not yet available!!!

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
  # This option is not yet available!!!

  user_reply_format_syntax: "[(Reply: @{reply_name}:) {reply_message}]\n[[time} ~ @{username} - {name}:] {message}"
  user_format_syntax: "[{time} ~ @{username} - {name}:] {message}"
"""


class ConfigVersion:
    def __init__(self, config_file="config.yml"):
        """
        Initializes the configuration manager.
        Loads the default configuration and user configuration if available.
        """
        self.config_file = config_file

        # Load default configuration as a dictionary
        self.default_config = yaml.load(config_content)

        # Load user configuration if it exists, otherwise None
        self.user_config = self.load_user_config()

    def load_user_config(self):
        """
        Loads the user's configuration file.
        If the file does not exist, returns None.
        """
        if not os.path.exists(self.config_file):
            return None
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return yaml.load(f)
        except Exception as e:
            logging.error("Error loading user configuration: %s", e)
            return None

    def is_version_outdated(self):
        """
        Checks if the user's configuration version is outdated.
        Returns True if the user's version is older than the default version.
        """
        user_version = self.user_config.get("version") if self.user_config else None
        default_version = self.default_config.get("version")
        
        if user_version is None:
            logging.warning("No version found in user config. Assuming outdated.")
            return True
        
        return user_version < default_version

    def merge_configs(self, user_cfg, default_cfg, root=True):
        """
        Recursively merges the default configuration into the user's configuration.
        - Removes keys from user_cfg that no longer exist in default_cfg.
        - Adds new keys from default_cfg to user_cfg.
        - Retains user-defined values for existing keys.
        - Ensures the version is updated only in the root dictionary.
        """
        if root:
            # Ensure 'version' is NOT removed during cleanup
            keys_to_remove = [key for key in user_cfg if key not in default_cfg and key != "version"]
        else:
            keys_to_remove = [key for key in user_cfg if key not in default_cfg]

        for key in keys_to_remove:
            logging.info("Removing obsolete key: %s", key)
            del user_cfg[key]

        for key, default_value in default_cfg.items():
            if key in user_cfg:
                if isinstance(default_value, dict) and isinstance(user_cfg[key], dict):
                    self.merge_configs(user_cfg[key], default_value, root=False)
                elif not isinstance(user_cfg[key], type(default_value)):
                    logging.info("Updating key: %s (Type mismatch, replacing with default)", key)
                    user_cfg[key] = default_value
            else:
                logging.info("Adding new key: %s", key)
                user_cfg[key] = default_value

        # Only update 'version' at the root level
        if root:
            user_cfg["version"] = default_cfg.get("version")

        return user_cfg

    def check(self):
        """
        Checks the configuration file and updates it if necessary.
        - If no config file exists, it creates one using the default configuration.
        - If the config file is outdated, it updates it while preserving user values.
        """
        # If no user config exists, create a new one with the default configuration
        if self.user_config is None:
            logging.warning("Configuration file '%s' not found. Creating a new one...", self.config_file)
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    f.write(config_content)
                logging.info("Configuration file '%s' created successfully!", self.config_file)
            except Exception as e:
                logging.critical("Failed to create configuration file: %s", e)
            return

        # If user configuration is outdated, merge and update the file
        if self.is_version_outdated():
            logging.warning("Updating '%s' to the latest version: %s", self.config_file, self.default_config.get("version"))
            updated_config = self.merge_configs(self.user_config, self.default_config)
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    yaml.dump(updated_config, f)
                logging.info("Configuration file '%s' updated successfully!", self.config_file)
            except Exception as e:
                logging.critical("Failed to update configuration file: %s", e)
        else:
            logging.info("Configuration file '%s' is up-to-date. No changes needed.", self.config_file)

# Initialize colorama (for Windows compatibility)
init(autoreset=True)

def startup_screen():
    os.system("cls" if os.name == "nt" else "clear")  # Clear the console (Windows & Linux/macOS)
    
    banner = f"""
{Fore.CYAN}{Style.BRIGHT}Project: {Fore.WHITE}Bridge - CharacterAI personas in Discord.
{Fore.YELLOW}Description: {Fore.WHITE}An AI-powered Discord bot using Character.AI! :3 
{Fore.YELLOW}Creator: {Fore.WHITE}LixxRarin
{Fore.YELLOW}GitHub: {Fore.WHITE}https://github.com/LixxRarin/CharacterAI-Discord-Bridge
{Fore.YELLOW}Version: {Fore.WHITE}1.0.0 (first release)
{Style.RESET_ALL}
"""

    print(banner)
    time.sleep(2)  # Pause for 2 seconds before proceeding

# Call the function to display the startup screen
startup_screen()
config = ConfigVersion()
config.check()