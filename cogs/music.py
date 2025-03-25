import discord
from discord.ext import commands
from discord import app_commands
import wavelink
import asyncio
import json
import time
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Загрузка конфигурации
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

def format_time(seconds: float) -> str:
    """Форматирует время в виде mm:ss."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues = {}
        bot.loop.create_task(self.connect_to_nodes())
        self.loop_mode = {}  # none, track, queue
        self.volume_levels = {}
        self.previous_tracks = {}  # История треков для команды back
        # Initialize Spotify client
        self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=config["spotify_client_id"],
            client_secret=config["spotify_client_secret"]
        ))

    async def connect_to_nodes(self):
        """Connect to the Lavalink nodes."""
        await self.bot.wait_until_ready()
        try:
            nodes = [
                wavelink.Node(
                    uri=f'http{"s" if config.get("lavalink_secure") else ""}://{config.get("lavalink_host")}:{config.get("lavalink_port")}',
                    password=config.get("lavalink_password")
                )
            ]
            await wavelink.Pool.connect(nodes=nodes, client=self.bot)
            print("Successfully connected to Lavalink!")
        except Exception as e:
            print(f"Failed to connect to Lavalink: {e}")

    def get_queue(self, guild_id: int):
        """Get or create queue for a guild."""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    async def get_track_info(self, track_title: str):
        """Get track info from Spotify API"""
        try:
            # Search for the track on Spotify
            results = self.sp.search(q=track_title, type='track', limit=1)
            if results['tracks']['items']:
                track = results['tracks']['items'][0]
                return {
                    'title': track['name'],
                    'artist': track['artists'][0]['name'],
                    'album': track['album']['name'],
                    'cover_url': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'spotify_url': track['external_urls']['spotify']
                }
        except Exception as e:
            print(f"Error fetching Spotify info: {e}")
        return None

    async def get_spotify_playlist_tracks(self, playlist_url: str, limit: int = 30):
        """Extract tracks from Spotify playlist"""
        try:
            # Extract playlist ID from URL
            playlist_id = playlist_url.split('playlist/')[1].split('?')[0]
            
            # Get playlist tracks
            results = self.sp.playlist_tracks(playlist_id, limit=limit)
            tracks = []
            
            for item in results['items']:
                track = item['track']
                if track:
                    # Формируем поисковый запрос для каждого трека
                    query = f"{track['name']} {track['artists'][0]['name']}"
                    tracks.append({
                        'query': query,
                        'title': track['name'],
                        'artist': track['artists'][0]['name'],
                        'album': track['album']['name'],
                        'cover_url': track['album']['images'][0]['url'] if track['album']['images'] else None,
                        'spotify_url': track['external_urls']['spotify']
                    })
            return tracks
        except Exception as e:
            print(f"Error fetching Spotify playlist: {e}")
            return None

    async def get_spotify_album_tracks(self, album_url: str):
        """Extract all tracks from Spotify album"""
        try:
            # Extract album ID from URL
            album_id = album_url.split('album/')[1].split('?')[0]
            
            # Get all album tracks
            tracks = []
            results = self.sp.album_tracks(album_id)
            
            # Get album info for cover art and other details
            album_info = self.sp.album(album_id)
            
            while results:
                for item in results['items']:
                    query = f"{item['name']} {item['artists'][0]['name']}"
                    tracks.append({
                        'query': query,
                        'title': item['name'],
                        'artist': item['artists'][0]['name'],
                        'album': album_info['name'],
                        'cover_url': album_info['images'][0]['url'] if album_info['images'] else None,
                        'spotify_url': item['external_urls']['spotify']
                    })
                
                if results['next']:
                    results = self.sp.next(results)
                else:
                    results = None
                    
            return tracks
        except Exception as e:
            print(f"Error fetching Spotify album: {e}")
            return None

    @app_commands.command(name="play", description="Проигрывает музыку или плейлист Spotify")
    @app_commands.describe(
        query="Ссылка на трек/плейлист Spotify или поисковый запрос",
        playlist_limit="Лимит треков для плейлиста (макс. 30)"
    )
    async def play(self, interaction: discord.Interaction, query: str, playlist_limit: int = 30):
        await interaction.response.defer()

        if not interaction.guild.voice_client:
            try:
                channel = interaction.user.voice.channel
                await channel.connect(cls=wavelink.Player)
            except AttributeError:
                await interaction.followup.send("Вы должны быть в голосовом канале!")
                return
            except Exception as e:
                await interaction.followup.send(f"Ошибка подключения: {e}")
                return

        player: wavelink.Player = interaction.guild.voice_client
        queue = self.get_queue(interaction.guild_id)

        # Проверяем, является ли запрос ссылкой на альбом Spotify
        if "open.spotify.com/album" in query:
            tracks_info = await self.get_spotify_album_tracks(query)
            if not tracks_info:
                await interaction.followup.send("Не удалось загрузить альбом Spotify.")
                return

            added_tracks = 0
            embed = discord.Embed(
                title="Добавление альбома",
                description=f"Загрузка {len(tracks_info)} треков...",
                color=discord.Color.blue()
            )
            message = await interaction.followup.send(embed=embed)

            for track_info in tracks_info:
                try:
                    search_results = await wavelink.Playable.search(track_info['query'])
                    if search_results:
                        track = search_results[0]
                        if not player.playing:
                            await player.play(track)
                            player.current_track_info = track_info
                        else:
                            queue.append((track, track_info))
                        added_tracks += 1

                        if added_tracks % 5 == 0:
                            embed.description = f"Добавлено {added_tracks}/{len(tracks_info)} треков..."
                            await message.edit(embed=embed)

                except Exception as e:
                    print(f"Error adding track {track_info['title']}: {e}")
                    continue

            final_embed = discord.Embed(
                title="Альбом добавлен",
                description=f"Успешно добавлено {added_tracks} треков в очередь",
                color=discord.Color.green()
            )
            final_embed.set_footer(text="Made with ❤️ by npcx42")
            await message.edit(embed=embed)
            return

        # Проверяем, является ли запрос ссылкой на плейлист Spotify
        elif "open.spotify.com/playlist" in query:
            # Ограничиваем максимальное количество треков
            playlist_limit = min(playlist_limit, 30)
            
            tracks_info = await self.get_spotify_playlist_tracks(query, playlist_limit)
            if not tracks_info:
                await interaction.followup.send("Не удалось загрузить плейлист Spotify.")
                return

            added_tracks = 0
            embed = discord.Embed(
                title="Добавление плейлиста",
                description="Загрузка треков...",
                color=discord.Color.blue()
            )
            message = await interaction.followup.send(embed=embed)

            for track_info in tracks_info:
                try:
                    # Ищем каждый трек через wavelink
                    search_results = await wavelink.Playable.search(track_info['query'])
                    if search_results:
                        track = search_results[0]
                        if not player.playing:
                            await player.play(track)
                            player.current_track_info = track_info
                        else:
                            queue.append((track, track_info))
                        added_tracks += 1

                        # Обновляем embed каждые 5 треков
                        if added_tracks % 5 == 0:
                            embed.description = f"Добавлено {added_tracks}/{len(tracks_info)} треков..."
                            await message.edit(embed=embed)

                except Exception as e:
                    print(f"Error adding track {track_info['title']}: {e}")
                    continue

            final_embed = discord.Embed(
                title="Плейлист добавлен",
                description=f"Успешно добавлено {added_tracks} треков в очередь",
                color=discord.Color.green()
            )
            final_embed.set_footer(text="Made with ❤️ by npcx42")
            await message.edit(embed=final_embed)
            return

        # Обычное воспроизведение одного трека
        try:
            search = await wavelink.Playable.search(query)
            if not search:
                await interaction.followup.send("Ничего не найдено!")
                return

            track = search[0]
            queue = self.get_queue(interaction.guild_id)
            track_info = await self.get_track_info(track.title)

            if player.playing:
                queue.append(track)
                embed = discord.Embed(
                    title="Трек добавлен в очередь",
                    color=discord.Color.blue()
                )
            else:
                await player.play(track)
                embed = discord.Embed(
                    title="Сейчас играет",
                    color=discord.Color.green()
                )

            if track_info:
                embed.add_field(name="Трек", value=track_info['title'], inline=True)
                embed.add_field(name="Исполнитель", value=track_info['artist'], inline=True)
                embed.add_field(name="Альбом", value=track_info['album'], inline=True)
                if track_info['cover_url']:
                    embed.set_thumbnail(url=track_info['cover_url'])
                embed.url = track_info['spotify_url']
            else:
                embed.description = track.title
            
            embed.set_footer(text="Made with ❤️ by npcx42")  # Добавляем футер
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Произошла ошибка: {e}")

    @app_commands.command(name="skip", description="Пропустить текущий трек")
    async def skip(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("Бот не в голосовом канале!")
            return

        if not player.playing:
            await interaction.response.send_message("Сейчас ничего не играет!")
            return

        await player.stop()
        await interaction.response.send_message("⏭️ Трек пропущен")

    @app_commands.command(name="pause", description="Приостановить воспроизведение")
    async def pause(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            await interaction.response.send_message("Сейчас ничего не играет!")
            return

        await player.pause(not player.paused)
        await interaction.response.send_message(
            "⏸️ Пауза" if player.paused else "▶️ Воспроизведение"
        )

    @app_commands.command(name="queue", description="Показать очередь")
    async def queue(self, interaction: discord.Interaction):
        queue = self.get_queue(interaction.guild_id)
        if not queue:
            await interaction.response.send_message("Очередь пуста!")
            return

        queue_list = "\n".join(
            f"{i+1}. {track[0].title if isinstance(track, tuple) else track.title}" 
            for i, track in enumerate(queue[:10])
        )
        
        if len(queue) > 10:
            queue_list += f"\n...и еще {len(queue) - 10} треков"

        embed = discord.Embed(
            title="Очередь воспроизведения",
            description=queue_list,
            color=discord.Color.blue()
        )
        embed.set_footer(text="Made with ❤️ by npcx42")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stop", description="Остановить воспроизведение и очистить очередь")
    async def stop(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            await interaction.response.send_message("Бот не в голосовом канале!")
            return

        # Очищаем очередь перед отключением
        self.queues[interaction.guild_id] = []
        await player.stop()
        await player.disconnect()
        await interaction.response.send_message("⏹️ Воспроизведение остановлено")

    @app_commands.command(name="seek", description="Перемотать трек на указанную позицию")
    @app_commands.describe(position="Позиция в формате MM:SS или количество секунд")
    async def seek(self, interaction: discord.Interaction, position: str):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return await interaction.response.send_message("Ничего не играет!", ephemeral=True)

        # Конвертируем позицию в миллисекунды
        try:
            if ":" in position:
                minutes, seconds = map(int, position.split(":"))
                pos_ms = (minutes * 60 + seconds) * 1000
            else:
                pos_ms = int(position) * 1000
        except ValueError:
            return await interaction.response.send_message("Неверный формат времени!", ephemeral=True)

        try:
            await player.seek(pos_ms)
            await interaction.response.send_message(f"⏩ Перемотано на позицию {position}")
        except Exception as e:
            await interaction.response.send_message(f"Ошибка при перемотке: {e}", ephemeral=True)

    @app_commands.command(name="loop", description="Включить/выключить повтор")
    @app_commands.describe(mode="Режим повтора")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Выключить", value="none"),
        app_commands.Choice(name="Текущий трек", value="track"),
        app_commands.Choice(name="Очередь", value="queue")
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        guild_id = interaction.guild_id
        self.loop_mode[guild_id] = mode.value
        modes = {"none": "выключен", "track": "повтор трека", "queue": "повтор очереди"}
        await interaction.response.send_message(f"🔄 Режим повтора: {modes[mode.value]}")

    @app_commands.command(name="shuffle", description="Перемешать очередь")
    async def shuffle(self, interaction: discord.Interaction):
        queue = self.get_queue(interaction.guild_id)
        if not queue:
            return await interaction.response.send_message("Очередь пуста!", ephemeral=True)
        
        import random
        random.shuffle(queue)
        await interaction.response.send_message("🔀 Очередь перемешана")

    @app_commands.command(name="remove", description="Удалить трек из очереди")
    @app_commands.describe(position="Позиция трека в очереди")
    async def remove(self, interaction: discord.Interaction, position: int):
        queue = self.get_queue(interaction.guild_id)
        if not queue:
            return await interaction.response.send_message("Очередь пуста!", ephemeral=True)
        
        try:
            removed = queue.pop(position - 1)
            await interaction.response.send_message(f"❌ Удалён трек: {removed.title}")
        except IndexError:
            await interaction.response.send_message("Неверная позиция!", ephemeral=True)

    @app_commands.command(name="clear", description="Очистить очередь")
    async def clear(self, interaction: discord.Interaction):
        self.queues[interaction.guild_id] = []
        await interaction.response.send_message("🧹 Очередь очищена")

    @app_commands.command(name="move", description="Переместить трек в очереди")
    @app_commands.describe(from_pos="Текущая позиция", to_pos="Новая позиция")
    async def move(self, interaction: discord.Interaction, from_pos: int, to_pos: int):
        queue = self.get_queue(interaction.guild_id)
        if not queue:
            return await interaction.response.send_message("Очередь пуста!", ephemeral=True)
        
        try:
            track = queue.pop(from_pos - 1)
            queue.insert(to_pos - 1, track)
            await interaction.response.send_message(f"↕️ Перемещён трек: {track.title}")
        except IndexError:
            await interaction.response.send_message("Неверная позиция!", ephemeral=True)

    @app_commands.command(name="nowplaying", description="Показать текущий трек")
    async def nowplaying(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return await interaction.response.send_message("Ничего не играет!", ephemeral=True)

        track = player.current
        position = player.position
        duration = track.length

        # Создаем прогресс-бар
        bar_length = 20
        filled = int((position / duration) * bar_length)
        progress_bar = "▬" * filled + "🔘" + "▬" * (bar_length - filled)

        # Получаем информацию о треке из Spotify
        track_info = await self.get_track_info(track.title)
        
        embed = discord.Embed(title="Сейчас играет", color=discord.Color.blue())
        
        if track_info:
            embed.add_field(name="Трек", value=track_info['title'], inline=True)
            embed.add_field(name="Исполнитель", value=track_info['artist'], inline=True)
            embed.add_field(name="Альбом", value=track_info['album'], inline=True)
            if track_info['cover_url']:
                embed.set_thumbnail(url=track_info['cover_url'])
            embed.add_field(
                name="Прогресс",
                value=f"`{format_time(position/1000)} {progress_bar} {format_time(duration/1000)}`",
                inline=False
            )
            embed.url = track_info['spotify_url']
            embed.set_footer(text="Made with ❤️ by npcx42")  # Добавляем футер
        else:
            # Fallback if no Spotify info is found
            embed.add_field(name="Трек", value=track.title, inline=False)
            embed.add_field(
                name="Прогресс",
                value=f"`{format_time(position/1000)} {progress_bar} {format_time(duration/1000)}`",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="save", description="Сохранить текущий трек в личные сообщения")
    async def save(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return await interaction.response.send_message("Ничего не играет!", ephemeral=True)

        track = player.current
        # Получаем информацию из Spotify
        track_info = await self.get_track_info(track.title)

        embed = discord.Embed(
            title="💾 Сохранённый трек",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )

        if track_info:
            embed.add_field(name="Название", value=track_info['title'], inline=True)
            embed.add_field(name="Исполнитель", value=track_info['artist'], inline=True)
            embed.add_field(name="Альбом", value=track_info['album'], inline=True)
            embed.add_field(name="Длительность", value=format_time(track.length/1000), inline=True)
            embed.add_field(name="Ссылки", value=f"[YouTube]({track.uri})\n[Spotify]({track_info['spotify_url']})", inline=True)
            
            if track_info['cover_url']:
                embed.set_thumbnail(url=track_info['cover_url'])
        else:
            # Fallback если информация из Spotify недоступна
            embed.add_field(name="Название", value=track.title, inline=True)
            embed.add_field(name="Длительность", value=format_time(track.length/1000), inline=True)
            embed.add_field(name="Ссылка", value=f"[YouTube]({track.uri})", inline=True)

        embed.set_footer(text="Made with ❤️ by npcx42")  # Заменяем существующий футер на новый

        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("✉️ Информация о треке отправлена в личные сообщения!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Не удалось отправить сообщение. Проверьте настройки личных сообщений.", ephemeral=True)

    @app_commands.command(name="lyrics", description="Поиск текста песни")
    async def lyrics(self, interaction: discord.Interaction, query: str = None):
        player: wavelink.Player = interaction.guild.voice_client
        if not query and (not player or not player.playing):
            return await interaction.response.send_message("Укажите название песни или включите музыку!", ephemeral=True)

        search_query = query or player.current.title
        # Здесь можно добавить интеграцию с Genius API для поиска текста

        await interaction.response.send_message("🎵 Функция поиска текста песни находится в разработке")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        """Обработчик окончания трека"""
        player = payload.player
        guild_id = player.guild.id

        # Проверяем существование очереди для гильдии
        if guild_id not in self.queues:
            return

        if not player.playing and self.queues[guild_id]:
            loop_mode = self.loop_mode.get(guild_id, "none")
            queue = self.get_queue(guild_id)

            try:
                if loop_mode == "track" and player.current:
                    await player.play(player.current)
                elif loop_mode == "queue" and queue:
                    track = queue.pop(0)
                    if isinstance(track, tuple):
                        await player.play(track[0])
                        queue.append(track)
                    else:
                        await player.play(track)
                        queue.append(track)
                elif queue:
                    track = queue.pop(0)
                    if isinstance(track, tuple):
                        await player.play(track[0])
                    else:
                        await player.play(track)
            except Exception as e:
                print(f"Error in track_end handler: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
