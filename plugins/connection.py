from pyrogram import filters, Client, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from database.connections_mdb import add_connection, all_connections, if_active, delete_connection
from info import ADMINS
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


@Client.on_message((filters.private | filters.group) & filters.command('connect'))
async def addconnection(bot: Client, update: Message):
    userid = update.from_user.id if update.from_user else None
    if not userid:
        return await update.reply(f"You are anonymous admin. Use /connect {update.chat.id} in PM")
    chat_type = update.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        try:
            cmd, group_id = update.text.split(" ", 1)
        except:
            await update.reply_text(
                "<b>Enter in correct format!</b>\n\n"
                "<code>/connect groupid</code>\n\n"
                "<i>Get your Group id by adding this bot to your group and use  <code>/id</code></i>",
                quote=True
            )
            return

    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        group_id = update.chat.id

    try:
        st = await bot.get_chat_member(group_id, userid)
        if (
            st.status != enums.ChatMemberStatus.ADMINISTRATOR
            and st.status != enums.ChatMemberStatus.OWNER
            and str(userid) not in ADMINS
        ):
            await update.reply_text("You should be an admin in Given group!", quote=True)
            return
    except Exception as e:
        logger.exception(e)
        await update.reply_text(
            "Invalid Group ID!\n\nIf correct, Make sure I'm present in your group!!",
            quote=True,
        )

        return
    try:
        st = await bot.get_chat_member(group_id, "me")
        if st.status == enums.ChatMemberStatus.ADMINISTRATOR:
            ttl = await bot.get_chat(group_id)
            title = ttl.title

            addcon = await add_connection(str(group_id), str(userid))
            if addcon:
                await update.reply_text(
                    f"Successfully connected to **{title}**\nNow manage your group from my pm !",
                    quote=True,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                if chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
                    await bot.send_message(
                        userid,
                        f"Connected to **{title}** !",
                        parse_mode=enums.ParseMode.MARKDOWN
                    )
            else:
                await update.reply_text(
                    "You're already connected to this chat!",
                    quote=True
                )
        else:
            await update.reply_text("Add me as an admin in group", quote=True)
    except Exception as e:
        logger.exception(e)
        await update.reply_text('Some error occured! Try again later.', quote=True)
        return


@Client.on_message((filters.private | filters.group) & filters.command('disconnect'))
async def deleteconnection(bot: Client, update: Message):
    userid = update.from_user.id if update.from_user else None
    if not userid:
        return await update.reply(f"You are anonymous admin. Use /connect {update.chat.id} in PM")
    chat_type = update.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        await update.reply_text("Run /connections to view or disconnect from groups!", quote=True)

    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        group_id = update.chat.id

        st = await bot.get_chat_member(group_id, userid)
        if (
            st.status != enums.ChatMemberStatus.ADMINISTRATOR
            and st.status != enums.ChatMemberStatus.OWNER
            and str(userid) not in ADMINS
        ):
            return

        delcon = await delete_connection(str(userid), str(group_id))
        if delcon:
            await update.reply_text("Successfully disconnected from this chat", quote=True)
        else:
            await update.reply_text("This chat isn't connected to me!\nDo /connect to connect.", quote=True)


@Client.on_message(filters.private & filters.command(["connections"]))
async def connections(bot: Client, update: Message):
    userid = update.from_user.id

    groupids = await all_connections(str(userid))
    if groupids is None:
        await update.reply_text(
            "There are no active connections!! Connect to some groups first.",
            quote=True
        )
        return
    buttons = []
    for groupid in groupids:
        try:
            ttl = await bot.get_chat(int(groupid))
            title = ttl.title
            active = await if_active(str(userid), str(groupid))
            act = " - ACTIVE" if active else ""
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"{title}{act}", callback_data=f"groupcb:{groupid}:{act}"
                    )
                ]
            )
        except:
            pass
    if buttons:
        await update.reply_text(
            "Your connected group details ;\n\n",
            reply_markup=InlineKeyboardMarkup(buttons),
            quote=True
        )
    else:
        await update.reply_text(
            "There are no active connections!! Connect to some groups first.",
            quote=True
        )

