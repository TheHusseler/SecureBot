
import json
import discord
from discord import SelectOption
from discord.ui import View, Button, Modal, TextInput, ChannelSelect, Select, RoleSelect
from discord.ext import commands

#Config structure:
#{
#     "GUILDS": {
#         "GUILD ID as key": {
#             "DELETE_ENABLED": True/False,
#             "MOD_ROLE": role id, role for moderators
#             "NOTIFICATIONS_CHANNEL": channel id, Notifications for when a user leaves or other misc notifications
#             "BOT_LOGS_CHANNEL": channel id, logs details for the bot's functionality and debugging
#             "SAVE_EMOJI_NAME": name of emoji for saving posts,
#             "MESSAGE_AGE_LIMIT": 90 by default
#             "DELETE_BOT_MESSAGES": True/False
#         }
#     },
#     "BOT_TOKEN": "Token Here"

class BotConfig:
    def __init__(self):
        self.config = {}

    def load_config(self, file_path):
        try:
            with open(file_path, "r") as file:
                self.config = json.load(file)
            print(f"Loaded config")
        except FileNotFoundError:
            print("config.json file not found.")
        except json.JSONDecodeError:
            print("Error decoding config.json.")
        except Exception as e:
            print(f"Unexpected error loading config.json: {e}")

    def save_config(self, file_path):
        try:
            with open(file_path, "w") as file:
                json.dump(self.config, file, indent=4)
            print(f"Config saved")
        except Exception as e:
            print(f"Unexpected error saving config.json: {e}")

    def get_guild_data(self, guild_id, data_name):
        guild = self.config["GUILDS"][guild_id]
        return guild[data_name]

    def set_guild_data(self, guild_id, data_name, value):
        self.config["GUILDS"][guild_id][data_name] = value

class ConfigModal(Modal):
    bot_config: BotConfig

    title = "Configure Bot - Part 2"

    def __init__(self, bot_config: BotConfig):
        super().__init__(title="Configure Bot - Part 2")

        self.bot_config = bot_config

        self.add_item(TextInput(label="Save Emoji Name", placeholder="Enter the name of the emoji used to save posts from deletion"))
        self.add_item(TextInput(label="Message Age Limit", placeholder="Enter the number of days you want to keep messages for"))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            guild_id = str(interaction.guild.id)

            try:
                # Validate message age limit input
                message_age_limit = int(self.children[1].value)
            except ValueError:
                await interaction.response.send_message("Invalid input for Message Age Limit. Please enter a number.", ephemeral=True)
                return

            guild_data = {
                "SAVE_EMOJI_NAME": self.children[0].value,
                "MESSAGE_AGE_LIMIT": int(self.children[1].value)
            }
            if guild_id in self.bot_config.config["GUILDS"]: 
                self.bot_config.config["GUILDS"][guild_id].update(guild_data)
            else:
                self.bot_config.config["GUILDS"][guild_id] = guild_data
            
            self.bot_config.save_config("config.json")

            await interaction.response.send_message("Configuration updated successfully!", ephemeral=True)
        except Exception as e:
            print(f"Error in ConfigModal callback: {e}")
            await interaction.response.send_message("An error occurred. Please try again.", ephemeral=True)



class ConfigView(View):
    bot_config: BotConfig

    def __init__(self, guild: discord.Guild, bot_config: BotConfig):
        super().__init__()

        self.bot_config = bot_config

        self.mod_role_select = RoleSelect(
            placeholder="Select Moderator Role",
            custom_id="mod_role_select"
        )

        self.notifications_channel_select = ChannelSelect(
            placeholder="Select Notifications Channel",
            custom_id="notifications_channel_select",
            channel_types=[discord.ChannelType.text]
        )

        self.bot_logs_channel_select = ChannelSelect(
            placeholder="Select Bot Logs Channel",
            custom_id="bot_logs_channel_select",
            channel_types=[discord.ChannelType.text]
        )

        self.delete_bot_messages = Select(placeholder="Delete Bot Messages", 
            options=[
                SelectOption(label="Yes", description="The bot will delete it's own messages", value=True), 
                SelectOption(label="No", description="The bot will never delete it's own messages", value=False)
            ]
        )

        self.add_item(self.mod_role_select)
        self.add_item(self.notifications_channel_select)
        self.add_item(self.bot_logs_channel_select) 
        self.add_item(self.delete_bot_messages)    

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data.get('custom_id') != 'next':
            await interaction.response.defer()
        return True

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, custom_id="next", row=4)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)

        try:
            guild_data = {
                "MOD_ROLE": int(self.mod_role_select.values[0].id),
                "NOTIFICATIONS_CHANNEL": int(self.notifications_channel_select.values[0].id),
                "BOT_LOGS_CHANNEL": int(self.bot_logs_channel_select.values[0].id),
                "DELETE_BOT_MESSAGES": self.delete_bot_messages.values[0]
            }

            if guild_id in self.bot_config.config["GUILDS"]:
                self.bot_config.config["GUILDS"][guild_id].update(guild_data)
            else:
                self.bot_config.config["GUILDS"][guild_id] = guild_data

            self.bot_config.save_config("config.json")

            await interaction.response.send_modal(ConfigModal(self.bot_config))
        except IndexError:
            await interaction.response.send_message("Must select a channel for each", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(f"Unexpected error saving selections: {e}", ephemeral=True)
            return



