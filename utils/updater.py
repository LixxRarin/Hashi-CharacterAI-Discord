import json
import os
import re
import sys
import time
import zipfile
import asyncio
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Dict, Any

import requests
from colorama import Fore, init, Style
from packaging import version

import utils.func as func
from utils.config_updater import ConfigManager

if not os.path.exists("version.txt"):
    with open("version.txt", "w") as file:
        file.write("1.1.4\n")

# Initialize colorama for cross-platform colored output
init(autoreset=True)


def sync_dict(current, default):
    """
    Recursively synchronize the current dictionary with the default model.
    - Adds keys missing in current using the default value.
    - Keeps keys that already exist.
    - Removes keys not defined in the default model.
    """
    new_dict = {}
    for key, default_value in default.items():
        if key in current:
            # If both values are dictionaries, update recursively
            if isinstance(default_value, dict) and isinstance(current[key], dict):
                new_dict[key] = sync_dict(current[key], default_value)
            else:
                new_dict[key] = current[key]
        else:
            # If the default value is callable (like lambda for time), call it
            new_dict[key] = default_value() if callable(default_value) else default_value
    # Remove keys not in default (strict sync)
    return new_dict


def update_session_file(file_path="session.json"):
    """
    Update the session.json file:
    - Only update existing servers/channels.
    - For each channel, add missing keys (with default values) and remove extra keys.
    - If a channel's data is null, remove that channel entry.
    - Do NOT overwrite existing values like webhook_url, only add missing keys.
    """
    # Updated default model for channel configuration.
    default_channel_model = {
        "channel_name": "default_channel_name",  # Placeholder for channel.name
        "character_id": "default_character_id",  # Placeholder for character_id
        "webhook_url": None,                     # Default is None, do not overwrite valid URLs!
        "chat_id": None,
        "setup_has_already": False,
        "last_message_time": lambda: time.time(),
        "awaiting_response": False,
        "alt_token": None,
        "muted_users": [],
        "mode": None,                            # New field for mode ("bot" or "webhook")
        "config": {
            "use_cai_avatar": True,
            "use_cai_display_name": True,
            "new_chat_on_reset": False,
            "system_message": """[DO NOT RESPOND TO THIS MESSAGE!]
You are connected to a Discord channel, where several people may be present. Your objective is to interact with them in the chat.
Greet the participants and introduce yourself by fully translating your message into English.
Now, send your message introducing yourself in the chat, following the language of this message!""",
            "send_the_greeting_message": True,
            "send_the_system_message_reply": True,
            "send_message_line_by_line": True,
            "delay_for_generation": 5,
            "remove_ai_text_from": [r'\*[^*]*\*', r'\[[^\]]*\]', '"'],
            "remove_user_text_from": [r'\*[^*]*\*', r'\[[^\]]*\]'],
            "remove_user_emoji": True,
            "remove_ai_emoji": True,
            "user_reply_format_syntax": """┌──[🔁 Replying to @{reply_username} - {reply_name}]
│   ├─ 📝 Reply: {reply_message}
│   └─ ⏳ {time} ~ @{username} - {name}
|   └─ 📢 Message: {message}
└───────────────────────────────────────""",
            "user_format_syntax": """┌──[💬]
│   ├─ ⏳ {time} ~ @{username} - {name}
│   └─ 📢 Message: {message}
└───────────────────────────────────────"""
        }
    }

    # Check if the session file exists; if not, create an empty session data dictionary
    if not os.path.exists(file_path):
        func.log.info(
            f"Session file '{file_path}' does not exist. Creating a new file.")
        session_data = {}
    else:
        # Load existing session data
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                session_data = json.load(f)
            except json.JSONDecodeError:
                func.log.warning(
                    "Error: JSON file is not properly formatted. Creating a new empty session data.")
                session_data = {}

    # Iterate over each server in the session data
    for server_id, server_data in session_data.items():
        func.log.debug(f"Processing server: {server_id}")
        # Only update if the server has a 'channels' key
        if "channels" in server_data:
            channels = server_data["channels"]
            # List of channels to remove if their data is None
            channels_to_remove = []
            for channel_id, channel_data in channels.items():
                # If channel data is null, mark it for removal
                if channel_data is None:
                    print(
                        f"Channel {channel_id} has null data. It will be removed.")
                    channels_to_remove.append(channel_id)
                else:
                    func.log.debug(f"Processing channel: {channel_id}")
                    # Only add missing keys, do not overwrite existing values (especially webhook_url)
                    for key, default_value in default_channel_model.items():
                        if key not in channel_data:
                            channel_data[key] = default_value() if callable(default_value) else default_value
                        # For nested config dict, sync keys but do not overwrite existing values
                        if key == "config" and isinstance(channel_data[key], dict):
                            for ckey, cdefault in default_channel_model["config"].items():
                                if ckey not in channel_data["config"]:
                                    channel_data["config"][ckey] = cdefault
                    # Remove extra keys not in the default model
                    for key in list(channel_data.keys()):
                        if key not in default_channel_model:
                            del channel_data[key]
            # Remove channels that had null data
            for channel_id in channels_to_remove:
                del channels[channel_id]
        else:
            func.log.debug(
                f"No channels found for server: {server_id}. Skipping update for this server.")

    # Write the updated session data back to the JSON file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=4, ensure_ascii=False)

    func.log.debug("Session file updated successfully.")


class AutoUpdater:
    def __init__(self, repo_url, current_version, branch="main", is_exe=None):
        """
        Initializes the AutoUpdater.

        :param repo_url: Git repository URL (e.g., git@github.com:username/repo.git)
        :param current_version: Current version of the program (e.g., "1.0.2")
        :param branch: Branch to check for updates (default: "main")
        :param is_exe: Whether the program is running as an executable (auto-detected if None)
        """
        self.repo_url = repo_url
        self.current_version = current_version
        self.branch = branch
        self.is_exe = is_exe if is_exe is not None else self.is_running_as_exe()
        self.repo_owner, self.repo_name = self._extract_repo_info(repo_url)
        self.base_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}"
        self.headers = {'Accept': 'application/vnd.github.v3+json'}
        self.exe_name = "Hashi.exe"
        self.exe_path = Path(sys.executable).resolve() if self.is_exe else None
        self.script_dir = Path(__file__).parent.resolve()

    def check_and_update(self, force=False):
        if os.environ.get("SKIP_AUTOUPDATE") == "1":
            func.log.info(
                "Skipping update check to avoid infinite restart loop.")
            return

        if self.is_exe:
            # NOTA: Forçar uma atualização para .exe é mais complexo, pois precisa da URL do recurso de lançamento.
            # A implementação atual fará o download novamente da versão mais recente, se forçada.
            latest_release = self._get_latest_release()
            is_new_version = latest_release and version.parse(latest_release['tag_name']) > version.parse(self.current_version)

            if force or is_new_version:
                log_msg = "Forcing executable update..." if force else "New executable version detected. Updating..."
                func.log.info(log_msg)
                self._update_exe(latest_release)
            else:
                func.log.info("No executable updates available.")
        else:
            if force:
                func.log.info("Forcing source code update...")
                try:
                    if not (self.script_dir / '.git').exists():
                        func.log.error("Cannot force update: Not a git repository.")
                        return
                    subprocess.run(['git', 'fetch', 'origin', self.branch],
                                   check=True, cwd=self.script_dir, capture_output=True)
                    if self._update_from_commit():
                        func.log.info("Source update applied; restarting program.")
                        self._restart_program()
                except subprocess.CalledProcessError as e:
                    func.log.error(f"Failed to fetch before forced update: {e.stderr.decode().strip() if e.stderr else e}")
                return

            update_available = self._is_source_update_available()
            if update_available:
                func.log.info("New source code version detected. Updating...")
                if self._update_from_commit():
                    func.log.info("Source update applied; restarting program.")
                    self._restart_program()
            else:
                func.log.info("Source code is up to date.")

    def _extract_repo_info(self, repo_url):
        match = re.match(
            r"(?:git@github\.com:|https://github\.com/)([\w-]+)/([\w-]+)(?:\.git)?", repo_url)
        if not match:
            raise ValueError("Invalid repository URL")
        return match.group(1), match.group(2)

    def _get_latest_release(self):
        try:
            response = requests.get(
                f"{self.base_url}/releases/latest", headers=self.headers)
            if response.status_code == 200:
                return response.json()
            else:
                func.log.error(
                    "Failed to fetch latest release: Status code %s", response.status_code)
                return None
        except Exception as e:
            func.log.error("Error fetching release: %s", e)
            return None

    def _update_exe(self, release_data):
        func.log.info("New update found, downloading...")

        new_version = release_data.get('tag_name', self.current_version)
        asset = next((a for a in release_data.get('assets', [])
                     if a.get('name', '').endswith('.exe')), None)

        if asset is None:
            asset = next((a for a in release_data.get('assets', [])
                         if a.get('name', '').endswith('.zip')), None)
            if asset:
                func.log.info(
                    "Zip asset found for update, processing zip file...")
                try:
                    self._download_with_progress(
                        asset['browser_download_url'], new_version, zip_mode=True)
                except Exception as e:
                    func.log.error("Update via zip failed: %s", e)
                return
            else:
                func.log.error(
                    "No suitable asset found for update (neither .exe nor .zip)")
                return
        try:
            self._download_with_progress(
                asset['browser_download_url'], new_version)
        except Exception as e:
            func.log.error("Executable update failed: %s", e)

    def _download_with_progress(self, url, new_version, zip_mode=False):
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0
        temp_exe = self.exe_path.parent / "Hashi_new.exe"

        try:
            with open(temp_exe, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        percent = (downloaded_size / total_size) * 100
                        print(f"Download progress: {percent:.2f}%", end="\r")
        except Exception as e:
            func.log.error("Failed to write new executable: %s", e)
            return

        if not zip_mode:
            self._apply_update(temp_exe, new_version)

    def _apply_update(self, temp_exe, new_version):
        func.log.info("Switching to the latest executable file...")
        version_file = self.exe_path.parent / "version.txt"
        update_script = f"""@echo off
timeout /t 3 /nobreak >nul
del "{self.exe_path}"
move /Y "{temp_exe}" "{self.exe_path}"
echo {new_version} > "{version_file}"
start "" "{self.exe_path}"
exit
"""
        try:
            with open("update.bat", "w", encoding="utf-8") as f:
                f.write(update_script)
            subprocess.Popen(["update.bat"], shell=True,
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
            sys.exit(0)
        except Exception as e:
            func.log.error("Failed to execute update script: %s", e)

    def _is_source_update_available(self):
        try:
            if not (self.script_dir / '.git').exists():
                return False

            # Fetch the latest info from the remote without applying changes
            subprocess.run(['git', 'fetch', 'origin', self.branch],
                           check=True, cwd=self.script_dir, capture_output=True)

            # Get the local commit hash
            local_hash_proc = subprocess.run(
                ['git', 'rev-parse', 'HEAD'], check=True, cwd=self.script_dir, capture_output=True, text=True)
            local_hash = local_hash_proc.stdout.strip()

            # Get the remote commit hash
            remote_hash_proc = subprocess.run(
                ['git', 'rev-parse', f'origin/{self.branch}'], check=True, cwd=self.script_dir, capture_output=True, text=True)
            remote_hash = remote_hash_proc.stdout.strip()

            # Compare hashes
            if local_hash != remote_hash:
                func.log.debug(
                    f"Update available: Local hash {local_hash[:7]} != Remote hash {remote_hash[:7]}")
                return True

            return False
        except subprocess.CalledProcessError as e:
            func.log.error(
                f"Failed to check for source update: {e.stderr.decode().strip() if e.stderr else e}")
            return False
        except Exception as e:
            func.log.error(
                f"An unexpected error occurred while checking for source update: {e}")
            return False

    def _update_from_commit(self):
        try:
            subprocess.run(['git', 'reset', '--hard', f'origin/{self.branch}'],
                           check=True, cwd=self.script_dir, capture_output=True)
            func.log.info("Code updated via Git (branch: %s)", self.branch)
            return True
        except Exception as e:
            func.log.error("Source update failed: %s", e)
            return False

    def _restart_program(self):
        new_env = os.environ.copy()
        new_env["SKIP_AUTOUPDATE"] = "1"
        subprocess.Popen([str(self.exe_path)], env=new_env) if self.is_exe else subprocess.Popen(
            [sys.executable] + sys.argv, env=new_env)
        sys.exit(0)

    @staticmethod
    def is_running_as_exe():
        return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def return_version():
    with open("version.txt", 'r') as file:
        version = file.read().strip()
    return version


def startup_screen():
    os.system("cls" if os.name == "nt" else "clear")
    banner = f"""{Style.BRIGHT}{Fore.WHITE}✦・ﾟ* Hashi 橋 - C.AI to Discord ﾟ・✦
{Fore.YELLOW}▶ {Fore.WHITE}Description: {Fore.WHITE}An AI-powered Discord bot using Character.AI!
{Fore.YELLOW}▶ {Fore.WHITE}Creator: {Fore.WHITE}LixxRarin
{Fore.YELLOW}▶ {Fore.WHITE}GitHub: {Fore.WHITE}https://github.com/LixxRarin/Hashi-CharacterAI-Discord
{Fore.YELLOW}▶ {Fore.WHITE}Version: {Fore.WHITE}{return_version()}
{Style.RESET_ALL}
"""
    print(banner)
    time.sleep(2)


async def boot():
    startup_screen()
    update_session_file()

    # Manage and update the configuration file
    config_manager = ConfigManager()
    await config_manager.check_and_update()

    # Verifica a flag de forçar atualização a partir da linha de comando
    force_update = "--force-update" in sys.argv

    # Initialize AutoUpdater using configuration data
    updater = AutoUpdater(
        repo_url=func.config_yaml["Options"]["repo_url"],
        current_version=return_version(),
        branch=func.config_yaml["Options"].get("repo_branch", "main")
    )
    # Executa a atualização se auto_update estiver ativado ou se for forçado
    if func.config_yaml["Options"].get("auto_update", False) or force_update:
        updater.check_and_update(force=force_update)

asyncio.run(boot())
