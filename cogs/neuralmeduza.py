import json
import requests
from bs4 import BeautifulSoup
import aiocron
import discord
from discord.ext import commands
from discord import app_commands

class NeuralMeduza(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_message = None  # Память для последнего отправленного поста
        self.previous_message = None  # Добавляем хранение предыдущего сообщения

        # Загрузка конфигурации из JSON файла
        with open("config.json", encoding="utf-8") as f:
            config = json.load(f)

        self.CHANNEL_URL = config["channel_url"]
        self.DISCORD_BOT_ID = int(config["discord_bot_id"])
        self.DISCORD_CHANNEL_ID = int(config["discord_channel_id"])
        self.DISCORD_THREAD_NAME = config["discord_thread_name"]
        self.DISCORD_DEBUG_ACCESS = config["discord_debug_access_uid"]  # список id в виде строк

        self.start_channel_check()

    def fetch_latest_message(self, channel_url: str) -> str or None:
        """Запрашивает страницу канала и возвращает новый пост (если он отличается от предыдущего)."""
        try:
            response = requests.get(channel_url)
            response.raise_for_status()
        except Exception as e:
            print(f"Ошибка запроса: {e}")
            return None

        soup = BeautifulSoup(response.content, "html.parser")
        messages = soup.find_all("div", class_="tgme_widget_message_text")
        if not messages:
            return None

        new_text = messages[-1].get_text(strip=True)
        if new_text == self.last_message:
            return None

        self.previous_message = self.last_message  # Сохраняем предыдущее сообщение
        self.last_message = new_text
        return new_text

    def start_channel_check(self):
        """Планировщик, запускаемый по расписанию каждые 5 минут"""
        @aiocron.crontab("*/5 * * * *")
        async def scheduled_check():
            new_text = self.fetch_latest_message(self.CHANNEL_URL)
            if new_text:
                channel = self.bot.get_channel(self.DISCORD_CHANNEL_ID)
                if channel:
                    try:
                        await channel.send(new_text)
                        print(f"Отправлено новое сообщение с {self.CHANNEL_URL}: {new_text}")
                    except Exception as e:
                        print(f"Ошибка при отправке сообщения: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user} (ID: {self.bot.user.id})")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        channelId = message.channel.id
        userId = message.author.id
        bot = message.author.bot

        # Проверка, является ли сообщение от бота
        if bot and userId == self.DISCORD_BOT_ID:
            if channelId == self.DISCORD_CHANNEL_ID:
                await message.create_thread(
                    name=self.DISCORD_THREAD_NAME,
                    reason="Разрешение на комментарии под сообщением"
                )
        else:
            if channelId == self.DISCORD_CHANNEL_ID:
                await message.delete()

    @app_commands.command(name="debug", description="Проверить работу бота и получить сообщения из Telegram")
    async def debug_command(self, interaction: discord.Interaction):
        if str(interaction.user.id) not in self.DISCORD_DEBUG_ACCESS:
            await interaction.response.send_message("У вас нет прав для выполнения этой команды.", ephemeral=True)
            return
        
        new_text = self.fetch_latest_message(self.CHANNEL_URL)
        response_msg = f"Бот работает.\n\n"
        response_msg += f"Ссылка на канал: {self.CHANNEL_URL}\n\n"
        
        if self.previous_message:
            response_msg += f"Предыдущее сообщение:\n{self.previous_message}\n\n"
        
        if new_text:
            response_msg += f"Новое сообщение:\n{new_text}"
        else:
            response_msg += f"Текущее сообщение:\n{self.last_message}"
        
        await interaction.response.send_message(response_msg)

async def setup(bot: commands.Bot):
    await bot.add_cog(NeuralMeduza(bot))