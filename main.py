import discord
from discord.ext import commands
import asyncio
import datetime
import json
import os
import sys

DEFAULT_PREFIX = '!'
OWNER_ID = 0
BOT_TOKEN = 'x'

def load_server_config(server_id):
    server_id = str(server_id)
    try:
        with open(f'server_data/{server_id}.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        default_config = {
            'prefix': DEFAULT_PREFIX,
            'jail': {},
            'mute': {},
            'fake_permissions': {},
            'aliases': {},
            'logs_channel_id': None,
            'jail_logs_channel_id': None
        }
        save_server_config(server_id, default_config)
        return default_config

def save_server_config(server_id, config):
    server_id = str(server_id)
    os.makedirs('server_data', exist_ok=True)
    with open(f'server_data/{server_id}.json', 'w') as f:
        json.dump(config, f, indent=4)

def load_bot_config():
    try:
        with open('bot_config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        default_config = {
            'whitelisted_servers': []
        }
        save_bot_config(default_config)
        return default_config
    
def save_bot_config(config):
    with open('bot_config.json', 'w') as f:
        json.dump(config, f, indent=4)


def get_prefix(bot, message):
    if not message.guild:
        return DEFAULT_PREFIX
    
    server_id = str(message.guild.id)
    config = load_server_config(server_id)
    return config.get('prefix', DEFAULT_PREFIX)


intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=get_prefix, intents=intents)
bot.remove_command("help") 

async def is_server_whitelisted(guild):
    bot_config = load_bot_config()
    whitelisted_servers = bot_config.get('whitelisted_servers', [])
    return str(guild.id) in whitelisted_servers or not whitelisted_servers

def parse_duration(duration_str):
    if duration_str.lower() == 'infinite':
        return None
    
    unit = duration_str[-1].lower()
    try:
        amount = int(duration_str[:-1])
    except ValueError:
        return None
    
    if unit == 'm':
        return datetime.timedelta(minutes=amount)
    elif unit == 'h':
        return datetime.timedelta(hours=amount)
    elif unit == 'd':
        return datetime.timedelta(days=amount)
    elif unit == 'y':
        return datetime.timedelta(days=amount*365)
    
    return None

def check_role_hierarchy(ctx, target_member):
    bot_member = ctx.guild.get_member(bot.user.id)
    bot_highest_role = bot_member.top_role

    if bot_highest_role.position <= target_member.top_role.position:
        return False, "Bot's role is too low to perform this action. Please move the bot's role higher in the server hierarchy."

    if ctx.author.top_role.position <= target_member.top_role.position:
        return False, "You cannot moderate a member with an equal or higher role than yours."

    return True, ""

def save_user_roles(member):
    server_id = str(member.guild.id)
    config = load_server_config(server_id)
    
    if 'user_roles' not in config:
        config['user_roles'] = {}
    
    roles_to_save = [role.id for role in member.roles if role != member.guild.default_role]
    config['user_roles'][str(member.id)] = roles_to_save
    
    save_server_config(server_id, config)

def restore_user_roles(member):
    server_id = str(member.guild.id)
    config = load_server_config(server_id)
    
    if 'user_roles' not in config or str(member.id) not in config['user_roles']:
        return []
    
    role_ids = config['user_roles'][str(member.id)]
    roles = [member.guild.get_role(role_id) for role_id in role_ids if member.guild.get_role(role_id)]
    
    del config['user_roles'][str(member.id)]
    save_server_config(server_id, config)
    
    return [role for role in roles if role is not None]

def custom_check_permissions(ctx):
    if not hasattr(ctx.command, 'requires_permissions'):
        return True
    
    required_perm = ctx.command.requires_permissions
    
    permission_map = {
        'ban_members': 'ban_members',
        'kick_members': 'kick_members',
        'manage_messages': 'manage_messages',
        'manage_roles': 'manage_roles',
        'manage_channels': 'manage_channels',
        'administrator': 'administrator',
        'manage_guild': 'manage_guild',
        'manage_nicknames': 'manage_nicknames'
    }
    
    discord_perm_attr = permission_map.get(required_perm)
    if discord_perm_attr and getattr(ctx.author.guild_permissions, discord_perm_attr, False):
        return True
    
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    fake_perms = config.get('fake_permissions', {})
    
    for role in ctx.author.roles:
        role_id = str(role.id)
        if role_id in fake_perms and required_perm in fake_perms.get(role_id, []):
            return True
    
    return False

def requires_permission(permission):
    def decorator(func):
        func.requires_permissions = permission
        return func
    return decorator

async def log_action(guild, action_type, member, moderator, reason=None, duration=None, log_type="general"):
    server_id = str(guild.id)
    config = load_server_config(server_id)
    
    channel_id = None
    if log_type == "jail":
        channel_id = config.get('jail_logs_channel_id')
    else:
        channel_id = config.get('logs_channel_id')
    
    if not channel_id:
        return
    
    channel = guild.get_channel(channel_id)
    if not channel:
        return
    
    colors = {
        'ban': discord.Color.dark_red(),
        'unban': discord.Color.green(),
        'kick': discord.Color.orange(),
        'mute': discord.Color.gold(),
        'unmute': discord.Color.green(),
        'jail': discord.Color.red(),
        'unjail': discord.Color.green(),
        'warning': discord.Color.yellow()
    }
    
    color = colors.get(action_type.lower(), discord.Color.blue())
    
    embed = discord.Embed(
        title=f"🛡️ Moderation Action: {action_type.capitalize()}",
        color=color,
        timestamp=datetime.datetime.now()
    )
    
    embed.add_field(name="User", value=member.mention if hasattr(member, "mention") else member, inline=False)
    embed.add_field(name="Moderator", value=moderator.mention, inline=False)
    
    if duration:
        embed.add_field(name="Duration", value=duration, inline=False)
    
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Error logging action: {e}")

def is_owner():
    async def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

async def process_command_aliases(ctx, command_name):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    aliases = config.get('aliases', {})
    
    if command_name in aliases:
        real_command = aliases.get(command_name)
        command = bot.get_command(real_command)
        
        if command:
            content = ctx.message.content
            parts = content.split(' ', 1)
            
            if len(parts) > 1:
                new_content = f"{ctx.prefix}{real_command} {parts[1]}"
            else:
                new_content = f"{ctx.prefix}{real_command}"
            
            ctx.message.content = new_content
            await bot.process_commands(ctx.message)
            return True
    
    return False

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print(f'Bot ID: {bot.user.id}')
    print('------')
    
    os.makedirs('server_data', exist_ok=True)
    
    await bot.change_presence(activity=discord.Game(name=f"kam my beloved"))

@bot.event
async def on_guild_join(guild):
    if not await is_server_whitelisted(guild):
        print(f"Leaving non-whitelisted server: {guild.name} ({guild.id})")
        try:
            await guild.owner.send(f"Bot is only allowed in whitelisted servers. Contact @6969969696969969696969")
        except:
            pass
        await guild.leave()
        return
    
    print(f"Joined new guild: {guild.name} ({guild.id})")
    
    load_server_config(guild.id)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if not message.guild:
        await bot.process_commands(message)
        return
    
    if not await is_server_whitelisted(message.guild):
        return
    
    prefix = get_prefix(bot, message)
    
    if not message.content.startswith(prefix):
        return
    
    command_name = message.content[len(prefix):].split(' ')[0]
    
    is_alias = await process_command_aliases(await bot.get_context(message), command_name)
    
    if not is_alias:
        await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        if hasattr(ctx.command, 'requires_permissions'):
            await ctx.send("You don't have permission to use this command.")
        else:
            await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Please check the command syntax.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Unexpected error: {error}")
        await ctx.send("An unexpected error occurred.")

@bot.command(name="help", aliases=["commands", "h"])
async def help_command(ctx):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    prefix = config.get('prefix', DEFAULT_PREFIX)
    
    embed = discord.Embed(
        title="Bot Commands",
        description=f"Prefix: `{prefix}`",
        color=discord.Color.blue()
    )
    
    mod_commands = [
        f"`{prefix}ban <user> [duration] [reason]` - Ban a user",
        f"`{prefix}unban <user_id>` - Unban a user",
        f"`{prefix}kick <user> [reason]` - Kick a user",
        f"`{prefix}mute <user> [duration] [reason]` - Mute a user",
        f"`{prefix}unmute <user>` - Unmute a user",
        f"`{prefix}jail <user> [duration] [reason]` - Jail a user",
        f"`{prefix}unjail <user>` - Unjail a user"
    ]
    embed.add_field(name="Moderation", value="\n".join(mod_commands), inline=False)
    
    setup_commands = [
        f"`{prefix}setupjail` - Set up jail system",
        f"`{prefix}setupmute` - Set up mute system",
        f"`{prefix}setuplogs` - Set up logging channels",
        f"`{prefix}prefix <set|remove|list> [new_prefix]` - Manage bot prefix"
    ]
    embed.add_field(name="Setup", value="\n".join(setup_commands), inline=False)
    
    alias_commands = [
        f"`{prefix}alias add <name> <command>` - Add a command alias",
        f"`{prefix}alias remove <name>` - Remove an alias",
        f"`{prefix}alias list` - List all aliases",
        f"`{prefix}alias removeall` - Remove all aliases"
    ]
    embed.add_field(name="Aliases", value="\n".join(alias_commands), inline=False)
    
    vm_commands = [
        f"`{prefix}vm` - Create a temporary voice channel",
        f"`{prefix}vm name <name>` - Rename your voice channel",
        f"`{prefix}vm limit <number>` - Set user limit for your channel",
        f"`{prefix}vm lock` - Lock your voice channel",
        f"`{prefix}vm unlock` - Unlock your voice channel"
    ]
    embed.add_field(name="VoiceMaster", value="\n".join(vm_commands), inline=False)
    
    server_aliases = config.get('aliases', {})
    if server_aliases:
        alias_list = [f"`{prefix}{alias}` → `{prefix}{command}`" for alias, command in server_aliases.items()]
        embed.add_field(name="Server Aliases", value="\n".join(alias_list), inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="setuplogs", aliases=["logsetup"])
@commands.has_permissions(administrator=True)
async def setup_logs(ctx):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    try:
        logs_channel = await ctx.guild.create_text_channel('logs', 
                                                        overwrites={
                                                            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)
                                                        })
        
        jail_logs_channel = None
        if 'jail_logs_channel_id' not in config or not ctx.guild.get_channel(config['jail_logs_channel_id']):
            jail_logs_channel = await ctx.guild.create_text_channel('jail-logs', 
                                                                overwrites={
                                                                    ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)
                                                                })
        
        config['logs_channel_id'] = logs_channel.id
        if jail_logs_channel:
            config['jail_logs_channel_id'] = jail_logs_channel.id
        
        save_server_config(server_id, config)
        
        await ctx.send(f"Logging channels have been set up at <#{logs_channel.id}>")
    
    except discord.Forbidden:
        await ctx.send("I don't have permission to create channels/Manage roles. Move the bot role up or check permissions.")
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

@bot.command(name="setupjail", aliases=["jailsetup", "prison"])
@commands.has_permissions(administrator=True)
async def setupjail(ctx):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'jail' in config and config['jail'].get('jailed_role_id') and ctx.guild.get_role(config['jail'].get('jailed_role_id')):
        await ctx.send('Jail system is already set up for this server.')
        return
    
    try:
        jailed_role = await ctx.guild.create_role(name='Jailed', reason='Jail system setup')
        
        jail_channel = await ctx.guild.create_text_channel('jail', 
                                                        overwrites={
                                                            jailed_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                                                            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)
                                                        })
        
        jail_logs_channel = None
        if 'jail_logs_channel_id' in config and ctx.guild.get_channel(config['jail_logs_channel_id']):
            jail_logs_channel = ctx.guild.get_channel(config['jail_logs_channel_id'])
        else:
            jail_logs_channel = await ctx.guild.create_text_channel('jail-logs', 
                                                                overwrites={
                                                                    ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)
                                                                })
        
        for channel in ctx.guild.channels:
            if channel in [jail_channel, jail_logs_channel]:
                continue
            
            overwrites = channel.overwrites.copy()
            
            overwrites[jailed_role] = discord.PermissionOverwrite(
                view_channel=False,
                send_messages=False,
                read_messages=False,
                add_reactions=False
            )
            
            await channel.edit(overwrites=overwrites)
        
        if 'jail' not in config:
            config['jail'] = {}
        
        config['jail']['jailed_role_id'] = jailed_role.id
        config['jail']['jail_channel_id'] = jail_channel.id
        config['jail_logs_channel_id'] = jail_logs_channel.id
        
        save_server_config(server_id, config)
        
        await ctx.send(f'Jail system has been set up at <#{jail_logs_channel.id}>')
    
    except discord.Forbidden:
        await ctx.send("I don't have permission to create channels/Manage roles. Move the bot role up or check permissions.")
    except Exception as e:
        await ctx.send(f'An error occurred: {str(e)}')

@bot.command(name="setupmute", aliases=["mutesetup"])
@commands.has_permissions(administrator=True)
async def setupmute(ctx):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'mute' in config and config['mute'].get('muted_role_id') and ctx.guild.get_role(config['mute'].get('muted_role_id')):
        await ctx.send('Mute system is already set up for this server.')
        return
    
    try:
        muted_role = await ctx.guild.create_role(name='Muted', reason='Mute system setup')
        
        for channel in ctx.guild.channels:
            overwrites = channel.overwrites.copy()
            
            overwrites[muted_role] = discord.PermissionOverwrite(
                send_messages=False,
                add_reactions=False
            )
            
            await channel.edit(overwrites=overwrites)
        
        if 'mute' not in config:
            config['mute'] = {}
        
        config['mute']['muted_role_id'] = muted_role.id
        
        save_server_config(server_id, config)
        
        await ctx.send('Mute system has been set up')
    
    except discord.Forbidden:
        await ctx.send("I don't have permission to create channels/Manage roles. Move the bot role up or check permissions.")
    except Exception as e:
        await ctx.send(f'An error occurred: {str(e)}')

@bot.command(name="ban", aliases=["banish", "begone"])
@requires_permission('ban_members')
async def ban(ctx, member: discord.Member, duration='infinite', *, reason='No reason provided'):
    can_moderate, error_message = check_role_hierarchy(ctx, member)
    if not can_moderate:
        await ctx.send(error_message)
        return

    try:
        await member.ban(reason=reason)
        await ctx.send(f'{member} has been banned.')
        
        await log_action(ctx.guild, "ban", member, ctx.author, reason, duration)
        
        duration_delta = parse_duration(duration)
        if duration_delta:
            await asyncio.sleep(duration_delta.total_seconds())
            await ctx.guild.unban(member)
            
            await log_action(ctx.guild, "unban", member, ctx.author, f"Temporary ban expired ({duration})")
    except discord.Forbidden:
        await ctx.send("I don't have permission to ban members. Move the bot role up or check permissions.")

@bot.command(name="unban", aliases=["pardon"])
@requires_permission('ban_members')
async def unban(ctx, member_id: int):
    try:
        user = await bot.fetch_user(member_id)
        await ctx.guild.unban(user)
        await ctx.send(f'{user} has been unbanned')
        
        await log_action(ctx.guild, "unban", user, ctx.author)
    except discord.NotFound:
        await ctx.send('User not found')
    except discord.Forbidden:
        await ctx.send('I do not have permission to unban this user. Move the bot role up or check permissions.')

@bot.command(name="kick", aliases=["boot"])
@requires_permission('kick_members')
async def kick(ctx, member: discord.Member, *, reason='No reason provided'):
    can_moderate, error_message = check_role_hierarchy(ctx, member)
    if not can_moderate:
        await ctx.send(error_message)
        return

    try:
        await member.kick(reason=reason)
        await ctx.send(f'{member} has been kicked.')
        
        await log_action(ctx.guild, "kick", member, ctx.author, reason)
    except discord.Forbidden:
        await ctx.send("I don't have permission to kick members. Move the bot role up or check permissions.")

@bot.command(name="mute", aliases=["silence", "quiet"])
@requires_permission('manage_messages')
async def mute(ctx, member: discord.Member, duration='infinite', *, reason='No reason provided'):
    can_moderate, error_message = check_role_hierarchy(ctx, member)
    if not can_moderate:
        await ctx.send(error_message)
        return

    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'mute' not in config or not config['mute'].get('muted_role_id'):
        await ctx.send('Mute system not set up. Please run !setupmute first.')
        return
    
    muted_role = ctx.guild.get_role(config['mute']['muted_role_id'])
    
    if not muted_role:
        await ctx.send('Mute configuration is invalid. Please run !setupmute again.')
        return
    
    await member.add_roles(muted_role)
    
    await ctx.send(f'{member} has been muted for {duration}. Reason: {reason}')
    
    await log_action(ctx.guild, "mute", member, ctx.author, reason, duration)
    
    duration_delta = parse_duration(duration)
    if duration_delta:
        await asyncio.sleep(duration_delta.total_seconds())
        if muted_role in member.roles:
            await member.remove_roles(muted_role)
            
            await log_action(ctx.guild, "unmute", member, bot.user, f"Temporary mute expired ({duration})")

@bot.command(name="unmute", aliases=["unsilence"])
@requires_permission('manage_messages')
async def unmute(ctx, member: discord.Member):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)

    if 'mute' not in config or not config['mute'].get('muted_role_id'):
        await ctx.send('Mute system not set up. Please run !setupmute first.')
        return
    
    muted_role = ctx.guild.get_role(config['mute']['muted_role_id'])
    
    if not muted_role:
        await ctx.send('Mute configuration is invalid. Please run !setupmute again.')
        return
    
    if muted_role in member.roles:
        await member.remove_roles(muted_role)
        await ctx.send(f'{member} has been unmuted.')
        
        await log_action(ctx.guild, "unmute", member, ctx.author)
    else:
        await ctx.send(f'{member} is not muted.')

@bot.command(name="jail", aliases=["imprison", "detain"])
@requires_permission('manage_messages')
async def jail(ctx, member: discord.Member, duration='infinite', *, reason='No reason provided'):
    can_moderate, error_message = check_role_hierarchy(ctx, member)
    if not can_moderate:
        await ctx.send(error_message)
        return

    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'jail' not in config or not config['jail'].get('jailed_role_id'):
        await ctx.send('Jail system not set up. Please run !setupjail first.')
        return
    
    jailed_role = ctx.guild.get_role(config['jail']['jailed_role_id'])
    jail_channel = ctx.guild.get_channel(config['jail']['jail_channel_id'])
    
    if not jailed_role or not jail_channel:
        await ctx.send('Jail configuration is invalid. Please run !setupjail again.')
        return
    
    save_user_roles(member)
    
    await member.edit(roles=[ctx.guild.default_role])
    await member.add_roles(jailed_role)
    
    embed = discord.Embed(
        title="🔒 Jailed",
        description=f"**Reason:** {reason}",
        color=discord.Color.red()
    )
    embed.add_field(name="Jailed By", value=ctx.author.mention, inline=True)
    
    if duration != 'infinite':
        embed.add_field(name="Duration", value=duration, inline=True)
    
    await jail_channel.send(f"{member.mention} has been jailed.", embed=embed)
    
    await log_action(ctx.guild, "jail", member, ctx.author, reason, duration, "jail")
    
    await ctx.send(f'{member} has been jailed for {duration}.')
    
    duration_delta = parse_duration(duration)
    if duration_delta:
        await asyncio.sleep(duration_delta.total_seconds())
        if jailed_role in member.roles:
            await unjail(ctx, member, auto=True, duration=duration)


@bot.command(name="unjail", aliases=["free", "release"])
@requires_permission('manage_messages')
async def unjail(ctx, member: discord.Member, auto=False, duration=None):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'jail' not in config or not config['jail'].get('jailed_role_id'):
        await ctx.send('Jail system not set up. Please run !setupjail first.')
        return
    
    jailed_role = ctx.guild.get_role(config['jail']['jailed_role_id'])
    jail_channel = ctx.guild.get_channel(config['jail']['jail_channel_id'])
    
    if not jailed_role or not jail_channel:
        await ctx.send('Jail configuration is invalid. Please run !setupjail again.')
        return
    
    if jailed_role in member.roles:
        await member.remove_roles(jailed_role)
        

        previous_roles = restore_user_roles(member)
        if previous_roles:
            await member.add_roles(*previous_roles)
        
        reason = f"Temporary jail expired ({duration})" if auto else None
        await log_action(ctx.guild, "unjail", member, ctx.author if not auto else bot.user, reason, log_type="jail")
        if not auto:
            await ctx.send(f'{member} has been unjailed.')
    else:
        if not auto:
            await ctx.send(f'{member} is not jailed.')

@bot.command(name="prefix", aliases=["setprefix", "changeprefix"])
@commands.has_permissions(administrator=True)
async def change_prefix(ctx, action=None, new_prefix=None):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    current_prefix = config.get('prefix', DEFAULT_PREFIX)
    
    if action == 'set':
        if not new_prefix:
            await ctx.send('Please provide a new prefix. !prefix set <new_prefix>')
            return
        
        config['prefix'] = new_prefix
        save_server_config(server_id, config)
        
        await ctx.send(f'Prefix changed to: {new_prefix}')
    
    elif action == 'remove':
        config['prefix'] = DEFAULT_PREFIX
        save_server_config(server_id, config)
        await ctx.send(f'Prefix reset to default: {DEFAULT_PREFIX}')
    
    elif action == 'list':
        await ctx.send(f'Current prefix: {current_prefix}')
    
    else:
        await ctx.send(f'Usage:\n{current_prefix}prefix set <new_prefix>\n{current_prefix}prefix remove\n{current_prefix}prefix list')

@bot.command(name="fp", aliases=["fakepermissions", "fakeperm"])
@commands.has_permissions(administrator=True)
async def fake_permissions(ctx, action=None, role: discord.Role = None, permission=None):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'fake_permissions' not in config:
        config['fake_permissions'] = {}
    
    fake_perms = config['fake_permissions']
    
    if action not in ['grant', 'remove', 'list']:
        await ctx.send('Usage:\n!fp grant <role> <permission>\n!fp remove <role> <permission>\n!fp list')
        return
    
    if action == 'list':
        if not fake_perms:
            await ctx.send('No fake permissions set.')
            return
        
        response = "Current Fake Permissions:\n"
        for role_id, perms in fake_perms.items():
            role = ctx.guild.get_role(int(role_id))
            role_name = role.name if role else f"Role ID: {role_id}"
            response += f"{role_name}: {', '.join(perms)}\n"
        
        await ctx.send(response)
        return
    
    if not role:
        await ctx.send('Please mention a valid role.')
        return
    
    role_id = str(role.id)
    
    valid_permissions = [
        'administrator', 'manage_guild', 'manage_roles', 'manage_channels', 
        'kick_members', 'ban_members', 'manage_messages', 'manage_nicknames'
    ]
    
    if action == 'grant':
        if not permission or permission not in valid_permissions:
            await ctx.send(f'Invalid permission. Valid permissions are:\n{", ".join(valid_permissions)}')
            return
        
        if role_id not in fake_perms:
            fake_perms[role_id] = []
        
        if permission not in fake_perms[role_id]:
            fake_perms[role_id].append(permission)
        
        save_server_config(server_id, config)
        await ctx.send(f'Granted {permission} to {role.name}')
    
    elif action == 'remove':
        if role_id in fake_perms:
            if permission:
                if permission in fake_perms[role_id]:
                    fake_perms[role_id].remove(permission)
                    await ctx.send(f'Removed {permission} from {role.name}')
                else:
                    await ctx.send(f'Permission {permission} not found for this role.')
            else:
                del fake_perms[role_id]
                await ctx.send(f'Removed all fake permissions for {role.name}')
            
            save_server_config(server_id, config)
        else:
            await ctx.send('No fake permissions found for this role.')

@bot.command(name="alias")
@commands.has_permissions(administrator=True)
async def alias_command(ctx, action=None, alias_name=None, command_name=None):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'aliases' not in config:
        config['aliases'] = {}
    
    aliases = config['aliases']
    
    if action == 'add':
        if not alias_name or not command_name:
            await ctx.send('Please provide both alias name and command. !alias add <alias_name> <command_name>')
            return
        
        real_command = bot.get_command(command_name)
        if not real_command:
            await ctx.send(f'Command {command_name} does not exist.')
            return
        
        aliases[alias_name] = command_name
        save_server_config(server_id, config)
        await ctx.send(f'Added alias: {alias_name} → {command_name}')
    
    elif action == 'remove':
        if not alias_name:
            await ctx.send('Please provide an alias name to remove. !alias remove <alias_name>')
            return
        
        if alias_name in aliases:
            del aliases[alias_name]
            save_server_config(server_id, config)
            await ctx.send(f'Removed alias: {alias_name}')
        else:
            await ctx.send(f'Alias {alias_name} not found.')
    
    elif action == 'list':
        if not aliases:
            await ctx.send('No aliases configured for this server.')
            return
        
        prefix = config.get('prefix', DEFAULT_PREFIX)
        alias_list = [f'`{prefix}{alias}` → `{prefix}{command}`' for alias, command in aliases.items()]
        await ctx.send("Server Aliases:\n" + "\n".join(alias_list))
    
    elif action == 'removeall':
        if not aliases:
            await ctx.send('No aliases to remove.')
            return
        
        config['aliases'] = {}
        save_server_config(server_id, config)
        await ctx.send('All aliases have been removed.')
    
    else:
        await ctx.send('Usage:\n!alias add <alias_name> <command_name>\n!alias remove <alias_name>\n!alias list\n!alias removeall')

# OWNER ONLY (CHANGE OWNER_ID)
@bot.command(name="whitelist")
@is_owner()
async def whitelist(ctx, action=None, server_id=None):
    bot_config = load_bot_config()
    
    if 'whitelisted_servers' not in bot_config:
        bot_config['whitelisted_servers'] = []
    
    if action == 'add':
        if not server_id:
            await ctx.send('Please provide a server ID to whitelist.')
            return
        
        if server_id not in bot_config['whitelisted_servers']:
            bot_config['whitelisted_servers'].append(server_id)
            save_bot_config(bot_config)
            await ctx.send(f'Server {server_id} has been whitelisted.')
        else:
            await ctx.send(f'Server {server_id} is already whitelisted.')
    
    elif action == 'remove':
        if not server_id:
            await ctx.send('Please provide a server ID to remove from whitelist.')
            return
        
        if server_id in bot_config['whitelisted_servers']:
            bot_config['whitelisted_servers'].remove(server_id)
            save_bot_config(bot_config)
            await ctx.send(f'Server {server_id} has been removed from the whitelist.')
        else:
            await ctx.send(f'Server {server_id} is not whitelisted.')
    
    elif action == 'list':
        if not bot_config['whitelisted_servers']:
            await ctx.send('No servers are whitelisted.')
            return
        
        await ctx.send("Whitelisted Servers:\n" + "\n".join(bot_config['whitelisted_servers']))
    
    elif action == 'clear':
        bot_config['whitelisted_servers'] = []
        save_bot_config(bot_config)
        await ctx.send('Server whitelist has been cleared.')
    
    else:
        await ctx.send('Usage:\n!whitelist add <server_id>\n!whitelist remove <server_id>\n!whitelist list\n!whitelist clear')

@bot.command(name="vm", aliases=["voicemaster", "voice"])
async def voicemaster(ctx, action=None, *, value=None):
    if action == "setup" and ctx.author.guild_permissions.administrator:
        await setup_voicemaster(ctx)
        return
    
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'voice_master' not in config or not config['voice_master'].get('enabled', False):
        await ctx.send('VoiceMaster not set up. Please ask an administrator to run `!vm setup`.')
        return
    
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send('You need to be in a voice channel to use VoiceMaster commands.')
        return
    
    user_channel = ctx.author.voice.channel
    
    if not is_user_channel(ctx, user_channel):
        if not action:
            await create_voice_channel(ctx)
            return
        await ctx.send('You need to be in your temporary voice channel to modify it.')
        return
    
    if not action:
        await ctx.send('You already have a temporary voice channel. Use `!vm help` to see available commands.')
        return
    
    if action == "name":
        if not value:
            await ctx.send('Please provide a new name for your channel. Usage: !vm name <new_name>')
            return
        
        await user_channel.edit(name=value)
        await ctx.send(f'Channel renamed to: {value}')
    
    elif action == "limit":
        try:
            limit = int(value) if value else 0
            if limit < 0:
                limit = 0
                
            await user_channel.edit(user_limit=limit)
            limit_msg = "removed" if limit == 0 else f"set to {limit} users"
            await ctx.send(f'User limit {limit_msg}.')
        except ValueError:
            await ctx.send('Please provide a valid number for the user limit.')
    
    elif action == "lock":
        overwrites = user_channel.overwrites.copy()
        overwrites[ctx.guild.default_role] = discord.PermissionOverwrite(connect=False)
        await user_channel.edit(overwrites=overwrites)
        await ctx.send('Your channel has been locked.')
    
    elif action == "unlock":
        overwrites = user_channel.overwrites.copy()
        overwrites[ctx.guild.default_role] = discord.PermissionOverwrite(connect=True)
        await user_channel.edit(overwrites=overwrites)
        await ctx.send('Your channel has been unlocked. Anyone can join now.')

    elif action == "allow":
        if not value:
            await ctx.send('Please mention a user or provide a user ID. Usage: !vm allow @user')
            return
    
        try:
            if ctx.message.mentions:
                target_user = ctx.message.mentions[0]
            else:
                target_id = int(value.strip())
                target_user = await bot.fetch_user(target_id)
                if not target_user:
                    await ctx.send(f'Could not find user with ID: {value}')
                    return
            
            overwrites = user_channel.overwrites.copy()
            overwrites[target_user] = discord.PermissionOverwrite(connect=True, view_channel=True)
            await user_channel.edit(overwrites=overwrites)
            
            await ctx.send(f'{target_user.mention} can now join your channel.')
        except ValueError:
            await ctx.send('Please provide a valid user ID or mention.')
        except Exception as e:
            await ctx.send(f'Error: {str(e)}')

    elif action == "deny":
        if not value:
            await ctx.send('Please mention a user or provide a user ID. Usage: !vm deny @user')
            return
    
        try:
            if ctx.message.mentions:
                target_user = ctx.message.mentions[0]
            else:
                target_id = int(value.strip())
                target_user = await bot.fetch_user(target_id)
                if not target_user:
                    await ctx.send(f'Could not find user with ID: {value}')
                    return
            
            member = ctx.guild.get_member(target_user.id)
            if member and member.voice and member.voice.channel and member.voice.channel.id == user_channel.id:
                try:
                    if ctx.guild.afk_channel:
                        await member.move_to(ctx.guild.afk_channel)
                    else:
                        await member.move_to(None)
                except:
                    pass
            
            overwrites = user_channel.overwrites.copy()
            overwrites[target_user] = discord.PermissionOverwrite(connect=False, view_channel=True)
            await user_channel.edit(overwrites=overwrites)
            
            await ctx.send(f'{target_user.mention} has been denied access to your channel.')
        except ValueError:
            await ctx.send('Please provide a valid user ID or mention.')
        except Exception as e:
            await ctx.send(f'Error: {str(e)}')
        
            overwrites = user_channel.overwrites.copy()
            overwrites[target_user] = discord.PermissionOverwrite(connect=False, view_channel=True)
            await user_channel.edit(overwrites=overwrites)
            
            await ctx.send(f'{target_user.mention} has been denied access to your channel.')
        except ValueError:
            await ctx.send('Please provide a valid user ID or mention.')
        except Exception as e:
            await ctx.send(f'Error: {str(e)}')
    
    elif action == "help":
        prefix = config.get('prefix', DEFAULT_PREFIX)
        embed = discord.Embed(
            title="VoiceMaster Commands",
            description=f"Use these commands to manage your temporary voice channel.",
            color=discord.Color.blue()
        )
        commands = [
                f"`{prefix}vm` - Create a new voice channel",
                f"`{prefix}vm name <name>` - Rename your channel",
                f"`{prefix}vm limit <number>` - Set user limit (0 for no limit)",
                f"`{prefix}vm lock` - Lock your channel to prevent new users from joining",
                f"`{prefix}vm unlock` - Unlock your channel to allow anyone to join",
                f"`{prefix}vm allow <@user/ID>` - Allow a specific user to join your channel",
                f"`{prefix}vm deny <@user/ID>` - Prevent a specific user from joining your channel"
        ]
        embed.add_field(name="Available Commands", value="\n".join(commands), inline=False)
        await ctx.send(embed=embed)
    
    else:
        await ctx.send(f'Unknown action. Use `!vm help` to see available commands.')

async def setup_voicemaster(ctx):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'voice_master' in config and config['voice_master'].get('enabled', False):
        await ctx.send('VoiceMaster is already set up for this server.')
        return
    
    try:
        category = await ctx.guild.create_category('Temporary Voice Channels')
        
        join_channel = await ctx.guild.create_voice_channel('➕ Create Voice Channel', category=category)
        
        if 'voice_master' not in config:
            config['voice_master'] = {}
        
        config['voice_master']['enabled'] = True
        config['voice_master']['join_channel_id'] = join_channel.id
        config['voice_master']['category_id'] = category.id
        config['voice_master']['user_channels'] = {}
        
        save_server_config(server_id, config)
        
        await ctx.send('VoiceMaster has been set up successfully! Users can now join the "➕ Create Voice Channel" to create their own temporary voice channel.')
    
    except discord.Forbidden:
        await ctx.send('I do not have permission to create channels.')
    except Exception as e:
        await ctx.send(f'An error occurred: {str(e)}')

def is_user_channel(ctx, channel):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'voice_master' not in config or not config['voice_master'].get('enabled', False):
        return False
    
    user_channels = config['voice_master'].get('user_channels', {})
    return str(channel.id) in user_channels and user_channels[str(channel.id)] == ctx.author.id

async def create_voice_channel(ctx):
    server_id = str(ctx.guild.id)
    config = load_server_config(server_id)
    
    if 'voice_master' not in config or not config['voice_master'].get('enabled', False):
        await ctx.send('VoiceMaster not set up. Please ask an administrator to run `!vm setup`.')
        return
    
    category_id = config['voice_master'].get('category_id')
    category = ctx.guild.get_channel(category_id)
    
    if not category:
        await ctx.send('VoiceMaster category not found. Please ask an administrator to run `!vm setup` again.')
        return
    
    try:
        channel_name = f"{ctx.author.display_name}'s Channel"
        new_channel = await ctx.guild.create_voice_channel(name=channel_name, category=category)
        
        await ctx.author.move_to(new_channel)
        
        if 'user_channels' not in config['voice_master']:
            config['voice_master']['user_channels'] = {}
        
        config['voice_master']['user_channels'][str(new_channel.id)] = ctx.author.id
        save_server_config(server_id, config)
    
    except discord.Forbidden:
        await ctx.send('I do not have permission to create channels or move members.')
    except Exception as e:
        await ctx.send(f'An error occurred: {str(e)}')

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    
    if after.channel:
        server_id = str(after.channel.guild.id)
        config = load_server_config(server_id)
        
        if 'voice_master' in config and config['voice_master'].get('enabled', False):
            join_channel_id = config['voice_master'].get('join_channel_id')
            
            if join_channel_id and after.channel.id == join_channel_id:
                ctx = await bot.get_context(await get_dummy_message(member))
                await create_voice_channel(ctx)
    
    if before.channel:
        server_id = str(before.channel.guild.id)
        config = load_server_config(server_id)
        
        if 'voice_master' in config and config['voice_master'].get('enabled', False):
            user_channels = config['voice_master'].get('user_channels', {})
            
            if str(before.channel.id) in user_channels:
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete()
                        del config['voice_master']['user_channels'][str(before.channel.id)]
                        save_server_config(server_id, config)
                    except:
                        pass


async def get_dummy_message(member):

    channel = None
    for c in member.guild.channels:
        if isinstance(c, discord.TextChannel):
            channel = c
            break
    
    if not channel:
        return None
    
    class DummyMessage:
        def __init__(self):
            self.content = "!vm"
            self.author = member
            self.guild = member.guild
            self.channel = channel
            self._state = member._state
            self.id = 0
            self.attachments = []
            self.embeds = []
            self.mentions = []
            self.role_mentions = []
            self.channel_mentions = []
    
    return DummyMessage()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        if hasattr(ctx.command, 'requires_permissions'):
            await ctx.send("You don't have permission to use this command.")
        else:
            await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument. Please check the command syntax.")
    else:
        print(f"Unexpected error: {error}")
        await ctx.send("An unexpected error occurred.")


if __name__ == "__main__":
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("Invalid token. Please check your bot token.")
    except discord.HTTPException as e:
        print(f"HTTP Exception: {e}")
    except Exception as e:
        print(f"Error starting the bot: {e}")