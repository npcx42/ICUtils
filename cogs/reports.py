import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime

REPORTS_FILE = "data/reports.json"
CONFIG_FILE = "config.json"

class Reports(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reports = self.load_reports()  # Структура: {"reports": [...], "users_agreed": [...], "blocked_users": [...]}
        self.config = self.load_config()

    def load_reports(self):
        if os.path.exists(REPORTS_FILE):
            with open(REPORTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "blocked_users" not in data:
                    data["blocked_users"] = []
                return data
        return {"reports": [], "users_agreed": [], "blocked_users": []}

    def save_reports(self):
        with open(REPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.reports, f, ensure_ascii=False, indent=4)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def get_next_case_id(self):
        if self.reports["reports"]:
            return max(report["case_id"] for report in self.reports["reports"]) + 1
        return 1

    def has_user_agreed(self, user_id: str):
        return user_id in self.reports["users_agreed"]

    def mark_user_as_agreed(self, user_id: str):
        if user_id not in self.reports["users_agreed"]:
            self.reports["users_agreed"].append(user_id)
            self.save_reports()

    def is_blocked(self, user_id: str):
        return user_id in self.reports["blocked_users"]

    def block_user(self, user_id: str):
        if user_id not in self.reports["blocked_users"]:
            self.reports["blocked_users"].append(user_id)
            self.save_reports()

    def unblock_user(self, user_id: str):
        if user_id in self.reports["blocked_users"]:
            self.reports["blocked_users"].remove(user_id)
            self.save_reports()

    @app_commands.command(name="report", description="Отправить репорт на пользователя")
    @app_commands.describe(
        user="Пользователь", 
        reason="Причина жалобы",
        attachment="Файл с доказательством (при желании)"
    )
    async def report_command(self, interaction: discord.Interaction, user: discord.User, reason: str, attachment: discord.Attachment = None):
        reporter_id = str(interaction.user.id)
        if self.is_blocked(reporter_id):
            await interaction.response.send_message("Вы не можете отправлять репорты. :middle_finger:", ephemeral=True)
            return

        if not self.has_user_agreed(reporter_id):
            await self.send_first_report_warning(interaction, user, reason, attachment)
        else:
            await self.send_report_confirmation(interaction, user, reason, attachment)

    async def send_first_report_warning(self, interaction: discord.Interaction, user: discord.User, reason: str, attachment: discord.Attachment = None):
        embed = discord.Embed(title="🚨 Внимание!", color=discord.Color.orange())
        embed.description = (
            "Похоже, это ваш первый репорт! Напоминаем, что каждая жалоба должна соответствовать нарушению **правил сервера**, "
            "а не быть основанной на личной неприязни или недоразумениях.\n\n"
            "⚠️ **Данное сообщение служит для предотвращения ложных репортов.**\n\n"
            "Вы **точно** хотите отправить жалобу на этого пользователя?"
        )
        view = ConfirmReportView(self.create_report, interaction, user, reason, attachment)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def send_report_confirmation(self, interaction: discord.Interaction, user: discord.User, reason: str, attachment: discord.Attachment = None):
        embed = discord.Embed(title="⚠️ Внимание!", color=discord.Color.red())
        embed.description = (
            "Вы точно хотите отправить репорт? Это действие необратимо и ложные репорты будут строго наказываться."
        )
        view = ConfirmReportView(self.create_report, interaction, user, reason, attachment)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def create_report(self, interaction: discord.Interaction, user: discord.User, reason: str, attachment: discord.Attachment = None):
        case_id = self.get_next_case_id()
        reporter_id = str(interaction.user.id)
        report_obj = {
            "case_id": case_id,
            "user_id": str(user.id),
            "reported_by": reporter_id,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "attachment": attachment.url if attachment else None,
            "status": "На рассмотрении",
            "appealed": False,
            "appeal": None,
            "appeal_status": None
        }
        self.reports["reports"].append(report_obj)
        self.save_reports()

        # Admin channel notification
        admin_channel_id = self.config.get("admin_channel_id")
        if admin_channel_id:
            admin_channel = self.bot.get_channel(admin_channel_id)
            if admin_channel:
                admin_embed = discord.Embed(title=f"Репорт #{case_id}", color=0xFFAB6E)
                admin_embed.add_field(name="Статус", value="На рассмотрении", inline=True)
                admin_embed.add_field(name="Репорт от", value=interaction.user.mention, inline=True)
                admin_embed.add_field(name="На пользователя", value=user.mention, inline=True)
                admin_embed.add_field(name="Причина", value=reason, inline=False)
                if attachment:
                    admin_embed.add_field(name="Прикрепленный файл", value=attachment.url, inline=False)
                admin_view = ReportResponseView(case_id, self.config, reporter_id, cog=self)
                await admin_channel.send(embed=admin_embed, view=admin_view)
        # ПОЧЕМУ ТУТ ДВА ЭМБЕДА СУКА!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        # Anonymous channel notification
        anon_channel_id = self.config.get("anonymous_reports_channel_id")
        if anon_channel_id:
            anon_channel = self.bot.get_channel(anon_channel_id)
            if anon_channel:
                anon_embed = discord.Embed(title=f"Репорт #{case_id}", color=0xFFAB6E)
                anon_embed.add_field(name="Статус", value="На рассмотрении", inline=True)
                anon_embed.add_field(name="На пользователя", value=user.mention, inline=True)
                anon_embed.add_field(name="Причина", value=reason, inline=False)
                message = await anon_channel.send(embed=anon_embed)
                anon_view = AnonymousReportView(case_id, self.config, reporter_id, cog=self, message=message)
                await message.edit(view=anon_view)

        await interaction.followup.send(f"Репорт отправлен.", ephemeral=True)
        self.mark_user_as_agreed(reporter_id)

    @app_commands.command(name="reports", description="Показать список всех репортов на пользователя")
    @app_commands.describe(user="Пользователь, чьи репорты вы хотите посмотреть")
    async def reports_command(self, interaction: discord.Interaction, user: discord.User):
        if not self.reports["reports"]:
            await interaction.response.send_message(f"Нет доступных репортов на {user.name}.", ephemeral=True)
            return

        user_reports = [report for report in self.reports["reports"] if report["user_id"] == str(user.id)]
        if not user_reports:
            await interaction.response.send_message(f"Нет репортов на {user.name}.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Репорты на {user.name}", color=discord.Color.blue())
        for report in user_reports:
            embed.add_field(
                name=f"Репорт #{report['case_id']}",
                value=f"Жалоба от <@{report['reported_by']}>\nПричина: {report['reason']}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="delete_report", description="Удалить репорт по номеру кейса")
    @app_commands.describe(case_id="Номер кейса репорта, который вы хотите удалить")
    async def delete_report(self, interaction: discord.Interaction, case_id: int):
        report = next((r for r in self.reports["reports"] if r["case_id"] == case_id), None)
        if not report:
            await interaction.response.send_message(f"Репорт с номером кейса #{case_id} не найден.", ephemeral=True)
            return

        self.reports["reports"].remove(report)
        self.save_reports()
        await interaction.response.send_message(f"Репорт #{case_id} был успешно удален.", ephemeral=True)

    @app_commands.command(name="banreports", description="Блокировать отправку репортов для пользователя")
    @app_commands.describe(user="Пользователь, которого хотите заблокировать")
    async def banreports(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("У вас нет прав для использования этой команды.", ephemeral=True)
            return
        reporter_id = str(user.id)
        if reporter_id in self.reports["blocked_users"]:
            await interaction.response.send_message("Этот пользователь уже заблокирован в системе репортов.", ephemeral=True)
        else:
            self.block_user(reporter_id)
            await interaction.response.send_message(f"Пользователь {user.mention} заблокирован в системе репортов.", ephemeral=True)

    @app_commands.command(name="unbanreports", description="Разблокирует доступ к системе репортов выбранному пользователю.")
    @app_commands.describe(user="Пользователь, которого хотите разблокировать")
    async def unbanreports(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("У вас нет прав для использования этой команды.", ephemeral=True)
            return
        reporter_id = str(user.id)
        if reporter_id not in self.reports["blocked_users"]:
            await interaction.response.send_message(f"Пользователь {user.mention} не заблокирован в системе репортов.", ephemeral=True)
        else:
            self.unblock_user(reporter_id)
            await interaction.response.send_message(f"Пользователь {user.mention} разблокирован в системе репортов.", ephemeral=True)

# View для подтверждения отправки репорта
class ConfirmReportView(discord.ui.View):
    def __init__(self, create_report_callback, interaction, user, reason, attachment: discord.Attachment = None):
        super().__init__(timeout=60)
        self.create_report_callback = create_report_callback
        self.interaction = interaction
        self.user = user
        self.reason = reason
        self.attachment = attachment

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.create_report_callback(self.interaction, self.user, self.reason, self.attachment)
        self.stop()

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send("Репорт отменен.", ephemeral=True)
        self.stop()

# View для ответа и отклонения репорта (в админ-канале)
class ReportResponseView(discord.ui.View):
    def __init__(self, case_id: int, config: dict, reporter_id: str, *, cog=None):
        super().__init__(timeout=None)
        self.case_id = case_id
        self.config = config
        self.reporter_id = reporter_id
        self.cog = cog

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("У вас нет прав для принятия репорта.", ephemeral=True)
            return

        report = next((r for r in self.cog.reports["reports"] if r["case_id"] == self.case_id), None)
        if report:
            report["status"] = "Принято"
            self.cog.save_reports()

            # Обновляем статус в анонимном канале
            anon_channel_id = self.config.get("anonymous_reports_channel_id")
            if anon_channel_id:
                anon_channel = interaction.client.get_channel(anon_channel_id)
                if anon_channel:
                    async for message in anon_channel.history():
                        if message.embeds and str(self.case_id) in message.embeds[0].title:
                            embed = message.embeds[0]
                            embed.set_field_at(0, name="Статус", value="Репорт был принят администрацией.", inline=True)
                            await message.edit(embed=embed)
                            break

        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="Статус", value="Принято", inline=True)
        await interaction.message.edit(embed=embed, view=None)

        reporter = interaction.client.get_user(int(self.reporter_id))
        if reporter:
            try:
                await reporter.send(f"Ваш репорт #{self.case_id} был **принят**.")
            except discord.Forbidden:
                pass

        await interaction.response.send_message("Репорт принят.", ephemeral=True)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, emoji="🚫")
    async def reject_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("У вас нет прав для отклонения репорта.", ephemeral=True)
            return

        # Открытие модального окна для ввода причины отклонения
        modal = ReportRejectionModal(self.case_id, self.config, self.reporter_id, cog=self.cog)
        await interaction.response.send_modal(modal)

# View для анонимного уведомления с кнопкой обжалования
class AnonymousReportView(discord.ui.View):
    def __init__(self, case_id: int, config: dict, reporter_id: str, *, cog=None, message=None):
        super().__init__(timeout=None)
        self.case_id = case_id
        self.config = config
        self.reporter_id = reporter_id
        self.cog = cog
        self.message = message  # Сохраняем сообщение для обновления

    @discord.ui.button(label="Обжаловать репорт", style=discord.ButtonStyle.secondary, emoji="📝")
    async def appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        report = next((r for r in self.cog.reports["reports"] if r["case_id"] == self.case_id), None)
        if not report:
            await interaction.response.send_message("Данный репорт был отклонен администрацией и удален из базы.", ephemeral=True)
            return
        if report.get("appealed", False):
            await interaction.response.send_message("Этот репорт уже обжалован.", ephemeral=True)
            return
        if str(interaction.user.id) != report["reported_by"]:
            await interaction.response.send_message("Вы не можете обжаловать этот репорт, так как он не адресован вам.", ephemeral=True)
            return

        # Открытие модального окна для апелляции
        modal = AppealReportModal(self.case_id, self.config, self.reporter_id, cog=self.cog, message=self.message)
        await interaction.response.send_modal(modal)

class AppealReportModal(discord.ui.Modal, title="Обжалование репорта"):
    appeal_text = discord.ui.TextInput(
        label="Ваше сообщение",
        style=discord.TextStyle.paragraph,
        placeholder="Опишите, почему вы считаете репорт несправедливым.",
        required=True,
        max_length=500
    )

    def __init__(self, case_id: int, config: dict, reporter_id: str, *, cog=None, message=None):
        super().__init__()
        self.case_id = case_id
        self.config = config
        self.reporter_id = reporter_id
        self.cog = cog
        self.message = message  # Добавляем сообщение

    async def on_submit(self, interaction: discord.Interaction):
        report = next((r for r in self.cog.reports["reports"] if r["case_id"] == self.case_id), None)
        if not report:
            await interaction.response.send_message("Репорт не найден.", ephemeral=True)
            return

        report["appealed"] = True
        report["appeal"] = self.appeal_text.value
        report["appeal_status"] = "На рассмотрении"
        self.cog.save_reports()

        admin_channel_id = self.config.get("admin_channel_id")
        if admin_channel_id:
            admin_channel = interaction.client.get_channel(admin_channel_id)
            if admin_channel:
                embed = discord.Embed(title=f"Обжалование репорта #{self.case_id}", color=0xFFAB6E)
                embed.add_field(name="Статус апелляции", value="На рассмотрении", inline=True)
                embed.add_field(name="Апелляция:", value=self.appeal_text.value, inline=False)
                view = AppealActionView(self.case_id, self.config, self.reporter_id, cog=self.cog)
                await admin_channel.send(embed=embed, view=view)

                # Обновляем только поле обжалования, не трогая статус
                anon_channel_id = self.config.get("anonymous_reports_channel_id")
                if anon_channel_id:
                    anon_channel = interaction.client.get_channel(anon_channel_id)
                    if anon_channel:
                        async for message in anon_channel.history():
                            if message.embeds and str(self.case_id) in message.embeds[0].title:
                                embed = message.embeds[0]
                                # Просто добавляем поле обжалования, не трогая статус
                                embed.add_field(name="Обжалован", value="Да, на рассмотрении", inline=False)
                                await message.edit(embed=embed, view=None)
                                break

                # Обновляем embed сообщения после успешной отправки апелляции
                if self.message and self.message.embeds:
                    embed = self.message.embeds[0]
                    embed.add_field(name="Обжалован", value="Да, на рассмотрении", inline=False)
                    await self.message.edit(embed=embed, view=None)

                await interaction.response.send_message("Ваше обжалование отправлено.", ephemeral=True)
                return

        await interaction.response.send_message("Ошибка: канал для апелляций не найден.", ephemeral=True)

class AppealActionView(discord.ui.View):
    def __init__(self, case_id: int, config: dict, reporter_id: str, *, cog=None):
        super().__init__(timeout=None)
        self.case_id = case_id
        self.config = config
        self.reporter_id = reporter_id
        self.cog = cog

    @discord.ui.button(label="Принять апелляцию", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        report = next((r for r in self.cog.reports["reports"] if r["case_id"] == self.case_id), None)
        if report:
            report["appeal_status"] = "Принято"
            self.cog.save_reports()

            # Обновляем статус в анонимном канале
            anon_channel_id = self.config.get("anonymous_reports_channel_id")
            if anon_channel_id:
                anon_channel = interaction.client.get_channel(anon_channel_id)
                if anon_channel:
                    async for message in anon_channel.history():
                        if message.embeds and str(self.case_id) in message.embeds[0].title:
                            embed = message.embeds[0]
                            for i, field in enumerate(embed.fields):
                                if field.name == "Обжалован":
                                    embed.set_field_at(i, name="Обжалован", value="Да, администрация приняла апелляцию.", inline=False)
                                    await message.edit(embed=embed)
                                    break
                            break

        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="Статус", value="Принято", inline=True)
        await interaction.message.edit(embed=embed, view=None)

        reporter = interaction.client.get_user(int(self.reporter_id))
        if reporter:
            try:
                await reporter.send(f"Ваша апелляция по репорту #{self.case_id} была **принята**.")
            except discord.Forbidden:
                pass

        await interaction.response.send_message("Апелляция принята.", ephemeral=True)

    @discord.ui.button(label="Отклонить апелляцию", style=discord.ButtonStyle.danger, emoji="🚫")
    async def decline_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AppealRejectionModal(self.case_id, self.config, self.reporter_id, cog=self.cog)
        await interaction.response.send_modal(modal)

class AppealRejectionModal(discord.ui.Modal, title="Отклонение апелляции"):
    rejection_reason = discord.ui.TextInput(label="Причина отказа", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, case_id: int, config: dict, reporter_id: str, *, cog=None):
        super().__init__()
        self.case_id = case_id
        self.config = config
        self.reporter_id = reporter_id
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        report = next((r for r in self.cog.reports["reports"] if r["case_id"] == self.case_id), None)
        if report:
            report["appeal_status"] = "Отклонено"
            report["appeal_rejection_reason"] = self.rejection_reason.value
            self.cog.save_reports()

            # Обновляем статус в анонимном канале
            anon_channel_id = self.config.get("anonymous_reports_channel_id")
            if anon_channel_id:
                anon_channel = interaction.client.get_channel(anon_channel_id)
                if anon_channel:
                    async for message in anon_channel.history():
                        if message.embeds and str(self.case_id) in message.embeds[0].title:
                            embed = message.embeds[0]
                            for i, field in enumerate(embed.fields):
                                if field.name == "Обжалован":
                                    embed.set_field_at(i, name="Обжалован", value="Да, администрация отклонила апелляцию.", inline=False)
                                    await message.edit(embed=embed)
                                    break
                            break

        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="Статус", value="Отклонено", inline=True)
        embed.add_field(name="Причина отказа", value=self.rejection_reason.value, inline=False)
        await interaction.message.edit(embed=embed, view=None)

        reporter = interaction.client.get_user(int(self.reporter_id))
        if reporter:
            try:
                await reporter.send(
                    f"Ваша апелляция по репорту #{self.case_id} была **отклонена**.\n"
                    f"Причина: {self.rejection_reason.value}"
                )
            except discord.Forbidden:
                pass

        await interaction.response.send_message("Апелляция отклонена.", ephemeral=True)
        
async def setup(bot: commands.Bot):
    await bot.add_cog(Reports(bot))