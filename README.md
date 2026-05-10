# Tidal Downloader (Docker)

Контейнеризированная версия [tiddl](https://github.com/oskvr37/tiddl) — CLI-утилиты для скачивания треков и экспорта коллекции из Tidal. Работает в OrbStack / Docker.

## Структура проекта

```
tiddl/
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── data/                    # Персистентные данные (volume)
│   ├── tiddl/
│   │   ├── config.toml      # Конфигурация tiddl
│   │   ├── auth.json        # Токены авторизации (создаётся при логине)
│   │   └── api_cache.sqlite # Кэш API-запросов
│   ├── Music/               # Скачанная музыка
│   ├── mixes.txt            # Список URL миксов для daily-экспорта
│   ├── artist_blocklist.txt # Блоклист артистов (один на строку)
│   ├── artist_aliases.txt  # Алиасы артистов (Name = Alias)
│   ├── all_tracks.txt       # Все треки из миксов (экспорт, без заблокированных)
│   ├── DailyTidal.txt       # Случайная подборка 100 треков
│   └── NewTidal.txt         # Новые треки с Tidal Home
└── tiddl/                   # Исходный код (форк)

Внешние пути (монтируются как /music):
├── DailyTidal/              # Скачанные daily-треки (не из библиотеки)
├── ReleaseRadar/            # Скачанные radar-треки
├── Playlists/
│   ├── Daily_Tidal.nsp      # Navidrome Smart Playlist
│   └── Release Radar.nsp    # Navidrome Smart Playlist
└── library_index.json       # Индекс существующей коллекции
```

## Сводка команд

Все команды выполняются через `docker compose run --rm tiddl`. Флаг `--rm` удаляет контейнер после выполнения, данные сохраняются в `./data/`.

```bash
# Авторизация
tiddl auth login                                              # Первый вход
tiddl auth refresh                                            # Обновить токен

# Экспорт
tiddl export daily                                            # My Mix 1-8 → all_tracks.txt + DailyTidal.txt (100 треков)
tiddl export new-tracks -o NewTidal.txt                       # New Tracks с Tidal Home → NewTidal.txt
tiddl export playlist <url> -o tracks.txt                     # Микс/плейлист → текстовый файл

# Скачивание
tiddl download url <url>                                      # Трек / альбом / плейлист / микс
tiddl download -q normal -p /data/DailyTidal from-file <txt>  # Из текстового списка

# Синхронизация (экспорт + проверка библиотеки + скачивание + NSP)
tiddl sync daily                                              # Daily Tidal одной командой
tiddl sync radar                                              # Release Radar одной командой

# Автоматизация (скрипт)
./sync_daily.sh daily                                         # Запуск Daily вручную
./sync_daily.sh radar                                         # Запуск Radar вручную
./sync_daily.sh all                                           # Обе задачи
```

## Запуск

### Авторизация

При первом запуске требуется авторизация в Tidal:

```bash
docker compose run --rm tiddl auth login
```

Появится ссылка — откройте её в браузере и подтвердите вход. Токен сохранится в `data/tiddl/auth.json` и переиспользуется при последующих запусках.

Обновить токен:

```bash
docker compose run --rm tiddl auth refresh
```

Выйти:

```bash
docker compose run --rm tiddl auth logout
```

### Скачивание

Скачать трек / альбом / плейлист / микс по URL:

```bash
docker compose run --rm tiddl download url "https://tidal.com/browse/track/103805726"
docker compose run --rm tiddl download url "https://tidal.com/browse/album/103805723"
```

Допускается сокращённый формат: `track/103805726`, `album/103805723`.

Дополнительные опции скачивания:

```bash
# Качество (low / normal / high / max)
docker compose run --rm tiddl download url <url> -q max

# Кастомный путь
docker compose run --rm tiddl download url <url> -p "/data/Music/Albums"

# Шаблон имени файла
docker compose run --rm tiddl download url <url> -o "{album.artist}/{album.title}/{item.number:02d}. {item.title}"

# Скачать из избранного
docker compose run --rm tiddl download fav

# Поиск и скачивание
docker compose run --rm tiddl download search "Pink Floyd"
```

Музыка сохраняется в `data/Music/`.

### Скачивание из текстового списка

Команда `download from-file` читает файл с треками в формате `artist - title` (один на строку), ищет каждый на Tidal и скачивает первый совпадающий результат.

```bash
# DailyTidal.txt → папка DailyTidal, качество Normal (AAC 320kbps)
docker compose run --rm tiddl download -q normal -p /data/DailyTidal -o "{item.artists} - {item.title}" --dolby-atmos allow from-file DailyTidal.txt

# NewTidal.txt → папка NewTidal, качество Normal
docker compose run --rm tiddl download -q normal -p /data/NewTidal -o "{item.artists} - {item.title}" --dolby-atmos allow from-file NewTidal.txt
```

Опции скачивания задаются на уровне команды `download`:

| Опция | Описание |
|-------|----------|
| `-q normal` | AAC 320kbps (.m4a) |
| `-q high` | FLAC 16-bit |
| `-q max` | FLAC до 24-bit |
| `-p /data/имя` | Папка для скачивания |
| `-o "шаблон"` | Шаблон имени файла |
| `--dolby-atmos allow` | Не пропускать Dolby Atmos треки |

### Экспорт треков

Команда `export` формирует текстовые списки треков в формате `artist - title`.

#### Экспорт плейлиста или микса

```bash
# По URL (автоматически определяет тип: playlist / mix)
docker compose run --rm tiddl export playlist "https://tidal.com/mix/002e97fa4491895af2359ec016eb34" -o tracks.txt

# По UUID
docker compose run --rm tiddl export playlist "002e97fa4491895af2359ec016eb34" -o tracks.txt
```

#### Daily-подборка из миксов

Создайте файл `data/mixes.txt` со ссылками на миксы (одна на строку):

```
https://tidal.com/mix/002031a111d26d855f13df60ef8035
https://tidal.com/mix/0020a08efcb74f0b86c8363bf5efae
https://tidal.com/mix/002a3c2e11ce412d0ca12bb451730f
```

При необходимости создайте файл `data/artist_blocklist.txt` с именами артистов (один на строку), чьи треки нужно исключить:

```
Taylor Swift
Eminem
```

Запустите экспорт:

```bash
docker compose run --rm tiddl export daily
```

Результат:
- `data/all_tracks.txt` — уникальные треки из всех миксов (без заблокированных артистов)
- `data/DailyTidal.txt` — 100 случайных треков из отфильтрованного списка

Опции:

| Опция | По умолчанию | Описание |
|-------|-------------|----------|
| `-i` | `mixes.txt` | Файл со списком URL |
| `-n` | `100` | Количество треков в daily-подборке |
| `-o` | `all_tracks.txt` | Файл со всеми треками |
| `-d` | `DailyTidal.txt` | Файл с daily-подборкой |
| `-b` | `artist_blocklist.txt` | Файл с блоклистом артистов |

Пример с кастомными параметрами:

```bash
docker compose run --rm tiddl export daily -i my_mixes.txt -n 50 -o full.txt -d daily50.txt -b my_blocklist.txt
```

#### Новые треки (New Tracks Suggestions)

Экспортирует список "New Tracks" с главной страницы Tidal:

```bash
docker compose run --rm tiddl export new-tracks -o NewTidal.txt
```

### Синхронизация (sync daily)

Команда `sync daily` — полноценный пайплайн для daily-подборки:

1. Читает `DailyTidal.txt` (список `artist - title`)
2. Проверяет каждый трек по `library_index.json` — если трек уже в коллекции, он не скачивается, но добавляется в плейлист по прямому пути
3. Недостающие треки ищутся на Tidal и скачиваются в папку `/music/DailyTidal/`
4. Генерируется Navidrome Smart Playlist (`Daily_Tidal.nsp`) с ссылками на оба типа треков

При поиске в библиотеке нормализация совпадает с `scan_library.py` из spotify-soulseek-bridge: убираются пометки (Remastered, Radio Edit, feat. и т.д.), ключ формируется как `artist - title` в нижнем регистре.

Если у артиста есть альтернативное имя (переименование группы, транслитерация), создайте файл `data/artist_aliases.txt`:

```
Electric Callboy = Eskimo Callboy
```

Формат: `Имя = Алиас`, по одной паре на строку. Алиасы двунаправленные.

```bash
docker compose run --rm tiddl sync daily
```

Опции:

| Опция | По умолчанию | Описание |
|-------|-------------|----------|
| `-i` | `DailyTidal.txt` | Входной файл со списком треков |
| `-l` | `/music/library_index.json` | Путь к индексу библиотеки |
| `-a` | `artist_aliases.txt` | Файл алиасов артистов |
| `-p` | `/music/DailyTidal` | Папка для скачивания новых треков |
| `--music-base` | `/Volumes/DeliRAID5/Media/Music` | Базовый путь Navidrome (обрезается из путей в NSP) |
| `-n` | `/music/Playlists/Daily_Tidal.nsp` | Путь к NSP-плейлисту |
| `-f` | `DailyTidal/` | Префикс папки в NSP для скачанных треков |
| `-q` | `normal` | Качество скачивания |
| `-t` | `4` | Количество потоков скачивания |
| `--dolby-atmos` | `allow` | Фильтр Dolby Atmos |

Плейлист содержит:
- `startsWith: DailyTidal/` — все скачанные треки
- `is: <путь из библиотеки>` — треки, найденные в коллекции

### Синхронизация (sync radar)

Команда `sync radar` — пайплайн для Release Radar:

1. Забирает "New Tracks" с главной Tidal (встроенный `export new-tracks`)
2. Проверяет каждый трек по `library_index.json`
3. Скачивает недостающие в `/music/ReleaseRadar/`
4. Обновляет NSP-плейлист

Всё одной командой:

```bash
docker compose run --rm tiddl sync radar
```

Опции те же, что и у `sync daily`, но с другими значениями по умолчанию:

| Опция | По умолчанию | Описание |
|-------|-------------|----------|
| `-o` | `NewTidal.txt` | Временный файл экспорта |
| `-p` | `/music/ReleaseRadar` | Папка для скачивания |
| `-n` | `/music/Playlists/Release Radar.nsp` | Путь к NSP |
| `-f` | `ReleaseRadar/` | Префикс папки в NSP |

## Автоматизация

Скрипт `sync_daily.sh` принимает аргумент: `daily`, `radar` или `all`.

| Задача | Расписание | Команда |
|--------|-----------|---------|
| Daily (`export daily` + `sync daily`) | Каждый день в 5:00, выполняется раз в 3 дня | `sync_daily.sh daily` |
| Radar (`sync radar`) | Каждое воскресенье в 5:00 | `sync_daily.sh radar` |
| Обе сразу | — | `sync_daily.sh all` |

Лог пишется в `data/sync.log`.

### Установка через launchd

Два plist — отдельное расписание для каждой задачи:

```bash
# Установить оба
cp com.tiddl.sync-daily.plist com.tiddl.sync-radar.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.tiddl.sync-daily.plist
launchctl load ~/Library/LaunchAgents/com.tiddl.sync-radar.plist

# Проверить статус
launchctl list | grep tiddl

# Удалить
launchctl unload ~/Library/LaunchAgents/com.tiddl.sync-daily.plist
launchctl unload ~/Library/LaunchAgents/com.tiddl.sync-radar.plist
rm ~/Library/LaunchAgents/com.tiddl.sync-daily.plist ~/Library/LaunchAgents/com.tiddl.sync-radar.plist
```

### Принудительный запуск

```bash
/Volumes/DeliRAID5/Dockers/tiddl/sync_daily.sh daily   # только Daily
/Volumes/DeliRAID5/Dockers/tiddl/sync_daily.sh radar   # только Radar
/Volumes/DeliRAID5/Dockers/tiddl/sync_daily.sh all     # обе задачи
```

## Конфигурация

Файл `data/tiddl/config.toml`. Ключевые параметры:

```toml
[download]
track_quality = "high"       # low / normal / high / max
download_path = "/data/Music"
skip_existing = true
threads_count = 4

[metadata]
enable = true
```

Полный пример конфигурации — в [docs/config.example.toml](docs/config.example.toml).

## Качество аудио

| Качество | Формат | Параметры |
|----------|--------|-----------|
| LOW | .m4a | 96 kbps |
| NORMAL | .m4a | 320 kbps |
| HIGH | .flac | 16-bit, 44.1 kHz |
| MAX | .flac | до 24-bit, 192 kHz |

## Внесённые изменения в оригинальный tiddl

1. **`tiddl/core/auth/models.py`** — поле `facebookUid` сделано опциональным (`Optional[int] = None`), т.к. Tidal API перестал возвращать его
2. **`tiddl/cli/commands/export.py`** — добавлена команда `export` с подкомандами:
   - `playlist` — экспорт плейлиста/микса в текстовый файл
   - `daily` — экспорт треков из нескольких миксов + случайная подборка
   - `new-tracks` — экспорт "New Tracks" с главной страницы Tidal
3. **`tiddl/cli/commands/subcommands/from_file.py`** — добавлена подкоманда `download from-file`: скачивание треков из текстового списка `artist - title`
4. **`tiddl/cli/commands/__init__.py`** — зарегистрированы команды `export` и `sync`
5. **`tiddl/cli/commands/sync.py`** — добавлены команды `sync daily` и `sync radar`: проверка по library_index.json, скачивание недостающих треков, генерация NSP-плейлистов
6. **`Dockerfile`** — обновлён: Python 3.13 Alpine, ffmpeg, `TIDDL_PATH=/data/tiddl`, `ENTRYPOINT ["tiddl"]`
7. **`docker-compose.yml`** — volumes: `./data:/data`, `/Volumes/DeliRAID5/Media/Music:/music`; tty + stdin_open для интерактива
8. **`.dockerignore`** — исключает `data/` из контекста сборки
9. **`sync_daily.sh`** + **`com.tiddl.sync-*.plist`** — автоматизация через launchd: Daily каждые 3 дня, Radar по воскресеньям
