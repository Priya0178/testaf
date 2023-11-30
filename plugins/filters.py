import io
import logging 

from pyrogram import filters, Client, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.errors import UserNotParticipant

from database.filters_mdb import(
   add_filter,
   get_filters,
   delete_filter,
   count_filters
)

from database.connections_mdb import active_connection
from plugins.utils import admin_check_dec
from utils import get_file_id, parser, split_quotes
from info import ADMINS

logger = logging.getLogger(__name__)

@Client.on_message(filters.command(['filter', 'add']) & filters.incoming)
@admin_check_dec
async def addfilter(bot: Client, update: Message):

    userid = update.from_user.id
    grp_id = update.chat.real_id
    title = ""
    args = update.text.html.split(None, 1)

    st = await bot.get_chat_member(grp_id, userid)
    if (
        st.status != enums.ChatMemberStatus.ADMINISTRATOR
        and st.status != enums.ChatMemberStatus.OWNER
        and str(userid) not in ADMINS
    ):
        return
    else:
        title = (await bot.get_chat(grp_id)).title

    if not grp_id or not title:
        return

    if len(args) < 2:
        await update.reply_text("Command Incomplete :(", quote=True)
        return

    extracted = await split_quotes(args[1])
    text = extracted[0].lower()

    if not update.reply_to_message and len(extracted) < 2:
        await update.reply_text("Add some content to save your filter!", quote=True)
        return

    if (len(extracted) >= 2) and not update.reply_to_message:
        reply_text, btn, alert = await parser(extracted[1], text)
        fileid = None
        if not reply_text:
            await update.reply_text("You cannot have buttons alone, give some text to go with it!", quote=True)
            return

    elif update.reply_to_message and update.reply_to_message.reply_markup:
        try:
            rm = update.reply_to_message.reply_markup
            btn = rm.inline_keyboard
            msg = get_file_id(update.reply_to_message)
            if msg:
                fileid = msg.file_id
                reply_text = update.reply_to_message.caption.html
            else:
                reply_text = update.reply_to_message.text.html
                fileid = None
            alert = None
        except:
            reply_text = ""
            btn = "[]" 
            fileid = None
            alert = None

    elif update.reply_to_message and update.reply_to_message.media:
        fileid = None
        try:
            msg = get_file_id(update.reply_to_message)
            fileid = msg.file_id if msg else None
            reply_text, btn, alert = await parser(extracted[1], text) if update.reply_to_message.sticker else await parser(update.reply_to_message.caption.html, text)
        except Exception as e:
            reply_text = ""
            btn = "[]"
            alert = None
            if not fileid and not reply_text:
                logger.exception(e)
    elif update.reply_to_message and update.reply_to_message.text:
        try:
            fileid = None
            reply_text, btn, alert = await parser(update.reply_to_message.text.html, text)
        except:
            reply_text = ""
            btn = "[]"
            alert = None
    else:
        # logger.info(update)
        return

    await add_filter(grp_id, text, reply_text, btn, fileid, alert)

    await update.reply_text(
        f"Filter for  `{text}`  added in  **{title}**",
        quote=True,
        parse_mode=enums.ParseMode.MARKDOWN
    )


@Client.on_message(filters.command(['viewfilters', 'filters']) & filters.incoming)
@admin_check_dec
async def get_all(bot: Client, update: Message):
    
    userid = update.from_user.id 
    grp_id = update.chat.real_id
    title = update.chat.real_title

    st = await bot.get_chat_member(grp_id, userid)
    if (
        st.status != enums.ChatMemberStatus.ADMINISTRATOR
        and st.status != enums.ChatMemberStatus.OWNER
        and str(userid) not in ADMINS
    ):
        return

    texts = await get_filters(grp_id)
    count = await count_filters(grp_id)
    if count:
        filterlist = f"Total number of filters in **{title}** : {count}\n\n"

        for text in texts:
            keywords = " ×  `{}`\n".format(text)

            filterlist += keywords

        if len(filterlist) > 4096:
            with io.BytesIO(str.encode(filterlist.replace("`", ""))) as keyword_file:
                keyword_file.name = "keywords.txt"
                await update.reply_document(
                    document=keyword_file,
                    quote=True
                )
            return
    else:
        filterlist = f"There are no active filters in **{title}**"

    await update.reply_text(
        text=filterlist,
        quote=True,
        parse_mode=enums.ParseMode.MARKDOWN
    )


@Client.on_message(filters.command(['del']) & filters.incoming)
@admin_check_dec
async def deletefilter(bot: Client, update: Message):

    userid = update.from_user.id if update.from_user else None
    grp_id = update.chat.real_id
    title = ""



    st = await bot.get_chat_member(grp_id, userid)
    if (
        st.status != enums.ChatMemberStatus.ADMINISTRATOR
        and st.status != enums.ChatMemberStatus.OWNER
        and str(userid) not in ADMINS
    ):
        return
    else:
        title = (await bot.get_chat(grp_id)).title
    try:
        cmd, text = update.text.split(" ", 1)
    except:
        await update.reply_text(
            "<i>Mention the filtername which you wanna delete!</i>\n\n"
            "<code>/del filtername</code>\n\n"
            "Use /viewfilters to view all available filters",
            quote=True
        )
        return

    query = text.lower()

    await delete_filter(update, query, grp_id, title)
        

@Client.on_message(filters.command('delall') & filters.incoming)
@admin_check_dec
async def delallconfirm(client, message):

    userid = message.from_user.id
    grp_id = message.chat.real_id
    title = message.chat.real_title

    st = await client.get_chat_member(grp_id, userid)
    if (st.status == enums.ChatMemberStatus.OWNER) or (str(userid) in ADMINS):
        await message.reply_text(
            f"This will delete all filters from '{title}'.\nDo you want to continue??",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="YES",callback_data="delallconfirm")],
                [InlineKeyboardButton(text="CANCEL",callback_data="delallcancel")]
            ]),
            quote=True
        )

