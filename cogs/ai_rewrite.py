import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import os
import google.generativeai as genai

# Load configuration
with open("config.json") as f:
    config = json.load(f)

GROQ_API_KEY = config.get("groq_api_key")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
TEST_GUILD_ID = 1166664409578491934  # Replace with your server ID
DEBUG_ACCESS_UIDS = config.get("discord_debug_access_uid", [])

# Load models from models.json
with open("data/models.json") as f:
    models_config = json.load(f)

MODELS = models_config.get("models", [])


# Load prompt from file
def load_prompt():
    if os.path.exists("prompt.txt"):
        with open("prompt.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    return "Ты полезный AI-ассистент, помогай пользователям ответами на их вопросы."


SYSTEM_PROMPT = load_prompt()


# Load blocked IDs from file
def load_blocked_ids():
    if os.path.exists("blocked_ids.json"):
        with open("blocked_ids.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# Save blocked IDs to file
def save_blocked_ids(blocked_ids):
    with open("blocked_ids.json", "w", encoding="utf-8") as f:
        json.dump(blocked_ids, f, ensure_ascii=False, indent=4)


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.history = {}
        self.selected_model = MODELS[0] if MODELS else "llama-3.3-70b-versatile"  # Default model
        self.blocked_ids = load_blocked_ids()
        self.user_preferences = {}  # Store user preferences

        # Initialize Gemini API
        genai.configure(api_key=config.get("gemini_api_key"))
        self.gemini_model = genai.GenerativeModel("gemini-2.0-flash-exp-image-generation")

    async def fetch_ai_response(self, user_id: int, prompt: str, provider: str = None, model: str = None) -> list[str]:
        """Fetch AI response from the API."""

        # Use user preference if provider is not specified
        if provider is None:
            provider = self.user_preferences.get(user_id)
            if provider is None:
                return ["Пожалуйста, выберите провайдера с помощью команды /ask."]

        # Get conversation history
        history = self.history.get(user_id, [])

        # Build full prompt with history
        full_prompt = ""
        for turn in history:
            role = turn["role"]
            content = turn["content"]
            full_prompt += f"{role}: {content}\n"
        full_prompt += f"user: {prompt}"

        # History messages with system prompt
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(self.history.get(user_id, []))
        messages.append({"role": "user", "content": prompt})

        if provider == "groq":
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}"
            }
            selected_model = model if model else self.selected_model
            payload = {
                "model": selected_model,
                "messages": messages
            }
            api_url = GROQ_API_URL

        elif provider == "google":
            genai.configure(api_key=config.get("gemini_api_key"))
            selected_model = "gemini-2.0-flash"  # Use this model for text response

        else:
            return ["Неверный провайдер API."]

        if provider == "groq":
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(api_url, headers=headers, json=payload) as resp:
                        if resp.status != 200:
                            return [f"Ошибка API: {resp.status} - {await resp.text()}"]
                        result = await resp.json()
                except Exception as e:
                    return [f"Ошибка при запросе к API: {e}"]

            ai_response = result.get("choices", [{}])[0].get("message", {}).get("content", "Ошибка обработки ответа.")

        elif provider == "google":
            try:
                response = self.gemini_model.generate_content(contents=full_prompt)
                ai_response = ""
                for part in response.candidates[0].content.parts:
                    if part.text is not None:
                        ai_response += part.text
                if not ai_response:
                    ai_response = "Ошибка обработки ответа."
            except Exception as e:
                return [f"Ошибка при запросе к Google API: {e}"]

        if user_id not in self.history:
            self.history[user_id] = []

        # Add user message and bot response to history
        self.history[user_id].append({"role": "user", "content": prompt})
        self.history[user_id].append({"role": "assistant", "content": ai_response})

        # Split the response into chunks if it's too long
        if len(ai_response) > 2000:
            chunks = [ai_response[i:i + 2000] for i in range(0, len(ai_response), 2000)]
            return chunks
        else:
            return [ai_response]

    @app_commands.command(name="ask", description="Получить ответ от AI через выбранный API провайдер")
    @app_commands.describe(prompt="Ваш запрос для AI", provider="Выберите API провайдера", model="Выберите модель (необязательно)")
    async def ask_command(self, interaction: discord.Interaction, prompt: str, provider: str, model: str = None):
        """Slash command to get a response from the AI with provider selection."""

        if interaction.user.id in self.blocked_ids:
            await interaction.response.send_message("Вы заблокированы от использования AI-команд.", ephemeral=True)
            return

        # Store user preference
        self.user_preferences[interaction.user.id] = provider

        await interaction.response.defer(thinking=True)
        responses = await self.fetch_ai_response(interaction.user.id, prompt, provider, model)
        for response in responses:
            await interaction.followup.send(response)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Event to handle bot mentions."""

        if message.author == self.bot.user:
            return

        if self.bot.user.mentioned_in(message):
            user_id = message.author.id
            prompt = message.content.replace(f"<@{self.bot.user.id}>", "").strip()  # Remove mention from text

            await message.channel.typing()  # Show that the bot is "thinking"
            responses = await self.fetch_ai_response(user_id, prompt)
            for response in responses:
                await message.reply(response)

    @ask_command.autocomplete("provider")
    async def provider_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocompletion for provider selection."""

        providers = ["groq", "google"]
        choices = [
            app_commands.Choice(name=provider, value=provider)
            for provider in providers if current.lower() in provider.lower()
        ]
        return choices

    @ask_command.autocomplete("model")
    async def model_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocompletion for model selection."""

        choices = [
            app_commands.Choice(name=model, value=model)
            for model in MODELS if current.lower() in model.lower()
        ]
        return choices

    @app_commands.command(name="block_user", description="Заблокирует пользователю AI команды.")
    @app_commands.describe(user="Пользователь, которого нужно заблокировать")
    async def block_user_command(self, interaction: discord.Interaction, user: discord.User):
        """Slash command to block a user from using AI commands."""

        if str(interaction.user.id) not in DEBUG_ACCESS_UIDS:
            await interaction.response.send_message("Эта команда доступна только пользователям с доступом.", ephemeral=True)
            return

        if user.id not in self.blocked_ids:
            self.blocked_ids.append(user.id)
            save_blocked_ids(self.blocked_ids)
            await interaction.response.send_message(f"Пользователь {user.mention} заблокирован от использования AI-команд.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Пользователь {user.mention} уже заблокирован.", ephemeral=True)

    @app_commands.command(name="unblock_user", description="Разблокирует пользователя для использования AI")
    @app_commands.describe(user="Пользователь, которого нужно разблокировать")
    async def unblock_user_command(self, interaction: discord.Interaction, user: discord.User):
        """Slash command to unblock a user for using AI commands."""

        if str(interaction.user.id) not in DEBUG_ACCESS_UIDS:
            await interaction.response.send_message("Эта команда доступна только пользователям с доступом.", ephemeral=True)
            return

        if user.id in self.blocked_ids:
            self.blocked_ids.remove(user.id)
            save_blocked_ids(self.blocked_ids)
            await interaction.response.send_message(f"Пользователю {user.mention} разблокированы AI команды!!!", ephemeral=True)
        else:
            await interaction.response.send_message(f"Пользователь {user.mention} не заблокирован.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AI(bot))
