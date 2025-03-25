import discord
from discord.ext import commands
import os
import json
import asyncio
import logging

# Настройка логирования только для консоли
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# Загрузка конфигурации
with open('config.json') as config_file:
    config = json.load(config_file)

class MyBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.logger = logging.getLogger('bot')

    async def setup_hook(self):
        print("Начало инициализации бота...")
        try:
            await self.load_cogs()
            await self.sync_commands()
            print("Инициализация бота успешно завершена")
        except Exception as e:
            print(f"Ошибка при инициализации: {e}")

    async def load_cogs(self):
        """Загружает все коги из папки cogs."""
        print("Начало загрузки когов...")
        loaded_cogs = 0
        failed_cogs = 0
        
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"Загружен ког: {filename}")
                    loaded_cogs += 1
                except Exception as e:
                    print(f"Ошибка загрузки {filename}: {e}")
                    failed_cogs += 1
        
        print(f"Загрузка когов завершена. Успешно: {loaded_cogs}, Ошибок: {failed_cogs}")

    async def sync_commands(self):
        """Синхронизирует слэш-команды для всех гильдий."""
        print("Начало синхронизации команд...")
        try:
            for guild_id in self.config.get("allowed_guilds", []):
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                print(f"Команды синхронизированы для гильдии {guild_id}")
        except Exception as e:
            print(f"Ошибка при синхронизации команд: {e}")

    async def on_ready(self):
        print(f"Бот {self.user.name} успешно запущен!")

    async def on_error(self, event, *args, **kwargs):
        print(f"Ошибка в событии {event}")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return  # Игнорируем ошибки о ненайденных командах
        print(f"Ошибка: {error}")

intents = discord.Intents.all()
intents.message_content = True  # Добавлено для получения содержимого сообщений
bot = MyBot(command_prefix=commands.when_mentioned, intents=intents)  # Теперь бот реагирует только на @упоминания

async def main():
    async with bot:
        await bot.start(config['token'])

if __name__ == '__main__':
    asyncio.run(main())