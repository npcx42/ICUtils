import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from typing import Dict, Any
from datetime import datetime
import pytz

IDEAS_FILE = "data/ideas.json"
CONFIG_FILE = "config.json"

class Ideas(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ideas: Dict[str, Any] = self.load_ideas()
        self.config = self.load_config()
        
    def load_config(self) -> dict:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def load_ideas(self) -> dict:
        os.makedirs("data", exist_ok=True)
        try:
            with open(IDEAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_ideas(self):
        with open(IDEAS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.ideas, f, ensure_ascii=False, indent=4)

    def calculate_rating(self, votes: Dict[str, int]) -> float:
        if not votes:
            return 0.0
        return round(sum(votes.values()) / len(votes), 1)

    @app_commands.command(name="suggest", description="Отправить предложение для сервера")
    @app_commands.describe(
        title="Краткий заголовок идеи",
        description="Подробное описание вашей идеи"
    )
    async def suggest(self, interaction: discord.Interaction, title: str, description: str):
        suggestions_channel_id = self.config.get("suggestions_channel_id")
        if not suggestions_channel_id:
            await interaction.response.send_message("Канал для предложений не настроен.", ephemeral=True)
            return

        channel = self.bot.get_channel(suggestions_channel_id)
        if not channel:
            await interaction.response.send_message("Не удалось найти канал для предложений.", ephemeral=True)
            return

        tz = pytz.timezone('Europe/Chisinau')
        current_time = datetime.now(tz)
        
        embed = discord.Embed(
            title=f"💡 {title}",
            description=description,
            color=0xFFAB6E,
            timestamp=current_time
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="Статус", value="⏳ На рассмотрении", inline=True)
        embed.add_field(name="Рейтинг", value="0.0 ⭐", inline=True)
        embed.set_footer(text="Made with ❤️ by npcx42, iconic people and my chinchillas 🐀")
        
        message = await channel.send(embed=embed)
        
        # Сохраняем информацию об идее
        self.ideas[str(message.id)] = {
            "author_id": interaction.user.id,
            "title": title,
            "description": description,
            "timestamp": current_time.isoformat(),
            "votes": {},
            "status": "pending",
            "decision_reason": None
        }
        self.save_ideas()

        # Добавляем кнопки и меню голосования
        view = IdeaView(self)
        await message.edit(view=view)
        
        await interaction.response.send_message("✅ Ваше предложение успешно отправлено!", ephemeral=True)

    async def update_idea_message(self, message_id: int):
        """Обновляет отображение идеи"""
        idea = self.ideas.get(str(message_id))
        if not idea:
            return

        channel = self.bot.get_channel(self.config.get("suggestions_channel_id"))
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
            embed = message.embeds[0]

            # Обновляем рейтинг
            rating = self.calculate_rating(idea["votes"])
            for i, field in enumerate(embed.fields):
                if field.name == "Рейтинг":
                    embed.set_field_at(i, name="Рейтинг", value=f"{rating} ⭐", inline=True)

            # Если есть решение, обновляем статус и удаляем view
            if idea["status"] != "pending":
                status_emoji = "✅" if idea["status"] == "accepted" else "❌"
                status_text = "Принято" if idea["status"] == "accepted" else "Отклонено"
                
                for i, field in enumerate(embed.fields):
                    if field.name == "Статус":
                        embed.set_field_at(i, name="Статус", value=f"{status_emoji} {status_text}", inline=True)
                
                if idea["decision_reason"]:
                    # Проверяем, есть ли уже поле с причиной
                    reason_exists = any(field.name == "Причина:" for field in embed.fields)
                    if not reason_exists:
                        embed.add_field(name="Причина:", value=idea["decision_reason"], inline=False)
                
                # Удаляем view после принятия решения
                await message.edit(embed=embed, view=None)
            else:
                await message.edit(embed=embed)
            
        except discord.NotFound:
            return

class IdeaView(discord.ui.View):
    def __init__(self, cog: Ideas):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(VoteSelect(cog))

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green, emoji="✅", custom_id="accept_idea")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ У вас нет прав для принятия идей.", ephemeral=True)
            return
        
        await interaction.response.send_modal(DecisionModal(self.cog, interaction.message, "accepted"))

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red, emoji="❌", custom_id="reject_idea")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ У вас нет прав для отклонения идей.", ephemeral=True)
            return
        
        await interaction.response.send_modal(DecisionModal(self.cog, interaction.message, "rejected"))

class VoteSelect(discord.ui.Select):
    def __init__(self, cog: Ideas):
        options = [
            discord.SelectOption(label=f"{i} звезд", value=str(i), emoji="⭐")
            for i in range(1, 6)
        ]
        super().__init__(
            placeholder="Оцените идею",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vote_select"
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        idea = self.cog.ideas.get(str(interaction.message.id))
        if not idea:
            await interaction.response.send_message("❌ Ошибка: идея не найдена.", ephemeral=True)
            return

        if idea["status"] != "pending":
            await interaction.response.send_message("❌ Голосование за эту идею закрыто.", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        if user_id == str(idea["author_id"]):
            await interaction.response.send_message("❌ Вы не можете голосовать за свою идею.", ephemeral=True)
            return

        vote = int(self.values[0])
        if user_id in idea["votes"]:
            old_vote = idea["votes"][user_id]
            if old_vote == vote:
                await interaction.response.send_message(f"ℹ️ Вы уже поставили {vote} ⭐ этой идее.", ephemeral=True)
                return
            
            msg = f"✅ Ваша оценка изменена с {old_vote} ⭐ на {vote} ⭐"
        else:
            msg = f"✅ Вы поставили {vote} ⭐ этой идее"

        idea["votes"][user_id] = vote
        self.cog.save_ideas()
        await self.cog.update_idea_message(interaction.message.id)
        await interaction.response.send_message(msg, ephemeral=True)

class DecisionModal(discord.ui.Modal, title="Решение по идее"):
    def __init__(self, cog: Ideas, message: discord.Message, decision: str):
        super().__init__()
        self.cog = cog
        self.message = message
        self.decision = decision
        self.reason = discord.ui.TextInput(
            label="Причина:",
            style=discord.TextStyle.paragraph,
            placeholder="Укажите причину вашего решения...",
            required=True,
            max_length=1000
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        idea = self.cog.ideas.get(str(self.message.id))
        if not idea:
            await interaction.response.send_message("❌ Ошибка: идея не найдена.", ephemeral=True)
            return

        idea["status"] = self.decision
        idea["decision_reason"] = self.reason.value
        self.cog.save_ideas()
        
        # Обновляем сообщение и удаляем view
        await self.cog.update_idea_message(self.message.id)
        
        # Отправляем уведомление автору
        try:
            author = await self.message.guild.fetch_member(idea["author_id"])
            if author:
                status = "принята" if self.decision == "accepted" else "отклонена"
                embed = discord.Embed(
                    title="Уведомление о решении",
                    description=f"Ваша идея «{idea['title']}» была {status}!\nПричина: {self.reason.value}",
                    color=0xFFAB6E,
                    timestamp=datetime.now(pytz.timezone('Europe/Chisinau'))
                )
                embed.set_footer(text="Made with ❤️ by npcx42, iconic people and my chinchillas 🐀")
                await author.send(embed=embed)
        except discord.NotFound:
            pass
        
        await interaction.response.send_message("✅ Решение по идее принято.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Ideas(bot))
