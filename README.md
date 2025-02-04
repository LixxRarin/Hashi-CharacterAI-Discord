# Bridge - Character.AI to Discord Servers

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://www.python.org/downloads/)

The Bridge that allows Character.AI personas to interact with users in your Discord server. Perfect for bringing AI personalities to your community!

It is worth noting that this project does not yet have a definitive name TwT...

**Demo Server**: [Join Discord](https://discord.gg/pPSk2g8YX2) | **Report Issues**: [GitHub Issues](https://github.com/LixxRarin/CharacterAI-Discord-Bridge/issues)

<a href="https://ibb.co/kRLnXxq"><img src="https://i.ibb.co/XhnBtbF/Captura-de-tela-2025-02-02-141343.png" alt="Captura-de-tela-2025-02-02-141343" border="0"></a>

## 📌 Contents
- [Features](#-features) 
- [Warnings](#-warnings)
- [Roadmap](#-roadmap)
- [Setup Guide](#-setup-guide)
  - [Prerequisites](#prerequisites)
  - [Discord Bot Creation](#discord-bot-creation)
  - [Installation](#installation)
  - [Configuration](#configuration)
- [Acknowledgments](#-BLESS)
- [License](#-license)

## 🌟 Features
- Real-time interaction between Character.AI personas and Discord users
- Simple YAML configuration
- Customizable
- Cross-platform compatibility (Anything that runs Python and has internet access)

## ⚠️ Warnings
1. **This is beta software** - Expect bugs and report them on our [Discord](#)
2. **Credits required** - You must credit [@LixxRarin](https://github.com/LixxRarin) if modifying/distributing
3. **No security bypass** - Does not interfere with Character.AI safety systems
4. **Non-commercial use** - Strictly for experimental/educational purposes

## 🚧 Roadmap
### Core Improvements
- [ ] Emoji filtering system
- [ ] DM interaction support
- [ ] Multi-language translation
- [ ] Multi-bot instance support

### Discord Features
- [ ] Slash commands for:
  - `/update_bridge` - Update Bridge
  - `/reset` - If something goes wrong
  - `/chatID` - Change the chat ID
  - `/charID` - Change to other character
  - `/config` - Adjust some settings dynamically

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

> You don't need to define a name or profile picture for your bot, Bridge does this automatically! (this is configurable)

### Installation

#### Windows Users
1. Download latest release [here](https://github.com/LixxRarin/CharacterAI-Discord-Bridge/releases)
2. Run `Bridge.exe`
3. `config.yml` will auto-generate

#### Linux/Python Users
```bash
# Install Python 3.11
sudo apt update && sudo apt install python3.11

# Clone repository
git clone https://github.com/yourusername/bridge.git
cd bridge

# Install dependencies
pip install -r requirements.txt

# Launch bridge
python3.11 app.py
```

### Configuration
Edit `config.yml` with these essential values:

```yaml
Discord:
  token: "YOUR_DISCORD_TOKEN" # From developer portal
  channel_bot_chat: [CHANNEL_ID] # Right-click channel → Copy ID

CAI:
  token: "YOUR_CHARACTER_AI_TOKEN"
  character_id: "7OQWCw72T2hHr8JwNIjXd8KpTy663wI_piz4XCHbeZ4" # Neuro-sama example
```
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

## 🔄 Updating
1. **Windows**: Replace executable
2. **Source**: 
```bash
# In the Bridge directory
git pull origin main
pip install -r requirements.txt --upgrade
```
> Don't worry about the 'config.yml' configuration file, it is updated automatically without losing your data.

## 🙏 BLESS
- **[PyCharacterAI](https://github.com/pycharacterai)** team for unofficial API wrapper
- **[Character.AI](https://character.ai/)**

## 📜 License
MIT License - See [LICENSE](LICENSE) for details. 