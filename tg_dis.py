import asyncio
import ssl
import certifi
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from discord.ext import commands
import discord

# ------------------- Настройки -------------------
TELEGRAM_TOKEN = "8047137767:AAELs_uYucqa0fbjbkAldIYXiPRubkeCWic"
TELEGRAM_CHAT_ID = -1001810100661
DISCORD_TOKEN = "MTMwMzQ0OTkzMDk4MzI4MDcwMA.Gz1MBz.V4gjv7HjnkuBute_dJUuZ5Ob6B5XoYPFSR7_W8"
UPDATE_INTERVAL = 10
# -------------------------------------------------

# ---------- Telegram bot ----------
tg_bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
update_message_id = None

# ---------- Discord bot ----------
intents = discord.Intents.default()
intents.members = True
intents.voice_states = True

ssl_context = ssl.create_default_context(cafile=certifi.where())
discord_bot = commands.Bot(command_prefix="!", intents=intents, ssl=ssl_context)

# ---------- Discord функции ----------
async def get_voice_members():
    channels_data = {}
    for guild in discord_bot.guilds:
        for channel in guild.voice_channels:
            members = [member.name for member in channel.members]
            channels_data[channel.name] = members
    return channels_data

async def format_message():
    data = await get_voice_members()
    msg_lines = ["СПИСОК УЧАСТНИКОВ ГОЛОСОВЫХ КАНАЛОВ В ДИСКОРДЕ:\n"]
    for channel, members in data.items():
        if members:
            msg_lines.append(f"*{channel}* ({len(members)}):\n" + "\n".join(members))
    return "\n".join(msg_lines) if len(msg_lines) > 1 else "Пусто"

# ---------- Telegram обновление сообщения ----------
async def update_telegram_message():
    global update_message_id
    try:
        text = await format_message()
        if update_message_id:
            await tg_bot.edit_message_text(chat_id=TELEGRAM_CHAT_ID,
                                           message_id=update_message_id,
                                           text=text,
                                           parse_mode=ParseMode.MARKDOWN)
        else:
            msg = await tg_bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                                            text=text,
                                            parse_mode=ParseMode.MARKDOWN)
            update_message_id = msg.message_id
    except Exception as e:
        print("Ошибка при обновлении Telegram сообщения:", e)

# ---------- Telegram команда /start ----------
@dp.message(Command(commands=["start"]))
async def start_command(message: types.Message):
    global update_message_id
    text = await format_message()
    msg = await message.answer(text, parse_mode=ParseMode.MARKDOWN)
    update_message_id = msg.message_id
    await message.answer("Бот запущен и будет обновлять список участников каждые 10 секунд!")

# ---------- Discord событие ----------
@discord_bot.event
async def on_ready():
    print(f"Discord бот {discord_bot.user} запущен!")
    async def loop_update():
        while True:
            await update_telegram_message()
            await asyncio.sleep(UPDATE_INTERVAL)
    discord_bot.loop.create_task(loop_update())

# ---------- Основной запуск ----------
async def main():
    tg_task = asyncio.create_task(dp.start_polling(tg_bot))
    await discord_bot.start(DISCORD_TOKEN)
    await tg_task

if __name__ == "__main__":
    asyncio.run(main())
