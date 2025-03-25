import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from typing import Literal

class Activity(commands.Cog):
    """Управление статусом и активностью бота"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._status_file = "data/activity.json"
        self.current_status = self._load_status()

    def _load_status(self) -> dict:
        """Загружает последний сохраненный статус"""
        default_status = {"text": None, "type": None}
        
        if not os.path.exists(self._status_file):
            return default_status
            
        try:
            with open(self._status_file, "r", encoding="utf-8") as f:
                loaded_status = json.load(f)
                # Проверка наличия необходимых ключей
                if "text" not in loaded_status or "type" not in loaded_status:
                    return default_status
                return loaded_status
        except (json.JSONDecodeError, FileNotFoundError, Exception):
            return default_status

    def _save_status(self, status_text: str, activity_type: str):
        """Сохраняет текущий статус в файл"""
        os.makedirs("data", exist_ok=True)
        data = {
            "text": status_text,
            "type": activity_type
        }
        with open(self._status_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def _create_activity(self, text: str, type_: str) -> discord.Activity:
        """Создает объект активности нужного типа"""
        activities = {
            "играет": lambda: discord.Game(name=text),
            "стримит": lambda: discord.Streaming(name=text, url="https://www.twitch.tv/npcx42"),
            "слушает": lambda: discord.Activity(type=discord.ActivityType.listening, name=text),
            "смотрит": lambda: discord.Activity(type=discord.ActivityType.watching, name=text)
        }
        return activities.get(type_, lambda: discord.Game(name=text))()

    @commands.Cog.listener()
    async def on_ready(self):
        """Восстанавливает статус бота при запуске"""
        if self.current_status.get("text"):  # Используем .get() для безопасного доступа
            activity = self._create_activity(
                self.current_status.get("text"), 
                self.current_status.get("type", "играет")  # Добавляем значение по умолчанию
            )
            await self.bot.change_presence(activity=activity)
            print(f"[Статус] Восстановлен: {self.current_status['text']} ({self.current_status['type']})")

    @app_commands.command(name="activity", description="Изменить статус бота")
    @app_commands.describe(
        text="Текст статуса",
        type="Тип активности"
    )
    async def change_activity(
        self,
        interaction: discord.Interaction,
        text: str,
        type: Literal["играет", "стримит", "слушает", "смотрит"]
    ):
        """Изменяет статус бота"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Только администраторы могут менять статус бота.", 
                ephemeral=True
            )
            return

        activity = self._create_activity(text, type)
        await self.bot.change_presence(activity=activity)
        self._save_status(text, type)
        self.current_status = {"text": text, "type": type}

        embed = discord.Embed(
            title="✅ Статус изменен",
            description=f"**Новый статус:** {text}\n**Тип:** {type}",
            color=0xFFAB6E
        )
        embed.set_footer(text="Made with ❤️ by npcx42, iconic people and my chinchillas 🐀")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @change_activity.error
    async def activity_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "❌ У вас недостаточно прав для использования этой команды.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Произошла ошибка при изменении статуса.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Activity(bot))
