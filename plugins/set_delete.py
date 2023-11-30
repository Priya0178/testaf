from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from info import ADMINS
from database.configsdb import get_config, update_config


@Client.on_message(filters.command("setdelete") & filters.user(ADMINS), group=-1)
async def setdelete(client, message):
    await message.reply_text(
        text="**Select the mode of delete button:**",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("30 min", callback_data="setdelete_1800"),
                    InlineKeyboardButton("25 min", callback_data="setdelete_1500"),
                ],
                [
                    InlineKeyboardButton("20 min", callback_data="setdelete_1200"),
                    InlineKeyboardButton("15 min", callback_data="setdelete_900"),
                ],
                [
                    InlineKeyboardButton("12 min", callback_data="setdelete_720"),
                    InlineKeyboardButton("10 min", callback_data="setdelete_600"),
                ],
                [
                    InlineKeyboardButton("5 min", callback_data="setdelete_300"),
                    InlineKeyboardButton("2 min", callback_data="setdelete_120"),
                ],
                [
                    InlineKeyboardButton("10 sec", callback_data="setdelete_10"),
                    InlineKeyboardButton("5 sec", callback_data="setdelete_5"),
                ],
            ]
        ),
        quote=True
    )


@Client.on_callback_query(filters.regex(r"^setdelete_\d+$") & filters.user(ADMINS), -2)
async def setdelete_callback(_, callback_query):

    await callback_query.answer()

    data = callback_query.data.split("_")[1]
    await callback_query.message.edit_text(
        text=f"**Messages will be automatically deleted after {data} seconds.**",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🗑 Close", callback_data="close_data")
                ]
            ]
        )
    )

    await update_config({"_id": "DELETE_TIME", "value": int(data)})




