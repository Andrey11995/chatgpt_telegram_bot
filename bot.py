import logging
import asyncio
import traceback
import html
import json
import tempfile
import pydub
from pathlib import Path
from datetime import datetime
import openai

import telegram
from telegram import (
    Update,
    User,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    AIORateLimiter,
    filters
)
from telegram.constants import ParseMode

from app import settings
from app.database import Database
from app.openai_utils import ChatGPT, generate_images, transcribe_audio
from app.strings import *

# setup
db = Database()
logger = logging.getLogger(__name__)

user_semaphores = {}
user_tasks = {}


def split_text_into_chunks(text, chunk_size):
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


def set_commands(language='en'):
    return [
        BotCommand("/new", COMMANDS["new"][language]),
        BotCommand("/mode", COMMANDS["mode"][language]),
        BotCommand("/retry", COMMANDS["retry"][language]),
        BotCommand("/balance", COMMANDS["balance"][language]),
        BotCommand("/link", COMMANDS["link"][language]),
        BotCommand("/settings", COMMANDS["settings"][language]),
        BotCommand("/help", COMMANDS["help"][language]),
    ]


async def register_user_if_not_exists(update: Update, context: CallbackContext, user: User):
    if not db.check_if_user_exists(user.id):
        db.add_new_user(
            user.id,
            update.message.chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name= user.last_name
        )
        db.start_new_dialog(user.id)

    if db.get_user_attribute(user.id, "current_dialog_id") is None:
        db.start_new_dialog(user.id)

    if user.id not in user_semaphores:
        user_semaphores[user.id] = asyncio.Semaphore(1)

    if db.get_user_attribute(user.id, "current_model") is None:
        db.set_user_attribute(user.id, "current_model", settings.models["available_text_models"][0])

    # back compatibility for n_used_tokens field
    n_used_tokens = db.get_user_attribute(user.id, "n_used_tokens")
    if isinstance(n_used_tokens, int):  # old format
        new_n_used_tokens = {
            "gpt-3.5-turbo": {
                "n_input_tokens": 0,
                "n_output_tokens": n_used_tokens
            }
        }
        db.set_user_attribute(user.id, "n_used_tokens", new_n_used_tokens)

    # voice message transcription
    if db.get_user_attribute(user.id, "n_transcribed_seconds") is None:
        db.set_user_attribute(user.id, "n_transcribed_seconds", 0.0)

    # image generation
    if db.get_user_attribute(user.id, "n_generated_images") is None:
        db.set_user_attribute(user.id, "n_generated_images", 0)


async def is_bot_mentioned(update: Update, context: CallbackContext):
    try:
        message = update.message

        if message.chat.type == "private":
            return True

        if message.text is not None and ("@" + context.bot.username) in message.text:
            return True

        if message.reply_to_message is not None:
            if message.reply_to_message.from_user.id == context.bot.id:
                return True
    except:
        return True
    else:
        return False


async def start_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id

    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    await context.bot.set_my_commands(set_commands(language))

    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.start_new_dialog(user_id)

    if context.args:
        invite_owner_id = int(context.args[0])
        db.add_invited_user_in_referral_link(invite_owner_id, user_id)
        invited_users = db.get_or_create_referral_link(invite_owner_id)
        if len(invited_users) >= 3:
            db.set_user_attribute(invite_owner_id, "trial", False)

    reply_text = HELLO[language]
    reply_text += HELP_MESSAGE[language]

    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)
    await show_chat_modes_handle(update, context)


async def help_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    await update.message.reply_text(HELP_MESSAGE[language], parse_mode=ParseMode.HTML)


async def help_group_chat_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text = HELP_GROUP_CHAT_MESSAGE[language].format(bot_username="@" + context.bot.username)

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    await update.message.reply_video(settings.help_group_chat_video_path)


async def retry_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
        return

    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
    if len(dialog_messages) == 0:
        await update.message.reply_text(NO_RETRY[language])
        return

    last_dialog_message = dialog_messages.pop()
    db.set_dialog_messages(user_id, dialog_messages, dialog_id=None)  # last message was removed from the context

    await message_handle(update, context, message=last_dialog_message["user"], use_new_dialog_timeout=False)


async def message_handle(update: Update, context: CallbackContext, message=None, use_new_dialog_timeout=True):
    # check if app was mentioned (for group chats)
    if not await is_bot_mentioned(update, context):
        return

    # check if message is edited
    if update.edited_message is not None:
        await edited_message_handle(update, context)
        return

    _message = message or update.message.text

    # remove app mention (in group chats)
    if update.message.chat.type != "private":
        _message = _message.replace("@" + context.bot.username, "").strip()

    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
        return
    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    chat_mode = db.get_user_attribute(user_id, "current_chat_mode")

    # check trial limit
    trial = db.get_user_attribute(user_id, "trial")
    n_requests = db.get_user_attribute(user_id, "n_requests")
    if trial and n_requests >= settings.free_requests_limit:
        await update.message.reply_text(LIMIT[language])
        return

    if chat_mode == "artist":
        await generate_image_handle(update, context, message=message)
        return

    async def message_handle_fn():
        # new dialog timeout
        if use_new_dialog_timeout:
            if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > settings.new_dialog_timeout and len(db.get_dialog_messages(user_id)) > 0:
                db.start_new_dialog(user_id)
                name_key = "name_ru" if language == "ru" else "name"
                mode = settings.chat_modes[chat_mode][name_key]
                mode = f"режим <b>{mode}</b>" if language == "ru" else f"<b>{mode}</b> mode"
                await update.message.reply_text(f"{DIALOG_TIMEOUT[language]} ({mode}) ✅", parse_mode=ParseMode.HTML)
        db.set_user_attribute(user_id, "last_interaction", datetime.now())

        # in case of CancelledError
        n_input_tokens, n_output_tokens = 0, 0
        current_model = db.get_user_attribute(user_id, "current_model")

        try:
            # send placeholder message to user
            placeholder_message = await update.message.reply_text("...")

            # send typing action
            await update.message.chat.send_action(action="typing")

            if _message is None or len(_message) == 0:
                await update.message.reply_text(EMPTY_MESSAGE[language], parse_mode=ParseMode.HTML)
                return

            dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
            parse_mode = {
                "html": ParseMode.HTML,
                "markdown": ParseMode.MARKDOWN
            }[settings.chat_modes[chat_mode]["parse_mode"]]

            chatgpt_instance = ChatGPT(model=current_model)
            if settings.enable_message_streaming:
                gen = chatgpt_instance.send_message_stream(_message, dialog_messages=dialog_messages, chat_mode=chat_mode)
            else:
                answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed = await chatgpt_instance.send_message(
                    _message,
                    dialog_messages=dialog_messages,
                    chat_mode=chat_mode
                )

                async def fake_gen():
                    yield "finished", answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed

                gen = fake_gen()

            prev_answer = ""
            async for gen_item in gen:
                status, answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed = gen_item

                answer = answer[:4096]  # telegram message limit

                # update only when 100 new symbols are ready
                if abs(len(answer) - len(prev_answer)) < 100 and status != "finished":
                    continue

                try:
                    await context.bot.edit_message_text(answer, chat_id=placeholder_message.chat_id, message_id=placeholder_message.message_id, parse_mode=parse_mode)
                except telegram.error.BadRequest as e:
                    if str(e).startswith("Message is not modified"):
                        continue
                    else:
                        await context.bot.edit_message_text(answer, chat_id=placeholder_message.chat_id, message_id=placeholder_message.message_id)

                await asyncio.sleep(0.01)  # wait a bit to avoid flooding

                prev_answer = answer

            # update user data
            new_dialog_message = {"user": _message, "app": answer, "date": datetime.now()}
            db.set_dialog_messages(
                user_id,
                db.get_dialog_messages(user_id, dialog_id=None) + [new_dialog_message],
                dialog_id=None
            )

            db.update_n_used_tokens(user_id, current_model, n_input_tokens, n_output_tokens)

        except asyncio.CancelledError:
            # note: intermediate token updates only work when enable_message_streaming=True (config.yml)
            db.update_n_used_tokens(user_id, current_model, n_input_tokens, n_output_tokens)
            raise

        except Exception as e:
            error_text = f"{ERROR[language]} {e}"
            logger.error(error_text)
            await update.message.reply_text(error_text)
            return

        # send message if some messages were removed from the context
        if n_first_dialog_messages_removed > 0:
            if n_first_dialog_messages_removed == 1:
                text = TOO_LONG_DIALOG[language]
            else:
                text = TOO_LONG_DIALOG_WITH_NUMBER[language].format(number=n_first_dialog_messages_removed)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async with user_semaphores[user_id]:
        task = asyncio.create_task(message_handle_fn())
        user_tasks[user_id] = task

        try:
            await task
        except asyncio.CancelledError:
            await update.message.reply_text(CANCELED[language], parse_mode=ParseMode.HTML)
        else:
            pass
        finally:
            if user_id in user_tasks:
                del user_tasks[user_id]


async def is_previous_message_not_answered_yet(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    if user_semaphores[user_id].locked():
        text = PLEASE_WAIT[language]
        await update.message.reply_text(text, reply_to_message_id=update.message.id, parse_mode=ParseMode.HTML)
        return True
    else:
        return False


async def voice_message_handle(update: Update, context: CallbackContext):
    # check if app was mentioned (for group chats)
    if not await is_bot_mentioned(update, context):
        return

    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
        return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    voice = update.message.voice
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = Path(tmp_dir)
        voice_ogg_path = tmp_dir / "voice.ogg"

        # download
        voice_file = await context.bot.get_file(voice.file_id)
        await voice_file.download_to_drive(voice_ogg_path)

        # convert to mp3
        voice_mp3_path = tmp_dir / "voice.mp3"
        pydub.AudioSegment.from_file(voice_ogg_path).export(voice_mp3_path, format="mp3")

        # transcribe
        with open(voice_mp3_path, "rb") as f:
            transcribed_text = await transcribe_audio(f)

            if transcribed_text is None:
                 transcribed_text = ""

    text = f"🎤: <i>{transcribed_text}</i>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # update n_transcribed_seconds
    db.set_user_attribute(user_id, "n_transcribed_seconds", voice.duration + db.get_user_attribute(user_id, "n_transcribed_seconds"))

    await message_handle(update, context, message=transcribed_text)


async def generate_image_handle(update: Update, context: CallbackContext, message=None):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    await update.message.chat.send_action(action="upload_photo")

    message = message or update.message.text

    try:
        image_urls = await generate_images(message, n_images=settings.return_n_generated_images)
    except openai.error.InvalidRequestError as e:
        if str(e).startswith("Your request was rejected as a result of our safety system"):
            text = GENERATE_IMAGE_ERROR[language]
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
            return
        else:
            raise

    # token usage
    db.set_user_attribute(user_id, "n_generated_images", settings.return_n_generated_images + db.get_user_attribute(user_id, "n_generated_images"))
    n_requests = db.get_user_attribute(user_id, "n_requests")
    db.set_user_attribute(user_id, "n_requests", n_requests + 1)

    for i, image_url in enumerate(image_urls):
        await update.message.chat.send_action(action="upload_photo")
        await update.message.reply_photo(image_url, parse_mode=ParseMode.HTML)


async def new_dialog_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    db.start_new_dialog(user_id)
    await update.message.reply_text(START_NEW_DIALOG[language])

    chat_mode = db.get_user_attribute(user_id, "current_chat_mode")
    welcome_message = "welcome_message_ru" if language == "ru" else "welcome_message"
    await update.message.reply_text(f"{settings.chat_modes[chat_mode][welcome_message]}", parse_mode=ParseMode.HTML)


async def cancel_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    if user_id in user_tasks:
        task = user_tasks[user_id]
        task.cancel()
    else:
        await update.message.reply_text(NOTHING_TO_CANCEL[language], parse_mode=ParseMode.HTML)


def get_chat_mode_menu(page_index: int, language: str):
    n_chat_modes_per_page = settings.n_chat_modes_per_page
    text = SELECT_CHAT_MODE[language].format(number=len(settings.chat_modes))

    # buttons
    chat_mode_keys = list(settings.chat_modes.keys())
    page_chat_mode_keys = chat_mode_keys[page_index * n_chat_modes_per_page:(page_index + 1) * n_chat_modes_per_page]

    name_key = "name_ru" if language == "ru" else "name"
    keyboard = []
    for chat_mode_key in page_chat_mode_keys:
        name = settings.chat_modes[chat_mode_key][name_key]
        keyboard.append([InlineKeyboardButton(name, callback_data=f"set_chat_mode|{chat_mode_key}")])

    # pagination
    if len(chat_mode_keys) > n_chat_modes_per_page:
        is_first_page = (page_index == 0)
        is_last_page = ((page_index + 1) * n_chat_modes_per_page >= len(chat_mode_keys))

        if is_first_page:
            keyboard.append([
                InlineKeyboardButton("»", callback_data=f"show_chat_modes|{page_index + 1}")
            ])
        elif is_last_page:
            keyboard.append([
                InlineKeyboardButton("«", callback_data=f"show_chat_modes|{page_index - 1}"),
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("«", callback_data=f"show_chat_modes|{page_index - 1}"),
                InlineKeyboardButton("»", callback_data=f"show_chat_modes|{page_index + 1}")
            ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    return text, reply_markup


async def show_chat_modes_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context): return

    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_chat_mode_menu(0, language)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def show_chat_modes_callback_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    if await is_previous_message_not_answered_yet(update.callback_query, context): return

    user_id = update.callback_query.from_user.id
    language = update.callback_query.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    query = update.callback_query
    await query.answer()

    page_index = int(query.data.split("|")[1])
    if page_index < 0:
        return

    text, reply_markup = get_chat_mode_menu(page_index, language)
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            pass


async def set_chat_mode_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    user_id = update.callback_query.from_user.id
    language = update.callback_query.from_user.language_code
    language = language if language == "ru" else "en"

    query = update.callback_query
    await query.answer()

    chat_mode = query.data.split("|")[1]

    db.set_user_attribute(user_id, "current_chat_mode", chat_mode)
    db.start_new_dialog(user_id)

    welcome_message = "welcome_message_ru" if language == "ru" else "welcome_message"
    await context.bot.send_message(
        update.callback_query.message.chat.id,
        f"{settings.chat_modes[chat_mode][welcome_message]}",
        parse_mode=ParseMode.HTML
    )


def get_settings_menu(user_id: int, language: str):
    current_model = db.get_user_attribute(user_id, "current_model")
    description_key = "description_ru" if language == "ru" else "description"
    text = settings.models["info"][current_model][description_key]

    text += "\n\n"
    score_dict = settings.models["info"][current_model]["scores"]
    for score_key, score_value in score_dict.items():
        text += "🟢" * score_value + "⚪️" * (5 - score_value) + f" – {score_key}\n\n"

    text += SELECT_MODEL[language]

    # buttons to choose models
    buttons = []
    for model_key in settings.models["available_text_models"]:
        title = settings.models["info"][model_key]["name"]
        if model_key == current_model:
            title = "✅ " + title

        buttons.append(
            InlineKeyboardButton(title, callback_data=f"set_settings|{model_key}")
        )
    reply_markup = InlineKeyboardMarkup([buttons])

    return text, reply_markup


async def settings_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
        return

    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_settings_menu(user_id, language)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def set_settings_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    user_id = update.callback_query.from_user.id
    language = update.callback_query.from_user.language_code
    language = language if language == "ru" else "en"

    query = update.callback_query
    await query.answer()

    _, model_key = query.data.split("|")
    db.set_user_attribute(user_id, "current_model", model_key)
    db.start_new_dialog(user_id)

    text, reply_markup = get_settings_menu(user_id, language)
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            pass


async def show_balance_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    # # count total usage statistics
    # total_n_spent_dollars = 0
    # total_n_used_tokens = 0
    #
    # n_used_tokens_dict = db.get_user_attribute(user_id, "n_used_tokens")
    # n_generated_images = db.get_user_attribute(user_id, "n_generated_images")
    # n_transcribed_seconds = db.get_user_attribute(user_id, "n_transcribed_seconds")
    #
    # details_text = "🏷️ Details:\n"
    # for model_key in sorted(n_used_tokens_dict.keys()):
    #     n_input_tokens, n_output_tokens = n_used_tokens_dict[model_key]["n_input_tokens"], n_used_tokens_dict[model_key]["n_output_tokens"]
    #     total_n_used_tokens += n_input_tokens + n_output_tokens
    #
    #     n_input_spent_dollars = config.models["info"][model_key]["price_per_1000_input_tokens"] * (n_input_tokens / 1000)
    #     n_output_spent_dollars = config.models["info"][model_key]["price_per_1000_output_tokens"] * (n_output_tokens / 1000)
    #     total_n_spent_dollars += n_input_spent_dollars + n_output_spent_dollars
    #
    #     details_text += f"- {model_key}: <b>{n_input_spent_dollars + n_output_spent_dollars:.03f}$</b> / <b>{n_input_tokens + n_output_tokens} tokens</b>\n"
    #
    # # image generation
    # image_generation_n_spent_dollars = config.models["info"]["dalle-2"]["price_per_1_image"] * n_generated_images
    # if n_generated_images != 0:
    #     details_text += f"- DALL·E 2 (image generation): <b>{image_generation_n_spent_dollars:.03f}$</b> / <b>{n_generated_images} generated images</b>\n"
    #
    # total_n_spent_dollars += image_generation_n_spent_dollars
    #
    # # voice recognition
    # voice_recognition_n_spent_dollars = config.models["info"]["whisper"]["price_per_1_min"] * (n_transcribed_seconds / 60)
    # if n_transcribed_seconds != 0:
    #     details_text += f"- Whisper (voice recognition): <b>{voice_recognition_n_spent_dollars:.03f}$</b> / <b>{n_transcribed_seconds:.01f} seconds</b>\n"
    #
    # total_n_spent_dollars += voice_recognition_n_spent_dollars
    #
    #
    # text = f"You spent <b>{total_n_spent_dollars:.03f}$</b>\n"
    # text += f"You used <b>{total_n_used_tokens}</b> tokens\n\n"
    # text += details_text

    trial = db.get_user_attribute(user_id, "trial")
    n_requests = db.get_user_attribute(user_id, "n_requests")
    if trial:
        invited_users = db.get_or_create_referral_link(user_id)
        text = TRIAL_VERSION[language].format(
            number=n_requests,
            limit=settings.free_requests_limit,
            invited=len(invited_users),
            required=settings.full_version_required_friends
        )
    else:
        text = FULL_VERSION[language].format(number=n_requests)

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def generate_link_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.get_or_create_referral_link(user_id)

    link = context.bot.link + f"?start={user_id}"
    text = f"{REFERRAL_LINK[language]}{link}"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def edited_message_handle(update: Update, context: CallbackContext):
    language = update.message.from_user.language_code
    language = language if language == "ru" else "en"
    if update.edited_message.chat.type == "private":
        text = EDITING_NOT_SUPPORTED[language]
        await update.edited_message.reply_text(text, parse_mode=ParseMode.HTML)


async def error_handle(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    try:
        # collect error message
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)
        update_str = update.to_dict() if isinstance(update, Update) else str(update)
        message = (
            f"An exception was raised while handling an update\n"
            f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
            "</pre>\n\n"
            f"<pre>{html.escape(tb_string)}</pre>"
        )

        # split text into multiple messages due to 4096 character limit
        for message_chunk in split_text_into_chunks(message, 4096):
            try:
                await context.bot.send_message(update.effective_chat.id, message_chunk, parse_mode=ParseMode.HTML)
            except telegram.error.BadRequest:
                # answer has invalid characters, so we send it without parse_mode
                await context.bot.send_message(update.effective_chat.id, message_chunk)
    except:
        await context.bot.send_message(update.effective_chat.id, "Some error in error handler")


async def post_init(application: Application):
    await application.bot.set_my_commands(set_commands())


def run_bot() -> None:
    application = (
        ApplicationBuilder()
        .token(settings.telegram_token)
        .concurrent_updates(True)
        .rate_limiter(AIORateLimiter(max_retries=5))
        .post_init(post_init)
        .build()
    )

    # add handlers
    user_filter = filters.ALL
    if len(settings.allowed_telegram_usernames) > 0:
        usernames = [x for x in settings.allowed_telegram_usernames if isinstance(x, str)]
        user_ids = [x for x in settings.allowed_telegram_usernames if isinstance(x, int)]
        user_filter = filters.User(username=usernames) | filters.User(user_id=user_ids)

    application.add_handler(CommandHandler("start", start_handle, filters=user_filter))
    application.add_handler(CommandHandler("help", help_handle, filters=user_filter))
    application.add_handler(CommandHandler("help_group_chat", help_group_chat_handle, filters=user_filter))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, message_handle))
    application.add_handler(CommandHandler("retry", retry_handle, filters=user_filter))
    application.add_handler(CommandHandler("new", new_dialog_handle, filters=user_filter))
    application.add_handler(CommandHandler("cancel", cancel_handle, filters=user_filter))

    application.add_handler(MessageHandler(filters.VOICE & user_filter, voice_message_handle))

    application.add_handler(CommandHandler("mode", show_chat_modes_handle, filters=user_filter))
    application.add_handler(CallbackQueryHandler(show_chat_modes_callback_handle, pattern="^show_chat_modes"))
    application.add_handler(CallbackQueryHandler(set_chat_mode_handle, pattern="^set_chat_mode"))

    application.add_handler(CommandHandler("settings", settings_handle, filters=user_filter))
    application.add_handler(CallbackQueryHandler(set_settings_handle, pattern="^set_settings"))

    application.add_handler(CommandHandler("balance", show_balance_handle, filters=user_filter))
    application.add_handler(CommandHandler("link", generate_link_handle, filters=user_filter))

    application.add_error_handler(error_handle)

    # start the app
    if settings.webhook:
        webhook_path = f"/{settings.webhook_prefix}/{settings.telegram_token}"
        webhook_url = f"{settings.webhook_host}{webhook_path}"
        application.run_webhook(
            listen="0.0.0.0",
            port=settings.webhook_port,
            webhook_url=webhook_url,
            url_path=webhook_path,
            drop_pending_updates=True
        )
    else:
        application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
