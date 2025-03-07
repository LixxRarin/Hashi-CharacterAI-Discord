import os
import re
import sys
import time
import zipfile
import asyncio
import subprocess
from io import BytesIO
from pathlib import Path

import requests
from colorama import Fore, init, Style
from packaging import version

import utils
from config_updater import ConfigManager

if not os.path.exists("version.txt"):
    with open("version.txt", "w") as file:
        file.write("1.0.8\n")

if not os.path.exists("cache.json"):
    with open("cache.json", "w") as file:
        file.write("{}")

# Initialize colorama for cross-platform colored output
init(autoreset=True)


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
        self.exe_path = Path(sys.executable).resolve() if self.is_exe else None
        self.script_dir = Path(__file__).parent.resolve()

    def check_and_update(self):
        if os.environ.get("SKIP_AUTOUPDATE") == "1":
            utils.log.info(
                "Skipping update check to avoid infinite restart loop.")
            return

        if self.is_exe:
            latest_release = self._get_latest_release()
            if latest_release and version.parse(latest_release['tag_name']) > version.parse(self.current_version):
                utils.log.info("New executable version detected. Updating...")
                self._update_exe(latest_release)
            else:
                utils.log.info("No executable updates available.")
        else:
            if self._update_from_commit():
                utils.log.info("Source update applied; restarting program.")
                self._restart_program()

    def _extract_repo_info(self, repo_url):
        match = re.match(
            r"(?:git@github\.com:|https:\/\/github\.com\/)([\w-]+)/([\w-]+)(?:\.git)?", repo_url)
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
                utils.log.error(
                    "Failed to fetch latest release: Status code %s", response.status_code)
                return None
        except Exception as e:
            utils.log.error("Error fetching release: %s", e)
            return None

    def _update_exe(self, release_data):
        utils.log.info("New update found, downloading...")

        new_version = release_data.get('tag_name', self.current_version)
        # Try to find an .exe asset first
        asset = next((a for a in release_data.get('assets', [])
                     if a.get('name', '').endswith('.exe')), None)
        if asset is None:
            # If no .exe asset, try to find a .zip asset
            asset = next((a for a in release_data.get('assets', [])
                         if a.get('name', '').endswith('.zip')), None)
            if asset:
                utils.log.info(
                    "Zip asset found for update, processing zip file...")
                try:
                    download_url = asset['browser_download_url']
                    zip_content = requests.get(download_url).content
                    zip_file = zipfile.ZipFile(BytesIO(zip_content))
                    exe_filename = None
                    for file in zip_file.namelist():
                        if file.endswith('.exe'):
                            exe_filename = file
                            break
                    if exe_filename is None:
                        utils.log.error(
                            "No .exe file found in the zip archive.")
                        return
                    new_exe_content = zip_file.read(exe_filename)
                    self._apply_update(new_exe_content, new_version)
                except Exception as e:
                    utils.log.error("Update via zip failed: %s", e)
                return
            else:
                utils.log.error(
                    "No suitable asset found for update (neither .exe nor .zip)")
                return
        try:
            download_url = asset['browser_download_url']
            new_exe_content = requests.get(download_url).content
            self._apply_update(new_exe_content, new_version)
        except Exception as e:
            utils.log.error("Executable update failed: %s", e)

    def _apply_update(self, new_exe_content, new_version):
        """
        Saves the new executable content to a temporary file and creates an update batch script
        that replaces the current executable with the new one and updates version.txt.
        """
        utils.log.info("Switching to the latest executable file...")
        temp_exe = self.exe_path.parent / "Bridge_new.exe"
        try:
            with open(temp_exe, "wb") as f:
                f.write(new_exe_content)
        except Exception as e:
            utils.log.error("Failed to write temporary executable file: %s", e)
            return

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
            # Launch update.bat in a new console window
            subprocess.Popen(["update.bat"], shell=True,
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
            sys.exit(0)
        except Exception as e:
            utils.log.error("Failed to execute update script: %s", e)

    def _update_from_commit(self):
        try:
            if (self.script_dir / '.git').exists():
                status = subprocess.run(
                    ['git', 'status', '--porcelain'], capture_output=True, text=True, cwd=self.script_dir)
                if status.stdout.strip():
                    utils.log.warning(
                        "There are uncommitted local changes. Consider committing or discarding them.")
                subprocess.run(['git', 'fetch', 'origin',
                               self.branch], check=True, cwd=self.script_dir)
                subprocess.run(
                    ['git', 'reset', '--hard', f'origin/{self.branch}'], check=True, cwd=self.script_dir)
                utils.log.info(
                    "Code updated via Git (branch: %s)", self.branch)
                return True
            else:
                from selfupdate import update
                update()
                utils.log.info("Code updated via selfupdate library.")
                return True
        except Exception as e:
            utils.log.error("Source update failed: %s", e)
            return False

    def _restart_program(self):
        new_env = os.environ.copy()
        new_env["SKIP_AUTOUPDATE"] = "1"
        if self.is_exe:
            subprocess.Popen([str(self.exe_path)], env=new_env)
        else:
            subprocess.Popen([sys.executable] + sys.argv, env=new_env)
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
    banner = f"""
{Fore.CYAN}{Style.BRIGHT}{Fore.WHITE}------- C.AI to Discord ~ Bridge -------
{Fore.YELLOW}Description: {Fore.WHITE}An AI-powered Discord bot using Character.AI! :3
{Fore.YELLOW}Creator: {Fore.WHITE}LixxRarin
{Fore.YELLOW}GitHub: {Fore.WHITE}https://github.com/LixxRarin/CharacterAI-Discord-Bridge
{Fore.YELLOW}Version: {Fore.WHITE}{return_version()}
{Style.RESET_ALL}
"""
    print(banner)
    time.sleep(2)


async def boot():
    startup_screen()

    # Manage and update the configuration file
    config_manager = ConfigManager()
    await config_manager.check_and_update()

    # Initialize AutoUpdater using configuration data
    updater = AutoUpdater(
        repo_url=utils.config_yaml["Options"]["repo_url"],
        current_version=return_version(),
        branch=utils.config_yaml["Options"].get("repo_branch", "main")
    )

    if utils.config_yaml["Options"].get("auto_update", False):
        updater.check_and_update()

asyncio.run(boot())
