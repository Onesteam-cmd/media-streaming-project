# Media Streaming Project

Локальный self-hosted сервис для поиска, подготовки, хранения и просмотра медиаконтента. Проект объединяет backend API, медиасервер, загрузчик, поисковые адаптеры и клиентское приложение в одном Docker Compose окружении.

> Проект предназначен для личной инфраструктуры и работы с контентом, который пользователь имеет право получать и хранить. Подключение источника не означает разрешения на загрузку защищённых материалов.

## Реализованные возможности

- поиск по одному или нескольким подключённым адаптерам;
- локальный демонстрационный каталог и интеграция с Internet Archive;
- интеграция с Jackett для получения поисковых результатов;
- ранжирование результатов по качеству, аудиодорожке, размеру и доступности;
- предварительная оценка времени загрузки;
- создание, обновление и отмена заявок на подготовку контента;
- интеграция с Transmission и отображение прогресса, скорости, ETA и числа пиров;
- импорт готового видео в локальную медиатеку;
- анализ файла через `ffprobe` и конвертация несовместимых форматов через `ffmpeg`;
- интеграция с Jellyfin и запуск сканирования библиотеки;
- регистрация, вход, серверные сессии, смена пароля и отзыв сессий;
- раздельные пользовательские заявки, медиатека и позиции просмотра;
- защищённая выдача видео через временные stream-токены;
- мобильный и web-клиент на Expo/React Native;
- reverse proxy и раздача web-клиента через Nginx;
- вспомогательные проверки и сценарии локальной разработки.

## Архитектура

```text
Expo / React Native client
          │
          ▼
       Nginx
          │
          ▼
     FastAPI backend ───── SQLite
          │
          ├──── search adapters
          │       ├─ local_demo
          │       ├─ Internet Archive
          │       └─ Jackett
          │
          ├──── Transmission
          ├──── FFmpeg / FFprobe
          └──── Jellyfin
                    │
                    ▼
              media/movies
```

Backend не привязан к одному источнику. Поиск и подготовка контента реализованы через адаптеры, а состояние кандидатов, заявок, загрузок, пользователей и позиций просмотра хранится в SQLite.

## Технологии

- Python 3.12, FastAPI, Pydantic, SQLAlchemy и SQLite;
- React Native, Expo, TypeScript и Expo Video;
- Docker Compose;
- Jellyfin;
- Transmission;
- Jackett и FlareSolverr;
- FFmpeg / FFprobe;
- Nginx;
- WSL2 для локальной Linux-среды.

## Структура проекта

```text
backend/       FastAPI API, модели, адаптеры и сервисы
catalogs/      демонстрационные каталоги
mobile/        Expo / React Native клиент
nginx/         reverse proxy и раздача web-клиента
scripts/       проверки, сборка и вспомогательные команды
media/         локальная медиатека; файлы не попадают в Git
jellyfin/      локальные данные Jellyfin; не попадают в Git
transmission/  конфигурация и загрузки; не попадают в Git
jackett/       локальная конфигурация Jackett; не попадает в Git
```

## Требования

Для основного локального запуска нужны:

- Docker Desktop с Docker Compose;
- WSL2 с Ubuntu — рекомендуемая среда для Windows;
- Git;
- Node.js и npm — только для разработки или пересборки клиента.

## Первичная настройка

Скопировать шаблон переменных окружения:

```bash
cp .env.example .env
```

Затем заполнить в `.env` только локальные значения. Как минимум могут понадобиться:

```env
JELLYFIN_API_KEY=
JACKETT_API_KEY=
REGISTRATION_INVITE_CODE=
MEDIA_PUBLIC_BASE_URL=
```

Файл `.env` содержит секреты и не должен добавляться в Git.

## Запуск backend-инфраструктуры

```bash
docker compose up --build -d
```

Проверить контейнеры:

```bash
docker compose ps
```

После сборки web-клиент и API доступны через Nginx:

```text
http://localhost:8091
http://localhost:8091/health
http://localhost:8091/api/readiness
```

Управляющие порты Jellyfin, Transmission и Jackett по умолчанию не публикуются наружу. Это сделано намеренно. Для первой настройки можно временно добавить локальные port mappings в отдельный Compose override, затем удалить их.

## Web-клиент

Установить зависимости один раз:

```bash
cd mobile
npm ci
cd ..
```

Собрать web-версию и перезапустить Nginx:

```bash
./scripts/build_web_app.sh
```

## Мобильная разработка

Обычный запуск Expo:

```bash
cd mobile
npm ci
npm start
```

Для запуска через Tailscale IP задаётся явно:

```bash
TAILSCALE_IP=100.x.y.z ./scripts/start_mobile_tailscale.sh
```

Идентификатор EAS-проекта намеренно не хранится в публичной версии. Для собственного EAS-проекта выполните настройку Expo/EAS в своей учётной записи.

## Основные API

Полная интерактивная схема доступна через Swagger при прямом доступе к backend или через настроенный proxy.

Ключевые группы endpoints:

```text
GET    /health
GET    /api/readiness
POST   /api/auth/register
POST   /api/auth/login
GET    /api/auth/me
POST   /api/auth/logout
POST   /api/auth/logout-all
POST   /api/auth/change-password
POST   /api/search
POST   /api/search/all
GET    /api/candidates
GET    /api/requests
POST   /api/requests
POST   /api/requests/{id}/refresh
POST   /api/requests/{id}/cancel
GET    /api/media/prepared
GET    /api/media/stream/{candidate_id}
DELETE /api/media/prepared/{candidate_id}
GET    /api/watch-positions
PUT    /api/watch-positions/{media_id}
GET    /api/transmission/status
GET    /api/transmission/torrents
GET    /api/jellyfin/status
GET    /api/jellyfin/libraries
POST   /api/jellyfin/scan
```

Большинство служебных endpoints требуют авторизацию.

## Проверка проекта

После запуска сервисов выполнить:

```bash
PROJECT_CHECK_USERNAME=<имя> \
PROJECT_CHECK_PASSWORD=<пароль> \
./scripts/project_check.sh
```

Либо передать уже полученный токен:

```bash
PROJECT_CHECK_AUTH_TOKEN=<token> ./scripts/project_check.sh
```

Проверка охватывает readiness, адаптеры, Jellyfin, Transmission, кандидатов, заявки, медиатеку и позиции просмотра.

## Локальные данные и безопасность

В репозиторий не включаются:

- `.env` и API-ключи;
- SQLite-база;
- конфигурации Jellyfin, Transmission и Jackett;
- загруженные и подготовленные видео;
- Expo cache, `node_modules` и результаты сборки;
- персональные Tailscale IP и EAS project ID.

Перед открытием сервиса за пределами доверенной локальной сети необходимо отдельно настроить TLS, ограничение origin, управление секретами и сетевую изоляцию.

## Текущий статус

Проект представляет собой рабочий локальный прототип. Основной end-to-end поток реализован, но для развёртывания из чистой копии ещё требуются ручная первичная настройка внешних сервисов и локальные API-ключи.
