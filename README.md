# 🍽️ Perfect Restaurant Bot

**COMPLETE REPOSITORY REWRITE - Bothost deployment**

Telegram бот для выбора ресторанов с системой статистики и отзывов.

## 🚀 **Быстрый старт на Bothost:**

### **Настройка бота:**
1. **Bot Token**: `8245055843:AAEpOGcGRbvy1TkfQx4Jj2rAqQB15CbxQp0`
2. **Git URL**: `https://github.com/vakjlksjkds/restoran.git`
3. **Ветка**: `main`

### **Переменные окружения:**
```env
BOT_TOKEN=8245055843:AAEpOGcGRbvy1TkfQx4Jj2rAqQB15CbxQp0
ADMIN_USER_ID=800133246
GROUP_CHAT_ID=-1001234567890
```

## 📋 **Команды бота:**
- `/start` - Начать работу с ботом
- `/random` - Выбрать случайный ресторан
- `/stats` - Показать статистику
- `/next_event` - Проверить ближайшее событие
- `/cancel_event` - Отменить событие (только админ)
- `/clear_reviews` - Удалить все отзывы (только админ)

## 🎯 **Особенности:**
- Группа из 3 человек + бот
- Последовательные отзывы от каждого участника
- Автоматические уведомления
- Система статистики
- Админские команды

## 📁 **Структура проекта:**
```
├── perfect_bot.py          # Основной файл бота
├── notifications.py        # Система уведомлений
├── restaurants.json        # База ресторанов
├── requirements.txt        # Зависимости
├── Dockerfile             # Docker конфигурация
└── README.md              # Документация
```

**Готово к развертыванию на Bothost!** 🎉