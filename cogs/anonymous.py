import discord
from discord.ext import commands
from discord import app_commands
import logging
import json
import re

class Anonymous(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        with open("config.json", "r") as f:
            self.config = json.load(f)
        self.setup_logger()
        self.url_pattern = re.compile(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+|'
            r'(?:www\.)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,6}(?:/[^\s]*)?'
        )
        
        # Паттерн для Discord инвайтов
        self.discord_invite_pattern = re.compile(
            r'(?:https?://)?(?:www\.)?(discord\.(?:gg|io|me|li)|discordapp\.com/invite)/[a-zA-Z0-9]+',
            re.IGNORECASE
        )
        
        # Белый список разрешенных доменов
        self.allowed_domains = {
            'youtube.com',
            'youtu.be',
            'google.com',
            'github.com',
            'spotify.com',
            'wikipedia.org',
            'stackoverflow.com'
        }
        
        # Обновленный паттерн для URL с учетом поддоменов
        self.url_pattern = re.compile(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        )

    def setup_logger(self):
        self.logger = logging.getLogger('safety_logs')
        self.logger.setLevel(logging.WARNING)
        handler = logging.FileHandler('data/safety_logs.log')
        formatter = logging.Formatter('%(asctime)s - %(levellevelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def is_allowed_url(self, url: str) -> bool:
        """Проверяет, является ли URL разрешенным"""
        try:
            # Извлекаем домен из URL
            domain = url.lower()
            for prefix in ['https://', 'http://', 'www.']:
                if domain.startswith(prefix):
                    domain = domain[len(prefix):]
            domain = domain.split('/')[0]
            
            # Проверяем основной домен
            return any(domain.endswith(allowed_domain) for allowed_domain in self.allowed_domains)
        except:
            return False

    def filter_links(self, message: str) -> tuple[str, bool]:
        """
        Фильтрует ссылки в сообщении
        Возвращает (отфильтрованное_сообщение, содержит_discord_инвайт)
        """
        # Проверяем наличие Discord инвайтов
        if self.discord_invite_pattern.search(message):
            return message, True
        
        # Фильтруем остальные ссылки
        def replace_url(match):
            url = match.group(0)
            return url if self.is_allowed_url(url) else '[Ссылка заблокирована]'
        
        filtered_message = self.url_pattern.sub(replace_url, message)
        return filtered_message, False

    @app_commands.command(name="anon", description="Отправить анонимное сообщение")
    @app_commands.describe(
        message="Текст сообщения",
        user="Получатель сообщения"
    )
    async def anon(self, interaction: discord.Interaction, message: str, user: discord.Member):
        await interaction.response.defer(ephemeral=True)

        if user.bot:
            await interaction.followup.send("❌ Нельзя отправлять анонимные сообщения ботам!", ephemeral=True)
            return

        try:
            filtered_message, has_invite = self.filter_links(message)
            
            if has_invite:
                await interaction.followup.send(
                    "❌ Сообщение не отправлено. Нельзя отправлять приглашения на Discord серверы!",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="📫 Анонимное сообщение",
                description=filtered_message,
                color=discord.Color.blue()
            )
            embed.set_footer(text="Это сообщение отправлено анонимно")
            
            try:
                await user.send(embed=embed)
                await interaction.followup.send("✉️ Сообщение успешно отправлено!", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ Не удалось отправить сообщение. Возможно, у пользователя закрыты личные сообщения.",
                    ephemeral=True
                )

        except Exception as e:
            self.logger.error(f"Error in anon command: {e}")
            await interaction.followup.send(
                "❌ Произошла ошибка при отправке сообщения.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Anonymous(bot))
