import time
from typing import Tuple, Union
from functools import wraps
from pyrogram import enums, Client
from pyrogram.types import Message
from database.connections_mdb import active_connection
from info import ADMINS as AUTH_USERS
ADMINS = {}

async def admin_check(message: Message) -> bool:
    if not message.from_user:
        return False

    user_id = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type not in [enums.ChatType.SUPERGROUP, enums.ChatType.GROUP]:
        return False

    if user_id in ADMINS.get(chat_id, []):
        return True

    client = message._client

    check_status = await client.get_chat_member(
        chat_id=chat_id,
        user_id=user_id
    )
    admin_strings = [
        enums.ChatMemberStatus.OWNER,
        enums.ChatMemberStatus.ADMINISTRATOR
    ]
    # https://git.colinshark.de/PyroBot/PyroBot/src/branch/master/pyrobot/modules/admin.py#L69
    if check_status.status not in admin_strings:
        return False
    else:
        if not ADMINS.get(chat_id, []):
            ADMINS[chat_id] = []
            ADMINS[chat_id].append(user_id)
        else:
            ADMINS[chat_id].append(user_id)
        return True


def extract_user(message: Message) -> Union[Tuple[int, str], Tuple[None, None]]:
    """extracts the user from a message"""
    user_id = None
    user_first_name = None

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_first_name = message.reply_to_message.from_user.first_name

    elif len(message.command) > 1:
        if (
            len(message.entities) > 1 and
            message.entities[1].type == enums.MessageEntityType.TEXT_MENTION
        ):
            # 0: is the command used
            # 1: should be the user specified
            required_entity = message.entities[1]
            user_id = required_entity.user.id
            user_first_name = required_entity.user.first_name
        else:
            user_id = message.command[1]
            # don't want to make a request -_-
            user_first_name = user_id

        try:
            user_id = int(user_id)
        except ValueError:
            pass

    else:
        user_id = message.from_user.id
        user_first_name = message.from_user.first_name

    return (user_id, user_first_name)


def extract_time(time_val):
    if any(time_val.endswith(unit) for unit in ('s', 'm', 'h', 'd')):
        unit = time_val[-1]
        time_num = time_val[:-1]  # type: str
        if not time_num.isdigit():
            return None

        if unit == 's':
            bantime = int(time.time() + int(time_num))
        elif unit == 'm':
            bantime = int(time.time() + int(time_num) * 60)
        elif unit == 'h':
            bantime = int(time.time() + int(time_num) * 60 * 60)
        elif unit == 'd':
            bantime = int(time.time() + int(time_num) * 24 * 60 * 60)
        else:
            # how even...?
            return None
        return bantime
    else:
        return None


def admin_check_dec(func):

    @wraps(func)
    async def wrapper(bot: Client, update: Message, *args, **kwargs):

        chat_type = update.chat.type
        user_id = update.from_user.id if update.from_user != None else None 
        if user_id is None:
            await update.reply_text("Anonymus User Can't Use This Command")
            return wrapper
        if chat_type == enums.ChatType.PRIVATE:
            chat_id = await active_connection(str(user_id))
            if chat_id is not None:
                try:
                    chat = await bot.get_chat(chat_id)
                    _ = chat.title
                except:
                    await update.reply_text("Make sure I'm admin in your group!!", quote=True)
                    return wrapper
            else:
                await update.reply_text("You are not connected to any groups!", quote=True)
                return wrapper
        elif chat_type in [enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
            chat = update.chat
        else:
            return wrapper
        
        chat_id = chat.id
        chat_dict = ADMINS.get(int(chat_id))
        chat_admins = chat_dict if chat_dict != None else (await admin_list(chat_id, bot))
        admin_status = True if user_id in chat_admins else False
        
        if (admin_status or user_id in AUTH_USERS):
            update.chat.real_id = chat.id
            update.chat.real_title = chat.title

            return await func(bot, update)
            
    return wrapper


async def admin_list(chat_id, bot: Client):
    """
    Creates A List Of Admin User ID's
    """
    global ADMINS
    admins_id_list = []
    async for x in bot.get_chat_members(chat_id=chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS):

        admin_id = x.user.id 
        admins_id_list.append(admin_id)

    admins_id_list.append(None)
    ADMINS[str(chat_id)] = admins_id_list
    return admins_id_list

