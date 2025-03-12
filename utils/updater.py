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

import utils.func as func
from utils.config_updater import ConfigManager

if not os.path.exists("version.txt"):
    with open("version.txt", "w") as file:
        file.write("1.1.0\n")

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
        self.exe_name = "Hashi.exe"
        self.exe_path = Path(sys.executable).resolve() if self.is_exe else None
        self.script_dir = Path(__file__).parent.resolve()

    def check_and_update(self):
        if os.environ.get("SKIP_AUTOUPDATE") == "1":
            func.log.info(
                "Skipping update check to avoid infinite restart loop.")
            return

        if self.is_exe:
            latest_release = self._get_latest_release()
            if latest_release and version.parse(latest_release['tag_name']) > version.parse(self.current_version):
                func.log.info("New executable version detected. Updating...")
                self._update_exe(latest_release)
            else:
                func.log.info("No executable updates available.")
        else:
            if self._update_from_commit():
                func.log.info("Source update applied; restarting program.")
                self._restart_program()

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

    def _update_from_commit(self):
        try:
            if (self.script_dir / '.git').exists():
                subprocess.run(['git', 'fetch', 'origin',
                               self.branch], check=True, cwd=self.script_dir)
                subprocess.run(
                    ['git', 'reset', '--hard', f'origin/{self.branch}'], check=True, cwd=self.script_dir)
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
{Fore.YELLOW}▶ {Fore.WHITE}GitHub: {Fore.WHITE}https://github.com/LixxRarin/CharacterAI-Discord-Bridge
{Fore.YELLOW}▶ {Fore.WHITE}Version: {Fore.WHITE}{return_version()}
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
        repo_url=func.config_yaml["Options"]["repo_url"],
        current_version=return_version(),
        branch=func.config_yaml["Options"].get("repo_branch", "main")
    )

    if func.config_yaml["Options"].get("auto_update", False):
        updater.check_and_update()

asyncio.run(boot())
