import discord
from discord.ext import commands
import json
import os

CONFIG_FILE = "config.json"
APPLICATIONS_FILE = "data/applications.json"

class Recruit(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = self.load_config()
        self.applications = self.load_applications()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                # Преобразуем ID каналов в int, если они переданы как строки
                if "recruit_channel_id" in config:
                    config["recruit_channel_id"] = int(config["recruit_channel_id"])
                if "admin_channel_id" in config:
                    config["admin_channel_id"] = int(config["admin_channel_id"])
                return config
        return {}

    def load_applications(self):
        if os.path.exists(APPLICATIONS_FILE):
            with open(APPLICATIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"submitted_users": []}

    def save_applications(self):
        with open(APPLICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.applications, f, ensure_ascii=False, indent=4)

    @commands.Cog.listener()
    async def on_ready(self):
        print("Бот готов!")
        recruit_channel_id = self.config.get("recruit_channel_id")
        print(f"Recruit channel ID: {recruit_channel_id}")
        if not recruit_channel_id:
            print("Канал для набора не настроен в config.json.")
            return

        recruit_channel = self.bot.get_channel(recruit_channel_id)
        if not recruit_channel:
            print("Канал для набора не найден. Проверьте права доступа и корректность ID.")
            return

        # Удаляем старые сообщения с кнопками, если они есть
        try:
            async for message in recruit_channel.history(limit=10):
                if message.author == self.bot.user:
                    await message.delete()
        except Exception as e:
            print(f"Ошибка при удалении старых сообщений: {e}")

        embed = discord.Embed(
            title="Набор в администрацию",
            description="Нажмите на кнопку ниже, чтобы подать заявку. Вы можете подать заявку только один раз.",
            color=discord.Color.blue()
        )
        view = RecruitView(self)
        try:
            await recruit_channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"Ошибка при отправке сообщения в канал набора: {e}")

class RecruitView(discord.ui.View):
    def __init__(self, cog: Recruit):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Подать заявку", style=discord.ButtonStyle.green)
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        if user_id in self.cog.applications.get("submitted_users", []):
            await interaction.response.send_message(
                "Вы уже подали заявку. Повторная подача невозможна.", ephemeral=True
            )
            return
        try:
            await interaction.response.send_modal(RecruitModal(self.cog, interaction.user))
        except Exception as e:
            print(f"Ошибка при открытии модального окна для заявки: {e}")
            await interaction.response.send_message("Произошла ошибка при открытии формы заявки.", ephemeral=True)

class RecruitModal(discord.ui.Modal):
    def __init__(self, cog: Recruit, user: discord.User):
        super().__init__(title="Подать заявку")
        self.cog = cog
        self.user = user
        # Краткий placeholder (не более 100 символов)
        self.application_text = discord.ui.TextInput(
            label="Заявка",
            style=discord.TextStyle.paragraph,
            placeholder="Возраст, время, опыт, причина, навыки, часовой пояс",
            required=True,
            max_length=1000
        )
        self.add_item(self.application_text)

    async def on_submit(self, interaction: discord.Interaction):
        admin_channel_id = self.cog.config.get("admin_channel_id")
        if not admin_channel_id:
            await interaction.response.send_message("Канал для заявок не настроен.", ephemeral=True)
            return

        admin_channel = interaction.client.get_channel(admin_channel_id)
        if not admin_channel:
            await interaction.response.send_message("Канал для заявок не найден.", ephemeral=True)
            return

        self.cog.applications.setdefault("submitted_users", []).append(str(self.user.id))
        self.cog.save_applications()

        embed = discord.Embed(
            title="Новая заявка",
            description=f"Заявка от {self.user.mention} ({self.user})",
            color=discord.Color.green()
        )
        embed.add_field(name="Текст заявки", value=self.application_text.value, inline=False)
        embed.set_footer(text=f"ID: {self.user.id}")

        view = ApplicationDecisionView(self.user.id)
        try:
            await admin_channel.send(embed=embed, view=view)
            await interaction.response.send_message("Ваша заявка отправлена на рассмотрение.", ephemeral=True)
        except Exception as e:
            print(f"Ошибка при отправке заявки: {e}")
            await interaction.response.send_message("Произошла ошибка при отправке заявки.", ephemeral=True)

class ApplicationDecisionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.client.get_user(self.user_id)
        if user:
            try:
                await user.send("Ваша заявка была **принята**! В течение 72 часов с вами свяжется один из администраторов сервера.")
                # Обновляем embed: добавляем решение и удаляем view (кнопки)
                if interaction.message.embeds:
                    embed = interaction.message.embeds[0]
                    embed.add_field(name="Решение", value="Принято", inline=False)
                    await interaction.message.edit(embed=embed, view=None)
                await interaction.response.send_message("Заявка принята. Уведомление отправлено пользователю.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message(
                    f"Не удалось отправить сообщение {user.mention}. Личные сообщения закрыты.",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message("Пользователь не найден.", ephemeral=True)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Передаём исходное сообщение в модальное окно для последующего обновления embed
        try:
            await interaction.response.send_modal(RejectModal(self.user_id, interaction.message))
        except Exception as e:
            print(f"Ошибка при открытии модального окна отказа: {e}")
            await interaction.response.send_message("Не удалось открыть форму для указания причины отказа.", ephemeral=True)

class RejectModal(discord.ui.Modal):
    def __init__(self, user_id: int, original_message: discord.Message):
        super().__init__(title="Причина отказа")
        self.user_id = user_id
        self.original_message = original_message
        self.reason = discord.ui.TextInput(
            label="Укажите причину отказа",
            style=discord.TextStyle.paragraph,
            placeholder="Кратко опишите причину отказа (до 100 символов)",
            required=True,
            max_length=100
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.client.get_user(self.user_id)
        # Обновляем embed исходного сообщения: добавляем решение
        try:
            if self.original_message.embeds:
                embed = self.original_message.embeds[0]
                embed.add_field(name="Решение", value="Отклонено", inline=False)
                await self.original_message.edit(embed=embed, view=None)
        except Exception as e:
            print(f"Не удалось обновить сообщение: {e}")
        if user:
            try:
                await user.send(f"К сожалению, ваша заявка была **отклонена**.\nПричина: {self.reason.value}")
                await interaction.response.send_message("Уведомление с причиной отказа отправлено пользователю.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message(
                    f"Не удалось отправить сообщение {user.mention}. Личные сообщения закрыты.",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message("Пользователь не найден.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Recruit(bot))
