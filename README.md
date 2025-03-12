# Project Hashi - 橋
### Character.AI to Discord Servers!

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)  [![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://www.python.org/downloads/)  ![Discord](https://img.shields.io/discord/1288665952099237898?logo=Discord&label=AquairoPallete&link=https%3A%2F%2Fdiscord.gg%2FpPSk2g8YX2)
 
Project Hashi allows Character.AI personas to interact with users in your Discord server. Perfect for bringing AI personalities to your community!

**Demo Server**: [Join Discord](https://discord.gg/pPSk2g8YX2) | **Report Issues**: [GitHub Issues](https://github.com/LixxRarin/Hashi-Character_AI-Discord/issues)

<a href="https://files.catbox.moe/uwwd6m.png"><img src="https://files.catbox.moe/uwwd6m.png" alt="..." border="0"></a>

## 🌟 Add the Bot to Your Server (Experimental)

[Click here to invite the bot](https://discord.com/oauth2/authorize?client_id=1115332091048120481)

> **Note:** At the moment, I don't have a stable server to host the bot, so there may be occasional downtimes and instabilities. Some settings are also unavailable right now. If you'd like, you can host the bot yourself for a smoother experience! :3

## 📌 Contents
- [Features](#-features) 
- [Warnings](#-warnings)
- [Roadmap](#-roadmap)
- [Setup Guide](#-setup-guide)
  - [Prerequisites](#prerequisites)
  - [Discord Bot Creation](#discord-bot-creation)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Setup Bot](#setup-bot)
- [Acknowledgments](#-acknowledgments)
- [License](#-license)

## 🌟 Features
- Real-time interaction between Character.AI personas and Discord users
- Uses webhooks and allows the bot to act as a standalone instance 
- Simple YAML configuration
- Customizable
- Cross-platform compatibility (Anything that runs Python and has internet access)

## ⚠️ Warnings
1. **This is beta software** - Expect bugs and report them on our [Discord](https://discord.gg/pPSk2g8YX2)
2. **Credits required** - You must credit [@LixxRarin](https://github.com/LixxRarin) if modifying/distributing
3. **No security bypass** - Does not interfere with Character.AI safety systems
4. **Non-commercial use** - Strictly for experimental/educational purposes

## 🚧 Roadmap
### Core Improvements
- [x] Emoji filtering system
- [x] Multi-bot instance support
- [ ] DM interaction support
- [ ] Add-ons/Plugins support
- [ ] Support for other AI APIs

### Discord Features
- [X] Slash commands for: (More commands coming soon)
  - `/setup` - configure and create a bot on the channel and character ID
  - `/config` - Configure a specific AI (+15 commands!)
  - `/remove` - Remove a bot from the server 
  - `/character_info` - View character information
  - `/chat_id` - Create a new Character.IA bot chat

## 🛠️ Setup Guide

### Prerequisites
- Discord developer account
- Character.AI account
- Python 3.11+ (for source version)
- Basic text editor (VS Code recommended)

### Discord Bot Creation
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create new application → Build → Bot
3. **Enable Privileged Intents**:
   - Presence Intent
   - Server Members Intent 
   - Message Content Intent
4. Copy bot token (store securely)

### Installation

#### Windows Users
1. Download latest release [here](https://github.com/LixxRarin/Hashi-Character_AI-Discord/releases)
2. Extract and Run `Hashi.exe`
3. `config.yml` will auto-generate

#### Linux/Source Users
```bash
# Install Python 3.11 (Use your Linux system package manager)
sudo apt update && sudo apt install python3.11

# Clone repository
git clone git@github.com:LixxRarin/Hashi-Character_AI-Discord.git
cd hashi

# Install dependencies 
pip install -r requirements.txt

# Launch Hashi
python3.11 app.py
```

### Configuration
Edit `config.yml` with these essential values:

```yaml
Discord:
  token: "YOUR_DISCORD_TOKEN" # From developer portal
Character_AI:
  token: "YOUR_CHARACTER_AI_TOKEN"
```
> The 'config.yaml' file is very well documented, and full of options!

#### Getting Character.AI Token

1. Go to the Character.AI homepage.  
2. Choose a random character.  
3. Enter inspection mode (usually ```F12```).  
4. Go to the "Network" tab.  
5. In the filter, search for ```/chat/character```.  
6. Look for something similar to this (image below).  
7. In Headers, look for "authorization".  
8. Done, your token is right next to it. 

 <a href="https://ibb.co/RkqGHn5q"><img src="https://i.ibb.co/ycrmsT3r/1.png" alt="1" border="0"></a>
<a href="https://ibb.co/yBSwQLNp"><img src="https://i.ibb.co/2YNDkXFS/2.png" alt="2" border="0"></a>

> This requires you to have a computer; I'm not sure if it's possible to do it on mobile devices.  
Never share your token with anyone!!!

#### Getting Character IDs
1. Navigate to character's chat page:
 ```
   https://character.ai/chat/CHARACTER_ID_HERE
   ```
2. Copy everything after last slash

#### Setup Bot
1. Use ```/setup``` on your Discord server, and fill in the Channel and Character ID fields. 

> The Channel field will be the channel where the Character.AI AI will receive and send messages.

> You don't need to define a name or profile picture for your bot, Hashi does this automatically! (this is configurable)

## 🔄 Updating

> The program updates itself, but if you need to, you can do it manually

1. **Windows**: Replace executable 
2. **Source**: 
```bash
# In the Hashi directory
git pull origin main
pip install -r requirements.txt --upgrade
```
> Don't worry about the 'config.yml' configuration file, it is updated automatically without losing your data.

## 🙏 Acknowledgments
- **[KarstSkarn](https://github.com/KarstSkarn)** for inspiration from [ChAIScrapper](https://github.com/KarstSkarn/ChAIScrapper)
- **[PyCharacterAI](https://github.com/pycharacterai)** team for unofficial API wrapper
- **[Character.AI](https://character.ai/)**

## 📜 License
MIT License - See [LICENSE](LICENSE) for details. 
