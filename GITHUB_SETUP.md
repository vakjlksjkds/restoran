# 🐙 Настройка GitHub репозитория

## 📋 Инструкции по загрузке на GitHub

### 1. Создайте репозиторий на GitHub

1. Перейдите на [GitHub.com](https://github.com)
2. Нажмите кнопку **"New"** или **"+"** → **"New repository"**
3. Заполните данные:
   - **Repository name**: `restaurant-bot` (или любое другое название)
   - **Description**: `🍽️ Telegram bot for restaurant selection with reviews and statistics`
   - **Visibility**: `Public` или `Private` (на ваш выбор)
   - **НЕ** добавляйте README, .gitignore или лицензию (они уже есть)
4. Нажмите **"Create repository"**

### 2. Подключите локальный репозиторий

После создания репозитория GitHub покажет команды. Выполните их:

```bash
# Добавьте remote origin (замените YOUR_USERNAME на ваш GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/restaurant-bot.git

# Переименуйте ветку в main (если нужно)
git branch -M main

# Загрузите код на GitHub
git push -u origin main
```

### 3. Альтернативный способ (если у вас есть SSH ключи)

```bash
# Для SSH (если настроены SSH ключи)
git remote add origin git@github.com:YOUR_USERNAME/restaurant-bot.git
git branch -M main
git push -u origin main
```

## 🔐 Настройка переменных окружения

После загрузки на GitHub:

1. **Создайте .env файл локально:**
   ```bash
   cp env.example .env
   ```

2. **Заполните .env файл:**
   ```env
   BOT_TOKEN=your_bot_token_here
   ADMIN_USER_ID=your_telegram_id
   GROUP_CHAT_ID=your_group_chat_id
   ```

3. **НЕ коммитьте .env файл** - он уже в .gitignore

## 🚀 Развертывание

После загрузки на GitHub вы можете развернуть бота:

### Docker:
```bash
git clone https://github.com/YOUR_USERNAME/restaurant-bot.git
cd restaurant-bot
cp env.example .env
# Отредактируйте .env
docker-compose up -d
```

### Systemd:
```bash
git clone https://github.com/YOUR_USERNAME/restaurant-bot.git
cd restaurant-bot
cp env.example .env
# Отредактируйте .env
sudo ./deploy.sh systemd
```

## 📝 Дополнительные настройки

### GitHub Actions (опционально)
Можете добавить автоматическое развертывание через GitHub Actions.

### GitHub Pages (опционально)
Можете создать документацию на GitHub Pages.

## ✅ Проверка

После загрузки проверьте:
- [ ] Все файлы загружены
- [ ] README.md отображается корректно
- [ ] .env файл НЕ загружен (безопасность)
- [ ] Репозиторий публичный/приватный по желанию
