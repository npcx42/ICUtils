import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
import random
import datetime

class Levels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = MongoClient(bot.config.get("mongodb_uri"))
        self.db = self.client[bot.config.get("mongodb_db")]
        self.levels_collection = self.db["levels"]
        self.roles_collection = self.db["roles"]
        self.settings_collection = self.db["settings"]
        
        self.levels_collection.create_index([("user_id", 1)], unique=True)
        self.settings_collection.create_index([("guild_id", 1)], unique=True)

    def get_guild_settings(self, guild_id):
        settings = self.settings_collection.find_one({"guild_id": guild_id})
        if not settings:
            settings = {
                "guild_id": guild_id,
                "xp_range": (10, 50),
                "level_up_message": "Поздравляем {user}, вы достигли уровня {level}!",
                "levels_enabled": True,
                "xp_cooldown": 60,
                "ignored_channels": [],
                "level_roles": {}
            }
            self.settings_collection.insert_one(settings)
        return settings

    def get_user_data(self, user_id):
        user_data = self.levels_collection.find_one({"user_id": user_id})
        if not user_data:
            user_data = {"user_id": user_id, "xp": 0, "level": 0, "last_xp_time": datetime.datetime.utcnow()}
            self.levels_collection.insert_one(user_data)
        return user_data

    def add_xp(self, user_id, guild, xp):
        user_data = self.get_user_data(user_id)
        new_xp = user_data["xp"] + xp
        new_level = user_data["level"]
        next_level_xp = (new_level + 1) * 100 + new_level * 50  # Уровни растут плавно

        while new_xp >= next_level_xp:
            new_level += 1
            next_level_xp = (new_level + 1) * 100 + new_level * 50

        self.levels_collection.update_one(
            {"user_id": user_id},
            {"$set": {"xp": new_xp, "level": new_level, "last_xp_time": datetime.datetime.utcnow()}}
        )

        if new_level > user_data["level"]:
            self.bot.loop.create_task(self.send_level_up_message(user_id, guild, new_level))

    async def send_level_up_message(self, user_id, guild, level):
        settings = self.get_guild_settings(guild.id)
        member = guild.get_member(user_id)
        if not member:
            return

        message = settings["level_up_message"].format(user=member.mention, level=level)
        await member.send(message)

        # Проверяем, есть ли роль за этот уровень
        role_id = settings["level_roles"].get(str(level))
        if role_id:
            role = guild.get_role(role_id)
            if role:
                await member.add_roles(role)
    
    @app_commands.command(name="level", description="Проверить текущий уровень пользователя")
    async def level_command(self, interaction: discord.Interaction):
        user_data = self.get_user_data(interaction.user.id)
        await interaction.response.send_message(f"Вы имеете {user_data['xp']} опыта и уровень {user_data['level']}.")

    @app_commands.command(name="set_xp_range", description="Установить диапазон опыта за сообщение")
    @commands.has_permissions(administrator=True)
    async def set_xp_range_command(self, interaction: discord.Interaction, min_xp: int, max_xp: int):
        self.settings_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"xp_range": (min_xp, max_xp)}},
            upsert=True
        )
        await interaction.response.send_message(f"Диапазон опыта установлен: {min_xp} - {max_xp}.")

    @app_commands.command(name="setlevelrole", description="Установить роль за определенный уровень")
    @commands.has_permissions(administrator=True)
    async def set_level_role_command(self, interaction: discord.Interaction, level: int, role: discord.Role):
        settings = self.get_guild_settings(interaction.guild.id)
        settings["level_roles"][str(level)] = role.id
        self.settings_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"level_roles": settings["level_roles"]}},
            upsert=True
        )
        await interaction.response.send_message(f"Роль {role.mention} теперь будет выдаваться на уровне {level}.")

    @app_commands.command(name="reset_levels", description="Сбросить уровни всех пользователей")
    @commands.has_permissions(administrator=True)
    async def reset_levels_command(self, interaction: discord.Interaction):
        self.levels_collection.delete_many({})
        await interaction.response.send_message("Уровни всех пользователей сброшены.")

    @app_commands.command(name="togglelevels", description="Включить или выключить систему уровней")
    @commands.has_permissions(administrator=True)
    async def toggle_levels_command(self, interaction: discord.Interaction):
        settings = self.get_guild_settings(interaction.guild.id)
        new_status = not settings["levels_enabled"]
        self.settings_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"levels_enabled": new_status}},
            upsert=True
        )
        status = "включена" if new_status else "выключена"
        await interaction.response.send_message(f"Система уровней {status}.")

    @app_commands.command(name="set_ignore_channel", description="Игнорировать канал для начисления опыта")
    @commands.has_permissions(administrator=True)
    async def set_ignore_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel):
        settings = self.get_guild_settings(interaction.guild.id)
        if str(channel.id) not in settings["ignored_channels"]:
            settings["ignored_channels"].append(str(channel.id))
            self.settings_collection.update_one(
                {"guild_id": interaction.guild.id},
                {"$set": {"ignored_channels": settings["ignored_channels"]}},
                upsert=True
            )
            await interaction.response.send_message(f"Канал {channel.mention} теперь игнорируется.")
        else:
            await interaction.response.send_message(f"Канал {channel.mention} уже в списке игнорируемых.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        settings = self.get_guild_settings(message.guild.id)
        if not settings["levels_enabled"]:
            return

        if str(message.channel.id) in settings["ignored_channels"]:
            return

        user_data = self.get_user_data(message.author.id)
        now = datetime.datetime.utcnow()
        if (now - user_data["last_xp_time"]).total_seconds() < settings["xp_cooldown"]:
            return

        xp = random.randint(*settings["xp_range"])
        self.add_xp(message.author.id, message.guild, xp)

async def setup(bot: commands.Bot):
    await bot.add_cog(Levels(bot))
