# grind Discord bot (early WIP)
Grind is a multi-function discord bot mostly focusing on easy to configure server security.

## Features
- Custom prefix per server
- Moderation commands (ban, kick, mute, jail, etc.)
- Logging actions in dedicated channels
- Role-based permissions and fake permissions system
- Command aliasing system
- Temporary voice channels (VoiceMaster system)
- Configurable settings stored in JSON files

## Installation
### Prerequisites
- Python 3.8+
- `discord.py` (`pip install discord.py`)

### Setup
1. Clone the repository:
   ```sh
   git clone https://github.com/kamilkej/repo.git
   cd repo
   ```
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
3. Set up your bot token in `main.py`:
   ```python
   BOT_TOKEN = "your-bot-token-here"
   ```
4. Run the bot:
   ```sh
   python main.py
   ```

## Usage
### Moderation Commands
| Command | Description |
|---------|-------------|
| `!ban <user> [duration] [reason]` | Ban a user |
| `!unban <user_id>` | Unban a user |
| `!kick <user> [reason]` | Kick a user |
| `!mute <user> [duration] [reason]` | Mute a user |
| `!unmute <user>` | Unmute a user |
| `!jail <user> [duration] [reason]` | Jail a user |
| `!unjail <user>` | Unjail a user |

### Configuration Commands
| Command | Description |
|---------|-------------|
| `!setupjail` | Set up jail system |
| `!setupmute` | Set up mute system |
| `!setuplogs` | Set up logging channels |
| `!prefix <set|remove|list> [new_prefix]` | Manage bot prefix |

### VoiceMaster Commands
| Command | Description |
|---------|-------------|
| `!vm` | Create a temporary voice channel |
| `!vm name <name>` | Rename your voice channel |
| `!vm limit <number>` | Set user limit for your channel |
| `!vm lock` | Lock your voice channel |
| `!vm unlock` | Unlock your voice channel |

## License
This project is licensed under the MIT License.


## To Do List
```- cogs (spaghetti code)
- autorole
- antinuke (maybe)
- antiraid (maybe)
- clown/star
- log customization and commands
- cmd answer customization
- snipe
- lockdown
- stripstaff
- ban/mute/kick history
- timeout
- imute/rmute
- vc
- unbanall
- role commands
- purge
 -nuke
- hide/unhide
- slowmode
- restrictcommand
- forcenickname
- boosterrole/boost msg
- FULL SETTINGS SYSTEM
- welcome
- autoresponder
- stickymessage
- imgonly
- word filter
- enable/disable command
- pin
- banner/av etc (server too)
- webhooks
- sticker
- emoji steal/add
- serverinfo/userinfo
- birthday
- timezone
- games (maybe)
- embed configuration
- afk
- poll
- msg reaction
- levels
- giveaways
- help command (actually nice)
```


