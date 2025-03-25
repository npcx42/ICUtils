import discord
from discord.ext import commands
from discord import app_commands

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(CategorySelect())

class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Утилиты",
                description="Полезные утилиты для повседневных задач",
                emoji="🛠️"
            ),
            discord.SelectOption(
                label="Музыка",
                description="Команды для проигрывания музыки",
                emoji="🎵"
            ),
            discord.SelectOption(
                label="Система репортов",
                description="Команды для работы с репортами",
                emoji="📢"
            ),
            discord.SelectOption(
                label="AI-команды",
                description="Взаимодействие с ИИ",
                emoji="🤖"
            ),
            discord.SelectOption(
                label="Модерация",
                description="Команды модерации",
                emoji="🛡️"
            )
        ]
        super().__init__(
            placeholder="Выберите категорию команд...",
            options=options,
            custom_id="help_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        
        embed = discord.Embed(
            title=f"Команды категории {category}",
            color=discord.Color.blue()
        )

        if category == "Утилиты":
            embed.description = (
                "**🛠️ Доступные команды:**\n"
                "• `/qrcode` - Создание QR-кода\n"
                "• `/qrdecode` - Чтение QR-кода\n"
                "• `/hash` - Хеширование текста\n"
                "• `/base64` - Кодирование/декодирование Base64\n"
                "• `/remind` - Установить напоминание\n"
                "• `/convert` - Конвертация валют\n"
                "• `/anon` - Отправить анонимное сообщение\n"
                "• `/weather` - Показать погоду\n"
                "• `/user` - Информация о пользователе"
            )

        elif category == "Музыка":
            embed.description = (
                "**🎵 Доступные команды:**\n"
                "• `/play` - Проигрывает музыку/плейлист\n"
                "• `/pause` - Приостановить воспроизведение\n"
                "• `/resume` - Возобновить воспроизведение\n"
                "• `/skip` - Пропустить текущий трек\n"
                "• `/stop` - Остановить воспроизведение\n"
                "• `/queue` - Показать очередь треков\n"
                "• `/nowplaying` - Показать текущий трек\n"
                "• `/save` - Сохранить трек в ЛС\n"
                "• `/loop` - Управление повтором\n"
                "• `/shuffle` - Перемешать очередь\n"
                "• `/seek` - Перемотать трек\n"
                "• `/clear` - Очистить очередь"
            )

        elif category == "Система репортов":
            embed.description = (
                "**📢 Доступные команды:**\n"
                "• `/report` - Создать новый репорт\n"
                "• `/reports` - Просмотр репортов\n"
                "• `/delete_report` - Удалить репорт"
            )

        elif category == "AI-команды":
            embed.description = (
                "**🤖 Доступные команды:**\n"
                "• `/ask` - Задать вопрос ИИ\n"
                "Поддерживаемые провайдеры: Groq, Google"
            )

        elif category == "Модерация":
            embed.description = (
                "**🛡️ Доступные команды:**\n"
                "• `/banreports` - Заблокировать отправку репортов\n"
                "• `/unbanreports` - Разблокировать отправку репортов"
            )

        embed.set_footer(text="Made with ❤️ by npcx42")
        await interaction.response.edit_message(embed=embed, view=self.view)

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Показать список команд по категориям")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Помощь по командам",
            description="Выберите категорию команд из выпадающего списка ниже",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Made with ❤️ by npcx42")
        
        view = HelpView()
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Help(bot))