import discord
from discord.ext import commands
from discord import app_commands
import base64
import qrcode
from io import BytesIO
import hashlib
import asyncio
import requests
import re
from datetime import datetime, timedelta
import socket
import platform
import subprocess
from pythonping import ping as pyping
import statistics
import json

# Опциональные импорты
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("OpenCV не установлен. Команда qrdecode будет недоступна.")

class Utils(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminders = {}  # для хранения напоминаний
        self.EXCHANGE_API_URL = "https://api.exchangerate-api.com/v4/latest/USD"
        self.exchange_rates = None
        self.last_rates_update = None

        # Загружаем конфигурацию
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        self.weather_api_key = config.get("openweather_api_key")  # Добавляем API-ключ для OpenWeatherMap

    @app_commands.command(name="base64", description="Кодировать или декодировать текст в Base64")
    @app_commands.describe(action="Выберите действие", text="Текст для кодирования или декодирования")
    @app_commands.choices(action=[
        app_commands.Choice(name="encode", value="encode"),
        app_commands.Choice(name="decode", value="decode")
    ])
    async def base64_command(self, interaction: discord.Interaction, action: app_commands.Choice[str], text: str):
        if action.value == "encode":
            encoded_text = base64.b64encode(text.encode()).decode()
            await interaction.response.send_message(f"Закодированный текст: `{encoded_text}`")
        elif action.value == "decode":
            try:
                decoded_text = base64.b64decode(text.encode()).decode()
                await interaction.response.send_message(f"Декодированный текст: `{decoded_text}`")
            except Exception as e:
                await interaction.response.send_message(f"Ошибка декодирования: {e}")

    @app_commands.command(name="qrcode", description="Генерация QR-кода")
    async def generate_qr(self, interaction: discord.Interaction, text: str):
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(text)
            qr.make(fit=True)

            img = qr.make_image(fill='black', back_color='white')
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

            file = discord.File(fp=buffer, filename="qrcode.png")
            await interaction.response.send_message("Ваш QR-код:", file=file)
        except Exception as e:
            await interaction.response.send_message(f"Ошибка генерации QR-кода: {e}")

    @app_commands.command(name="hash", description="Хешировать текст с использованием различных алгоритмов")
    @app_commands.describe(algorithm="Выберите алгоритм хеширования", text="Текст для хеширования")
    @app_commands.choices(algorithm=[
        app_commands.Choice(name="MD5", value="md5"),
        app_commands.Choice(name="SHA-1", value="sha1"),
        app_commands.Choice(name="SHA-256", value="sha256"),
        app_commands.Choice(name="SHA-512", value="sha512")
    ])
    async def hash_command(self, interaction: discord.Interaction, algorithm: app_commands.Choice[str], text: str):
        try:
            if algorithm.value == "md5":
                hash_object = hashlib.md5(text.encode())
            elif algorithm.value == "sha1":
                hash_object = hashlib.sha1(text.encode())
            elif algorithm.value == "sha256":
                hash_object = hashlib.sha256(text.encode())
            elif algorithm.value == "sha512":
                hash_object = hashlib.sha512(text.encode())
            else:
                await interaction.response.send_message("Неверный алгоритм хеширования.", ephemeral=True)
                return

            hash_hex = hash_object.hexdigest()
            await interaction.response.send_message(f"Хешированный текст ({algorithm.name}): `{hash_hex}`")
        except Exception as e:
            await interaction.response.send_message(f"Ошибка хеширования: {e}")

    async def update_exchange_rates(self):
        """Обновляет курсы валют"""
        try:
            response = requests.get(self.EXCHANGE_API_URL)
            data = response.json()
            self.exchange_rates = data['rates']
            self.last_rates_update = datetime.now()
        except Exception as e:
            print(f"Ошибка получения курсов валют: {e}")

    @app_commands.command(name="remind", description="Установить напоминание")
    @app_commands.describe(
        time="Время (например: 30s, 5m, 2h, 1d или комбинации: 1h30m, 2d5h)", 
        message="Текст напоминания"
    )
    async def remind_command(self, interaction: discord.Interaction, time: str, message: str):
        pattern = r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?'
        match = re.match(pattern, time.lower())
        
        if not match or not any(match.groups()):
            await interaction.response.send_message(
                "Неверный формат времени. Примеры:\n"
                "30s - 30 секунд\n"
                "5m - 5 минут\n"
                "2h - 2 часа\n"
                "1d - 1 день\n"
                "Можно комбинировать: 1d12h30m, 2h30s", 
                ephemeral=True
            )
            return

        days = int(match.group(1) or 0)
        hours = int(match.group(2) or 0)
        minutes = int(match.group(3) or 0)
        seconds = int(match.group(4) or 0)

        total_seconds = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds

        if total_seconds <= 0:
            await interaction.response.send_message("Время должно быть положительным!", ephemeral=True)
            return

        if total_seconds > 2592000:  # 30 дней
            await interaction.response.send_message(
                "Максимальное время напоминания - 30 дней", 
                ephemeral=True
            )
            return

        # Формируем читаемое время для ответа
        time_parts = []
        if days: time_parts.append(f"{days}d")
        if hours: time_parts.append(f"{hours}h")
        if minutes: time_parts.append(f"{minutes}m")
        if seconds: time_parts.append(f"{seconds}s")
        readable_time = " ".join(time_parts)

        await interaction.response.send_message(
            f"⏰ Напоминание установлено на {readable_time}",
            ephemeral=True
        )
        
        await asyncio.sleep(total_seconds)
        try:
            await interaction.user.send(f"⏰ Напоминание: {message}")
        except:
            print(f"Не удалось отправить напоминание пользователю {interaction.user.id}")

    @app_commands.command(name="convert", description="Конвертировать валюту")
    @app_commands.describe(amount="Сумма", from_currency="Из какой валюты", to_currency="В какую валюту")
    async def convert_command(self, interaction: discord.Interaction, amount: float, 
                            from_currency: str, to_currency: str):
        if not self.exchange_rates or \
           (datetime.now() - self.last_rates_update > timedelta(hours=1)):
            await self.update_exchange_rates()

        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency not in self.exchange_rates or to_currency not in self.exchange_rates:
            await interaction.response.send_message("Неподдерживаемая валюта!", ephemeral=True)
            return

        # Конвертация через USD как базовую валюту
        usd_amount = amount / self.exchange_rates[from_currency]
        result = usd_amount * self.exchange_rates[to_currency]

        await interaction.response.send_message(
            f"{amount:.2f} {from_currency} = {result:.2f} {to_currency}"
        )

    @app_commands.command(name="ping", description="Проверить доступность сервера или веб-ресурса")
    @app_commands.describe(target="IP адрес или домен для проверки")
    async def ping_command(self, interaction: discord.Interaction, target: str):
        await interaction.response.defer()
        
        try:
            # Try to resolve the hostname
            try:
                socket.gethostbyname(target)
            except socket.gaierror:
                await interaction.followup.send(f"❌ Не удалось разрешить домен: {target}", ephemeral=True)
                return

            # Perform the ping
            ping_result = pyping(target, count=4, timeout=2)
            
            # Calculate statistics
            if ping_result.success():
                response_times = [response.time_elapsed_ms for response in ping_result._responses if response]
                avg_time = statistics.mean(response_times) if response_times else 0
                min_time = min(response_times) if response_times else 0
                max_time = max(response_times) if response_times else 0
                packet_loss = (4 - len(response_times)) / 4 * 100  # Calculate packet loss percentage

                result = (
                    f"```\n"
                    f"Пинг {target}:\n"
                    f"Отправлено пакетов: 4\n"
                    f"Получено пакетов: {len(response_times)}\n"
                    f"Потеряно пакетов: {4 - len(response_times)} ({packet_loss:.1f}%)\n"
                    f"\n"
                    f"Минимальное время: {min_time:.1f} мс\n"
                    f"Среднее время: {avg_time:.1f} мс\n"
                    f"Максимальное время: {max_time:.1f} мс\n"
                    f"```"
                )
                await interaction.followup.send(result)
            else:
                await interaction.followup.send(f"❌ Сервер {target} недоступен", ephemeral=True)
                
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка при выполнении команды: {str(e)}", ephemeral=True)

    @app_commands.command(name="user", description="Показать информацию о пользователе")
    @app_commands.describe(user="Пользователь, о котором хотите узнать информацию")
    async def user_command(self, interaction: discord.Interaction, user: discord.User = None):
        """Показывает детальную информацию о пользователе"""
        target = user or interaction.user
        member = interaction.guild.get_member(target.id)

        embed = discord.Embed(
            title="Информация о пользователе",
            color=member.color if member else discord.Color.blue()
        )

        # Основная информация
        embed.add_field(name="Имя", value=f"{target} ({target.mention})", inline=False)
        embed.add_field(name="ID", value=target.id, inline=True)
        embed.add_field(name="Бот?", value=":white_check_mark:" if target.bot else ":x:", inline=True)

        # Даты
        created_at = int(target.created_at.timestamp())
        embed.add_field(
            name="Дата регистрации",
            value=f"<t:{created_at}:F>\n(<t:{created_at}:R>)",
            inline=False
        )

        if member:
            joined_at = int(member.joined_at.timestamp())
            embed.add_field(
                name="Присоединился к серверу",
                value=f"<t:{joined_at}:F>\n(<t:{joined_at}:R>)",
                inline=False
            )
            
            # Роли
            roles = [role.mention for role in reversed(member.roles[1:])]  # Исключаем @everyone
            if roles:
                embed.add_field(
                    name=f"Роли [{len(roles)}]",
                    value=" ".join(roles) if len(roles) <= 10 else " ".join(roles[:10]) + f" и ещё {len(roles)-10}",
                    inline=False
                )

            # Права
            key_permissions = []
            if member.guild_permissions.administrator:
                key_permissions.append("Администратор")
            if member.guild_permissions.manage_guild:
                key_permissions.append("Управление сервером")
            if member.guild_permissions.manage_roles:
                key_permissions.append("Управление ролями")
            if member.guild_permissions.manage_channels:
                key_permissions.append("Управление каналами")
            if member.guild_permissions.manage_messages:
                key_permissions.append("Управление сообщениями")
            if member.guild_permissions.kick_members:
                key_permissions.append("Кик участников")
            if member.guild_permissions.ban_members:
                key_permissions.append("Бан участников")

            if key_permissions:
                embed.add_field(
                    name="Ключевые права",
                    value=", ".join(key_permissions),
                    inline=False
                )

            # Статус и активность
            status_emoji = {
                "online": "🟢",
                "idle": "🌙",
                "dnd": "⛔",
                "offline": "⚫"
            }
            status = f"{status_emoji.get(str(member.status), '⚫')} {str(member.status).title()}"
            embed.add_field(name="Статус", value=status, inline=True)

            if member.activity:
                activity_type = {
                    discord.ActivityType.playing: "Играет в",
                    discord.ActivityType.streaming: "Стримит",
                    discord.ActivityType.listening: "Слушает",
                    discord.ActivityType.watching: "Смотрит",
                    discord.ActivityType.custom: "Кастомный статус:",
                    discord.ActivityType.competing: "Соревнуется в"
                }
                activity = f"{activity_type.get(member.activity.type, 'Неизвестно')} {member.activity.name}"
                embed.add_field(name="Активность", value=activity, inline=True)

        # Аватар
        embed.set_thumbnail(url=target.display_avatar.url)
        
        # Баннер, если есть
        if hasattr(target, 'banner') and target.banner:
            embed.set_image(url=target.banner.url)

        embed.set_footer(text="Made with ❤️ by npcx42, iconic people and my chinchillas 🐀")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="weather", description="Показать текущую погоду в указанном городе")
    @app_commands.describe(city="Название города")
    async def weather_command(self, interaction: discord.Interaction, city: str):
        """Показывает текущую погоду в указанном городе."""
        if not self.weather_api_key:
            await interaction.response.send_message("API-ключ для OpenWeatherMap не настроен.", ephemeral=True)
            return

        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={self.weather_api_key}&units=metric&lang=ru"
        try:
            response = requests.get(url)
            if response.status_code == 401:
                await interaction.response.send_message("Неверный API-ключ для OpenWeatherMap. Проверьте конфигурацию.", ephemeral=True)
                return
            elif response.status_code == 404:
                await interaction.response.send_message(f"Город '{city}' не найден. Проверьте правильность написания.", ephemeral=True)
                return
            elif response.status_code != 200:
                await interaction.response.send_message(f"Ошибка API OpenWeatherMap: {response.status_code} - {response.reason}", ephemeral=True)
                return

            data = response.json()
            weather = data["weather"][0]["description"].capitalize()
            temp = data["main"]["temp"]
            feels_like = data["main"]["feels_like"]
            humidity = data["main"]["humidity"]
            wind_speed = data["wind"]["speed"]

            embed = discord.Embed(
                title=f"Погода в городе {city.capitalize()}",
                color=discord.Color.blue()
            )
            embed.add_field(name="🌡 Температура", value=f"{temp}°C (ощущается как {feels_like}°C)", inline=False)
            embed.add_field(name="💧 Влажность", value=f"{humidity}%", inline=True)
            embed.add_field(name="💨 Скорость ветра", value=f"{wind_speed} м/с", inline=True)
            embed.add_field(name="🌥 Описание", value=weather, inline=False)
            embed.set_footer(text="Данные предоставлены OpenWeatherMap")

            await interaction.response.send_message(embed=embed)
        except requests.exceptions.RequestException as e:
            await interaction.response.send_message(f"Ошибка подключения к OpenWeatherMap: {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Произошла неизвестная ошибка: {e}", ephemeral=True)

    # Изменяем декоратор для условного добавления команды
    if CV2_AVAILABLE:
        @app_commands.command(name="qrdecode", description="Расшифровать QR-код")
        async def qrdecode_command(self, interaction: discord.Interaction, image: discord.Attachment):
            if not image.content_type.startswith('image/'):
                await interaction.response.send_message("Пожалуйста, отправьте изображение!", ephemeral=True)
                return

            try:
                # Скачиваем изображение
                image_data = await image.read()
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
                
                # Читаем QR-код
                detector = cv2.QRCodeDetector()
                data, bbox, _ = detector.detectAndDecode(img)
                
                if data:
                    await interaction.response.send_message(f"Содержимое QR-кода:\n```\n{data}\n```")
                else:
                    await interaction.response.send_message("QR-код не найден!", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Ошибка при чтении QR-кода: {e}", ephemeral=True)
    else:
        @app_commands.command(name="qrdecode", description="Расшифровать QR-код (Недоступно)")
        async def qrdecode_command(self, interaction: discord.Interaction, image: discord.Attachment):
            await interaction.response.send_message(
                "Эта команда недоступна. Установите opencv-python для её активации.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Utils(bot))