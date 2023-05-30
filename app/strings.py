COMMANDS = {
    "new": {
        "ru": "Начать новый диалог",
        "en": "Start new dialog"
    },
    "mode": {
        "ru": "Выбрать режим чата",
        "en": "Select chat mode"
    },
    "retry": {
        "ru": "Повторно сгенерировать ответ на предыдущий запрос",
        "en": "Re-generate response for previous query"
    },
    "balance": {
        "ru": "Показать баланс",
        "en": "Show balance"
    },
    "link": {
        "ru": "Сгенерировать реферальную ссылку",
        "en": "Generate referral link"
    },
    "settings": {
        "ru": "Показать настройки",
        "en": "Show settings"
    },
    "help": {
        "ru": "Помощь",
        "en": "Show help message"
    }
}

HELP_MESSAGE_EN = f"""Commands:
⚪ /retry – {COMMANDS["retry"]['en']}
⚪ /new – {COMMANDS["new"]['en']}
⚪ /mode – {COMMANDS["mode"]['en']}
⚪ /settings – {COMMANDS["settings"]['en']}
⚪ /balance – {COMMANDS["balance"]['en']}
⚪ /link – {COMMANDS["link"]['en']}
⚪ /help – {COMMANDS["help"]['en']}

🎨 Generate images from text prompts in <b>👩‍🎨 Artist</b> /mode
👥 Add app to <b>group chat</b>: /help_group_chat
🎤 You can send <b>Voice Messages</b> instead of text
"""

HELP_MESSAGE_RU = f"""Команды:
⚪ /retry – {COMMANDS["retry"]['ru']}
⚪ /new – {COMMANDS["new"]['ru']}
⚪ /mode – {COMMANDS["mode"]['ru']}
⚪ /settings – {COMMANDS["settings"]['ru']}
⚪ /balance – {COMMANDS["balance"]['ru']}
⚪ /link – {COMMANDS["link"]['ru']}
⚪ /help – {COMMANDS["help"]['ru']}

🎨 Генерируйте изображения из текстовых сообщений в режиме <b>👩🎨 Художник</b> /mode
👥 Добавьте приложение в <b>групповой чат</b>: /help_group_chat
🎤 Вы можете отправлять <b>Голосовые сообщения</b> вместо текстовых
"""

HELP_GROUP_CHAT_MESSAGE_EN = """You can add app to any <b>group chat</b> to help and entertain its participants!

Instructions (see <b>video</b> below):
1. Add the app to the group chat
2. Make it an <b>admin</b>, so that it can see messages (all other rights can be restricted)
3. You're awesome!

To get a reply from the app in the chat – @ <b>tag</b> it or <b>reply</b> to its message.
For example: "{bot_username} write a poem about Telegram"
"""

HELP_GROUP_CHAT_MESSAGE_RU = """Вы можете добавить приложение в любой групповой чат, чтобы помочь или развлечь его участников!

Инструкция (смотрите <b>видео</b> ниже):
1. Добавьте приложение в групповой чат
2. Сделайте его <b>администратором</b>, чтобы он мог видеть сообщения (все остальные права могут быть ограничены)
3. Ты потрясающий!

Чтобы получить ответ от приложения в чате – @<b>отметьте</b> его или <b>ответьте</b> на его сообщение.
Например: "{bot_username} напиши стих о Telegram"
"""

HELLO = {
    "ru": "Привет! Я - приложение <b>ChatGPT</b>, реализованное с помощью OpenAI API 🤖\n\n",
    "en": "Hi! I'm <b>ChatGPT</b> app implemented with OpenAI API 🤖\n\n"
}

HELP_MESSAGE = {
    "ru": HELP_MESSAGE_RU,
    "en": HELP_MESSAGE_EN
}

HELP_GROUP_CHAT_MESSAGE = {
    "ru": HELP_GROUP_CHAT_MESSAGE_RU,
    "en": HELP_GROUP_CHAT_MESSAGE_EN
}

NO_RETRY = {
    "ru": "Нет сообщений для повтора 🤷‍♂️",
    "en": "No message to retry 🤷‍♂️"
}

LIMIT = {
    "ru": "Достигнут лимит сообщений",
    "en": "Message limit reached"
}

DIALOG_TIMEOUT = {
    "ru": "Запуск нового диалога из-за тайм-аута",
    "en": "Starting new dialog due to timeout"
}

EMPTY_MESSAGE = {
    "ru": "🥲 Вы отправили <b>пустое сообщение</b>. Пожалуйста, попробуйте еще раз!",
    "en": "🥲 You sent <b>empty message</b>. Please, try again!"
}

ERROR = {
    "ru": "Что-то пошло не так во время выполнения. Причина:",
    "en": "Something went wrong during completion. Reason:"
}

TOO_LONG_DIALOG = {
    "ru": "✍️ <i>Примечание:</i> Ваш текущий диалог слишком длинный, поэтому ваше <b>первое сообщение</b> было удалено из контекста.\n Отправьте команду /new для запуска нового диалога",
    "en": "✍️ <i>Note:</i> Your current dialog is too long, so your <b>first message</b> was removed from the context.\n Send /new command to start new dialog"
}

TOO_LONG_DIALOG_WITH_NUMBER = {
    "ru": "✍️ <i>Примечание:</i> Ваш текущий диалог слишком длинный, поэтому <b>{number} первых сообщений</b> были удалены из контекста.\n Отправьте команду /new для запуска нового диалога",
    "en": "✍️ <i>Note:</i> Your current dialog is too long, so <b>{number} first messages</b> were removed from the context.\n Send /new command to start new dialog"
}

CANCELED = {
    "ru": "✅ Отменено",
    "en": "✅ Canceled"
}

PLEASE_WAIT = {
    "ru": "⏳ Пожалуйста, <b>дождитесь</b> ответа на предыдущее сообщение\nИли вы можете отменить его командой /cancel",
    "en": "⏳ Please <b>wait</b> for a reply to the previous message\nOr you can /cancel it"
}

GENERATE_IMAGE_ERROR = {
    "ru": "🥲 Ваш запрос <b>не соответствует</b> политике использования OpenAI.\nЧто ты там написал, а?",
    "en": "🥲 Your request <b>doesn't comply</b> with OpenAI's usage policies.\nWhat did you write there, huh?"
}

START_NEW_DIALOG = {
    "ru": "Запуск нового диалога ✅",
    "en": "Starting new dialog ✅"
}

NOTHING_TO_CANCEL = {
    "ru": "<i>Нечего отменять...</i>",
    "en": "<i>Nothing to cancel...</i>"
}

SELECT_CHAT_MODE = {
    "ru": "Выберите <b>режим чата</b> ({number} режимов доступно):",
    "en": "Select <b>chat mode</b> ({number} modes available):"
}

TRIAL_VERSION = {
    "ru": "Вы используете пробную версию!\nВы потратили {number}/{limit} бесплатных запросов\n\nЧтобы получить полную версию, вам нужно пригласить {invited}/{required} друзей",
    "en": "You use the trial version!\nYou spent {number}/{limit} free requests\n\nTo get the full version, you need to invite {invited}/{required} your friends"
}

FULL_VERSION = {
    "ru": "Вы используете полную версию!\nВы потратили {number} запросов",
    "en": "You use the full version!\nYou spent {number} requests"
}

REFERRAL_LINK = {
    "ru": "Ваша личная ссылка для приглашения друзей:\n",
    "en": "Your personal link to invite friends:\n"
}

EDITING_NOT_SUPPORTED = {
    "ru": "🥲 К сожалению, <b>редактирование</b> сообщений не поддерживается",
    "en": "🥲 Unfortunately, message <b>editing</b> is not supported"
}

SELECT_MODEL = {
    "ru": "\nВыберите <b>модель</b>:",
    "en": "\nSelect <b>model</b>:"
}
