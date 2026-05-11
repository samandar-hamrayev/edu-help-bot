# Edu Help Bot

A Telegram bot for educational support, backed by a **Django admin panel** for content management. Students interact through Telegram while administrators manage content via a web interface.

## Features

- Telegram bot interface (Aiogram 3.x)
- Django 5 admin panel with a modern UI (django-unfold)
- PostgreSQL database
- Nginx reverse proxy
- Fully containerized with Docker + docker-compose

## Tech Stack

| Component | Technology |
|-----------|------------|
| Bot framework | Aiogram 3.x |
| Admin backend | Django 5 + django-unfold |
| Database | PostgreSQL (psycopg 3) |
| Container | Docker + docker-compose + Nginx |
| Runtime | Python 3.11+ |

## Setup

### 1. Clone

```bash
git clone https://github.com/samandar-hamrayev/edu-help-bot.git
cd edu-help-bot
```

### 2. Configure environment

Create a `.env` file:

```env
BOT_TOKEN=your-telegram-bot-token
SECRET_KEY=your-django-secret-key
DEBUG=False
POSTGRES_DB=edu_bot
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
ALLOWED_HOSTS=localhost
```

### 3. Start with Docker

```bash
docker-compose up --build
```

### 4. Create Django superuser

```bash
docker-compose exec web python manage.py createsuperuser
# Admin panel: http://localhost/admin/
```

### 5. Run locally (without Docker)

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver &   # Django admin
python run_bot.py               # Telegram bot
```

## Project Structure

```
edu-help-bot/
├── bot/           # Aiogram bot handlers
├── core/          # Django app (models, views)
├── config/        # Django settings
├── nginx/         # Nginx configuration
├── run_bot.py     # Bot entry point
├── manage.py
├── Dockerfile
└── docker-compose.yml
```

## License

MIT
