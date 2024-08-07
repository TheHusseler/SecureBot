import discord
from discord import app_commands, MessageType
from discord.ext import tasks, commands
from config_manager import BotConfig, ConfigModal, ConfigView
import datetime
import json


BOT_TOKEN = "YOUR BOT TOKEN HERE"
#Task is timed for 9 UTC, or 4 central
cleanUpTimes = [datetime.time(hour=9, minute=0, tzinfo=datetime.timezone.utc)]

intents=discord.Intents.default()
intents.typing = False
intents.presences = False
intents.messages = True
intents.members = True
intents.reactions = True

#Necessary Permissions
#permissions integer (untested): 67202112

# client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="!", intents=intents,
                   case_insensitive=False)

bot_config = BotConfig()
count = 0

#Notifications for users leaving/joining
@bot.event
async def on_member_remove(member):
    notifications_channel = bot_config.get_guild_data(str(member.guild.id), "NOTIFICATIONS_CHANNEL")
    await bot.get_channel(notifications_channel).send(f"{member.mention} has left the server.")

    # - 90 days till deletion, runs once a day
    # - Where they want their logs

def has_mod_role():
    async def predicate(interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        if not bot_config.config["GUILDS"].get(guild_id):
            return True # Allow if guild is not in config
        mod_role_id = bot_config.get_guild_data(guild_id, "MOD_ROLE")
        if not mod_role_id:
            return True  # Allow if mod_role is not set

        mod_role = interaction.guild.get_role(int(mod_role_id))
        if mod_role in interaction.user.roles:
            return True
        else:
            await interaction.response.send_message("You do not have the required role to execute this command.", ephemeral=True)
            return False
    return app_commands.check(predicate)

#Regular Message Deletion
@bot.tree.command(
    name="clean-up",
    description="Cleans up messages that aren't saved and are over x days old."
)
@has_mod_role()
async def clean_up(interaction):
    await interaction.response.defer()  # Defer the response to prevent timeout 
    enabled = (bot_config.get_guild_data(str(interaction.guild_id), "DELETE_ENABLED")  == "True")
    if not enabled:
        await interaction.followup.send("Deletion is not enabled.")
        return
    deleted = await clean_up_messages(interaction.guild_id)
    try:
        await interaction.followup.send(f"Deleted {deleted} messages by command for guild {interaction.guild_id}.")
    except discord.errors.NotFound:
        print("Interaction not found. Possibly due to timing issues.")

async def clean_up_messages(guildId) -> int:
    count = 0
    messageAgeLimit = int(bot_config.get_guild_data(str(guildId), "MESSAGE_AGE_LIMIT"))
    date = discord.utils.utcnow() - datetime.timedelta(hours=messageAgeLimit)
    for channel in bot.get_guild(int(guildId)).text_channels:
        try:
            deleted = await channel.purge(limit=None, check=should_delete, before=date)
            count += len(deleted)
        except Exception as e:
            print(f"Error deleting messages in channel {channel.id}: {e}")
    for channel in bot.get_guild(int(guildId)).voice_channels:
        try:
            deleted = await channel.purge(limit=None, check=should_delete, before=date)
            count += len(deleted)
        except Exception as e:
            print(f"Error deleting messages in voice channel {channel.id}: {e}")
    for thread in bot.get_guild(int(guildId)).threads:
        try:
            deleted = await thread.purge(limit=None, check=should_delete, before=date)
            count += len(deleted)
        except Exception as e:
            print(f"Error deleting messages in thread {thread.id}: {e}")
    return count

def should_delete(message) -> bool:
    global count
    guildId = str(message.guild.id)
    deleteBotMessages = (bot_config.get_guild_data(guildId, "DELETE_BOT_MESSAGES") == "True")
    saveEmojiName = bot_config.get_guild_data(guildId, "SAVE_EMOJI_NAME")
    return (not message.pinned 
        and not has_save_emoji(message, saveEmojiName) 
        and (message.author != bot.user or deleteBotMessages)
        and not message.is_system()
        and not message.type is MessageType.thread_starter_message)

def has_save_emoji(message, saveEmojiName) -> bool:
    for reaction in message.reactions:
        if reaction.is_custom_emoji() and reaction.emoji.name == saveEmojiName:
            return True
    return False

## Logging and Bot Specifics

#Log data about save reactions
@bot.event
async def on_raw_reaction_add(payload):
    msg_channel = bot.get_channel(payload.channel_id)
    msg = await msg_channel.fetch_message(payload.message_id)
    user = bot.get_user(payload.user_id)
    save_emoji_name = bot_config.get_guild_data(str(payload.guild_id), "SAVE_EMOJI_NAME")
    if (payload.emoji.name == save_emoji_name):
        embedVar = discord.Embed(title=f"User {payload.member.display_name} saved post", color=0x00ff00)
        embedVar.add_field(name="Original Author", value=f"{msg.author.display_name}", inline=True)
        embedVar.add_field(name="Saved By", value=f"{user.display_name}", inline=True)
        embedVar.add_field(name="Link", value=f"{msg.jump_url}", inline=True)
        embedVar.add_field(name="Time Saved", value=f"{datetime.datetime.now()}", inline=True)
        bot_logs_channel = bot_config.get_guild_data(str(payload.guild_id), "BOT_LOGS_CHANNEL")
        await bot.get_channel(bot_logs_channel).send(embed=embedVar)

#Logging bot details
@bot.event
async def on_ready():
    guild_data = {}
    bot_config.load_config("config.json")
    await bot.add_cog(DailyAction(bot, bot_config))
    # clean_up_messages_daily.start()

    await logAll("Bot is ready and running.")
    
@bot.event
async def on_resumed():
    await logAll("Bot has reconnected.")
    print("Bot has reconnected.")


@bot.event
async def on_disconnect():
    await logAll("Bot has disconnected.")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        # Ignore CheckFailure errors
        return
    raise error 

async def logAll(message):
    try:
        for guild_id, guild in bot_config.config["GUILDS"].items():
            await log(message, guild_id)
    except KeyError as e:
        print(f"KeyError: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

async def log(message, guildId):
    try:
        channel = bot_config.get_guild_data(guildId, "BOT_LOGS_CHANNEL")
        if channel:
            await bot.get_channel(channel).send(message)
        else:
            print(f"Channel not found for guild {guildId}")
    except Exception as e:
        print(f"Failed to log message to guild {guildId}: {e}")

#Command to log all messages with the reaction currently in the server
@bot.tree.command(
    name="log-saved-messages",
    description="Log all messages with the reaction currently in the server."
)
@has_mod_role()
async def log_saved_messages(interaction):
    await interaction.response.defer()  # Defer the response to prevent timeout 
    saveEmojiName = bot_config.get_guild_data(str(interaction.guild_id), "SAVE_EMOJI_NAME")
    logChannel = bot_config.get_guild_data(str(interaction.guild_id), "BOT_LOGS_CHANNEL")
    count = 0
    for channel in bot.get_guild(interaction.guild_id).text_channels:
        count += await log_saved_messages_in_channel(channel, saveEmojiName, logChannel)
        for thread in channel.threads:
            count += await log_saved_messages_in_channel(thread, saveEmojiName, logChannel)
    await interaction.followup.send(f"Logged {count} saved messages.", ephemeral=True)

async def log_saved_messages_in_channel(channel, saveEmojiName, logChannel) -> int:
    saveEmojiName = bot_config.get_guild_data(str(channel.guild.id), "SAVE_EMOJI_NAME")
    count = 0
    async for message in channel.history(limit=None):
        if has_save_emoji(message, saveEmojiName):
            embedVar = discord.Embed(title=f"Saved post", color=0x00ff00)
            embedVar.add_field(name="Link", value=f"{message.jump_url}", inline=True)
            embedVar.add_field(name="Author", value=f"{message.author.display_name}", inline=True)
            embedVar.add_field(name="Channel", value=f"{channel.name}")
            embedVar.add_field(name="Content Preview", value=f"{message.content[:100]}", inline=True)
            await bot.get_channel(logChannel).send(embed=embedVar)
            count += 1
    return count;

#Command to check if bot is running
@bot.tree.command(
    name="bot-check",
    description="Check if bot is running"
)
@has_mod_role()
async def bot_check(interaction):
    await interaction.response.send_message("Your bot is running! Better go catch it...", ephemeral=True)

@bot.tree.command(name="config", description="Configure the bot settings.")
@has_mod_role()
async def config(interaction: discord.Interaction):
    view = ConfigView(interaction.guild, bot_config)
    description = "Select some configuration values for the bot. Then hit next to open the modal for more configuration values.\
     \nMod Role - The role that has permission to use the bot's commands. \nNotifications - Where the bot will send notifications for users joining/leaving. \
     \nBot Logs - Where the bot will errors, statuses and message saves. \n Delete Bot Messages - Whether the bot will delete it's own messages."
    embed = discord.Embed(title="Configure Bot Settings", description=description)
    await interaction.response.send_message("Configure the bot settings:", embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="sync", description="Sync the command tree.")
@has_mod_role()
async def sync(interaction: discord.Interaction):
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
        await interaction.response.send_message(f'Command tree synced. {len(synced)} commands synchronized.', ephemeral=True)
    except Exception as e:
        print(f"Failed to sync: {e}")
        await interaction.response.send_message(f'Failed to sync commands: {e}', ephemeral=True)

@bot.tree.command(name="enable-delete", description="Enable the deletion of messages.")
@has_mod_role()
async def enable_delete(interaction: discord.Interaction):
    try:
        enabled = (bot_config.get_guild_data(str(interaction.guild_id), "DELETE_ENABLED")  == "True")
        if enabled:
            await interaction.response.send_message(f'Deletion is already enabled.', ephemeral=True)
            return
        bot_config.set_guild_data(str(interaction.guild_id), "DELETE_ENABLED", True)
        await interaction.response.send_message(f'CDeletion enabled.', ephemeral=True)
    except Exception as e:
        print(f"Failed to enable deletion: {e}")
        await interaction.response.send_message(f'Failed to enable deletion: {e}', ephemeral=True)

@bot.tree.command(name="disable-delete", description="Disable the deletion of messages.")
@has_mod_role()
async def disable_delete(interaction: discord.Interaction):
    try:
        enabled = (bot_config.get_guild_data(str(interaction.guild_id), "DELETE_ENABLED")  == "True")
        if not enabled:
            await interaction.response.send_message(f'Deletion is already disabled.', ephemeral=True)
            return
        bot_config.set_guild_data(str(interaction.guild_id), "DELETE_ENABLED", False)
        await interaction.response.send_message(f'Deletion disabled.', ephemeral=True)
    except Exception as e:
        print(f"Failed to disable deletion: {e}")
        await interaction.response.send_message(f'Failed to disable deletion: {e}', ephemeral=True)

@bot.tree.command(name="is-delete-enabled", description="Check if deletion is enabled.")
@has_mod_role()
async def is_delete_enabled(interaction: discord.Interaction):
    try:
        enabled = (bot_config.get_guild_data(str(interaction.guild_id), "DELETE_ENABLED")  == "True")
        await interaction.response.send_message(f'Deletion enabled: {enabled}', ephemeral=True)
    except Exception as e:
        print(f"Failed to check if deletion is enabled: {e}")
        await interaction.response.send_message(f'Failed to check if deletion is enabled: {e}', ephemeral=True)

class DailyAction(commands.Cog):
    def __init__(self, bot, bot_config) -> None:
        self.bot = bot
        self.bot_config = bot_config
        self.clean_up_messages_daily.start()

    @tasks.loop(time=cleanUpTimes)
    async def clean_up_messages_daily(self) -> None:
        print("Daily clean-up job")
        guilds = self.bot_config.config["GUILDS"].items();
        for guild_id, guild in guilds:
            guild_id_str = str(guild_id)
            enabled = (bot_config.get_guild_data(guild_id_str, "DELETE_ENABLED")  == "True")
            if not enabled:
                continue
            messageAgeLimit = int(self.bot_config.get_guild_data(guild_id_str, "MESSAGE_AGE_LIMIT"))
            await log(f"Cleaning up messages that aren't saved and are over {messageAgeLimit} days old.", guild_id_str)
            deleted = await clean_up_messages(guild_id)
            await log(f"Deleted {deleted} messages", guild_id_str)

bot.run(BOT_TOKEN)
