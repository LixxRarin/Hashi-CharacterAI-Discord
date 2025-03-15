import os

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from packaging import version

import utils.func as func

# Set up ruamel.yaml in round-trip mode (preserves order and comments)
yaml = YAML(typ='rt')
yaml.preserve_quotes = True
yaml.encoding = "utf-8"

# Default configuration content
DEFAULT_CONFIG_CONTENT = r"""version: "1.1.4" # Don't touch here

# Discord Bot Configuration
Discord:
  token: "YOUR_DISCORD_BOT_TOKEN"
  # This is the token used to authenticate your bot with Discord.
  # Keep this token secure and do not share it publicly.

  messages_cache: "messages_cache.json"  # Path to the file where messages are cached.
  # This file stores the chat history for the bot.
  # It is used to keep track of conversations and ensure consistency.
  # If you have a lot of data, this file could grow in size.

# Character.AI Configuration
Character_AI:
  token: "YOUR_CHARACTER_AI_TOKEN"
  # This is the token for authenticating your bot with Character.AI.
  # Like the Discord token, keep this token private and do not share it.

# Bot Interaction Settings
Options:
  
  auto_update: true # If true, the program will check for a new update every time it starts up
  #If true, the program will automatically search for an update
  # For realases or commits, this depends on how you run Bridget

  repo_url: "git@github.com:LixxRarin/CharacterAI-Discord-Bridge.git" # Repository url
  # This is the repository where the program will check and update.
  # Only touch this if you know what you're doing here!

  repo_branch: "main" 
  # This is the branch where the program will check and update.
  # Only touch this if you know what you're doing here!

  enable_alternative_cai_token: false
  # 'true' if you want users to be able to use their alternative Character.AI tokens in their IAs.
  # This is useful if you don't want user tokens to be stored in 'session.json', for security reasons.
  # Please do not use for malicious purposes.

  debug_mode: false  # Enable debug mode for troubleshooting.
  # When true, the bot will log detailed information about its processes in the console, which is helpful for debugging.
  # This mode should be off in production to avoid excessive logging.
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
            func.log.error("Error loading user configuration: %s", e)
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
            func.log.warning(
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
            func.log.warning(
                "Configuration file '%s' not found. Creating a new one...", self.config_file)
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    yaml.dump(self.default_config, f)
                func.log.info(
                    "Configuration file '%s' created successfully!", self.config_file)
            except Exception as e:
                func.log.critical(
                    "Failed to create configuration file: %s", e)
            return

        if self.is_version_outdated():
            func.log.warning("Updating configuration '%s' to version %s",
                             self.config_file, self.default_config.get("version"))
            updated_config = self.merge_configs()
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    yaml.dump(updated_config, f)
                func.log.info(
                    "Configuration file '%s' updated successfully!", self.config_file)
            except Exception as e:
                func.log.critical(
                    "Failed to update configuration file: %s", e)
        else:
            func.log.info(
                "Configuration file '%s' is up-to-date.", self.config_file)
