import logging
import copy
import re
import os
import pyrogram # for manual filter
from sys import executable

from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty
from pyrogram.errors import MessageNotModified, FloodWait
from pyrogram.errors import UserIsBlocked, PeerIdInvalid

from database.ia_filterdb import get_file_details, get_search_results
from database.configsdb import get_config
from database.filters_mdb import (
    find_filter,
    get_filters,
)


from info import DELETE_TIME, AUTH_CHANNEL, CUSTOM_FILE_CAPTION, ADMINS, REQ_CHANNEL
from utils import get_size, get_poster, google_search, get_settings, temp, is_subscribed


logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(
    {"apscheduler.timezone": "UTC"}, 
    job_defaults={"misfire_grace_time": 5}, 
    daemon=True, 
    run_async=True, 
)

BUTTONS = {}
SPELL_CHECK = {}
FIND = {}

max_results = 300
max_per_page = 10
max_pages = max_results // max_per_page
poster ="https://te.legra.ph/file/2500cc8d983ab69349cff.jpg"


@Client.on_message(filters.command('clearcache') & filters.user(ADMINS))
async def clrcache(_, message):
    FIND.clear()
    await message.reply("**𝙲𝙰𝙲𝙷𝙴 𝙲𝙻𝙴𝙰𝚁𝙴𝙳**")


@Client.on_message((filters.group | filters.private) & filters.text & filters.incoming, group=-3)
async def give_filter(bot: Client, update: Message):
    group_id = update.chat.id
    name = update.text

    keywords = await get_filters(group_id)
    for keyword in reversed(sorted(keywords, key=len)):
        pattern = r"( |^|[^\w])" + re.escape(keyword) + r"( |$|[^\w])"
        if re.search(pattern, name, flags=re.IGNORECASE):
            reply_text, btn, alert, fileid = await find_filter(group_id, keyword)

            if reply_text:
                reply_text = reply_text.replace("\\n", "\n").replace("\\t", "\t")

            if btn is not None:
                try:
                    if fileid == "None":
                        k = await update.reply_text(
                            reply_text,
                            True,
                            disable_web_page_preview=True,
                            reply_markup=InlineKeyboardMarkup(eval(btn)) if btn != "[]" else None,
                        )
                    else:
                        k = await update.reply_cached_media(
                            fileid,
                            True,
                            caption=reply_text or "",
                            reply_markup=InlineKeyboardMarkup(eval(btn)) if btn != "[]" else None,
                        )
                    seconds = await get_config("DELETE_TIME", DELETE_TIME)
                    scheduler.add_job(
                        delete_msg, 'date', args=[bot, k, update.from_user.id], 
                        run_date=datetime.now() + timedelta(seconds=seconds)
                    )
                except Exception as e:
                    logger.exception(e, exc_info=True)
                break 

    else:
        await auto_filter(bot, update)


@Client.on_callback_query(filters.regex(r"^next"))
async def next_page(bot: Client, update: CallbackQuery):

    _, req, offset, key = update.data.split("_")

    if int(req) not in [update.from_user.id, 0]:
        return await update.answer("Search for yourself", show_alert=True)
    try:
        offset = int(offset)
    except:
        offset = 0

    files = FIND.get(key.lower(), False)
    if not files:
        await update.answer("Link expired search again.", show_alert=True)
        return

    total_pages = len(files)
    lpagefiles = len(files[-1])
    lpagefiles = lpagefiles if lpagefiles != max_per_page else 0

    btn = copy.deepcopy(files[offset])
    del files

    btn.insert(0, 
        [
            InlineKeyboardButton(f'🎬 {key} 🎬', 'reqst1')
        ]
    )

    if offset == 0 and total_pages == 1:
        btn.append(
            [
                InlineKeyboardButton(f"▫️ Pages 1 / 1", callback_data="pages")
            ]
        )

    elif offset == 0:
        btn.append(
            [
                InlineKeyboardButton("▫️ Pages", callback_data="pages"),
                InlineKeyboardButton(text=f"{offset + 1} / {total_pages}", callback_data="pages"),
                InlineKeyboardButton(text="Next ⏩️", callback_data=f"next_{req}_{offset + 1}_{key}")
            ]
        )
    
    elif offset + 1 == total_pages:
        btn.append(
            [
                InlineKeyboardButton("⏪ Previous", callback_data=f"next_{req}_{offset - 1}_{key}"),
                InlineKeyboardButton(f"{offset + 1} / {total_pages}", callback_data="pages")
            ]
        )

    else:
        btn.append(
            [
                InlineKeyboardButton("⏪ Previous", callback_data=f"next_{req}_{offset - 1}_{key}"),
                InlineKeyboardButton(f"{offset + 1} / {total_pages}", callback_data="pages"),
                InlineKeyboardButton("Next ⏩️", callback_data=f"next_{req}_{offset + 1}_{key}")
            ]
        )

    try:
        await update.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(btn)
        )
    except MessageNotModified:
        pass
    await update.answer()


@Client.on_callback_query(filters.regex(r"^spolling"))
async def advantage_spoll_choker(bot: Client, update: CallbackQuery):

    _, user, movie_ = update.data.split('#')
    if int(user) != 0 and update.from_user.id != int(user):
        return await update.answer("Search for yourself", show_alert=True)

    if movie_ == "close_spellcheck":
        return await update.message.delete()

    movies = SPELL_CHECK.get(update.message.reply_to_message_id)
    if not movies:
        return await update.answer("Link expired search again.", show_alert=True)

    movie = movies[(int(movie_))]
    await update.answer('Checking...!')

    k = await manual_filters(bot, update.message, text=movie)
    if k == False:
        files = await get_search_results(movie)
        if files:
            k = (movie, files, len(files))
            await auto_filter(bot, update, k)
        else:
            k = await update.message.edit('Movie not found')
            seconds = await get_config("DELETE_TIME", DELETE_TIME)
            scheduler.add_job(k.delete, 'date', run_date=datetime.now() + timedelta(seconds=seconds))


async def auto_filter(client, msg: Message, spoll=False):

    seconds = await get_config("DELETE_TIME", DELETE_TIME)
    cache = False

    if spoll:
        settings = await get_settings(msg.message.chat.id)
        message = msg.message.reply_to_message  # msg will be callback query
        search, files, total_results = spoll
        files = files[:max_results]

    else:
        message = msg
        settings = await get_settings(message.chat.id)
        if message.text.startswith("/"): 
            return  # ignore commands
        if re.findall("((^\/|^,|^!|^\.|^[\U0001F600-\U000E007F]).*)", message.text):
            return
        if not 2 < len(message.text) < 100:
            return

        search = message.text
        if FIND.get(search.lower(), False):
            files = copy.deepcopy(FIND[search.lower()])
            # Limit to max no of total pages
            files = files[:max_pages]
            
            pages = len(files)
            lpagefiles = len(files[-1])
            lpagefiles = lpagefiles if lpagefiles != max_per_page else 0
            total_results = (pages * max_per_page) - lpagefiles if pages != 0 else 0
            
            cache = True
        else:
            files = await get_search_results(search.lower())
            # Limit to max no of total results
            files = files[:max_results]
            if not files:
                if settings["spell_check"]:
                    return await advance_spell_check(msg)
                else:
                    return
        
            total_results = len(files)

    if total_results == 0:
        return

    
    if not cache:
        pre = 'filep' if settings['file_secure'] else 'file'
        if settings["button"]:
            btn = [
                [
                    InlineKeyboardButton(
                        text=f"📂 {get_size(file.file_size)} ● {file.file_name}", callback_data=f'{pre}#{file.file_id}'
                    ),
                ]
                for file in files
            ]
        else:
            btn = [
                [
                    InlineKeyboardButton(
                        text=f"{file.file_name}",
                        callback_data=f'{pre}#{file.file_id}',
                    ),
                    InlineKeyboardButton(
                        text=f"{get_size(file.file_size)}",
                        callback_data=f'{pre}_#{file.file_id}',
                    ),
                ]
                for file in files
            ]

        # Divide the buttons into groups/pages
        btn = [btn[i * max_per_page :(i + 1) * max_per_page ] for i in range((len(files) + max_per_page - 1) // max_per_page )]
        # Cache the btns split into pages for future use
        FIND[search.lower()] = copy.deepcopy(btn)
    else:
        btn = copy.deepcopy(files)


    total_pages = len(btn)
    btn[0].insert(0, 
        [
            InlineKeyboardButton(f'🎬 {search} 🎬', 'reqst1')
        ]
    )

    req = message.from_user.id if message.from_user else 0
    btn[0].append(
        [
            InlineKeyboardButton(text=f"▫️ Pages", callback_data="pages"),
            InlineKeyboardButton(text=f"1/{total_pages}", callback_data="pages"),
            InlineKeyboardButton(f'Next ⏩', f'next_{req}_1_{search}'),
        ]
    )
    if total_pages == 1:
        # Remove the next button if there is only one page
        btn[0][-1].pop()

    btn = btn[0]

    imdb = await get_poster(search, bulk=False) if settings["imdb"] else None
    TEMPLATE = settings['template']

    if imdb:
        cap = TEMPLATE.format(
            query = search,
            group = message.chat.title,
            title = imdb['title'],
            votes = imdb['votes'],
            aka = imdb["aka"],
            seasons = imdb["seasons"],
            localized_title = imdb['localized_title'],
            kind = imdb['kind'],
            imdb_id = imdb["imdb_id"],
            cast = imdb["cast"],
            runtime = imdb["runtime"],
            countries = imdb["countries"],
            languages = imdb["languages"],
            director = imdb["director"],
            release_date = imdb['release_date'],
            year = imdb['year'],
            genres = imdb['genres'],
            poster = imdb['poster'],
            plot = imdb['plot'],
            rating = imdb['rating'],
            url = imdb['url']
        )
    else:
        cap = f"<b>Hey {message.from_user.mention} 👋🏻\n\n<i>Title : {search}\nYour Files is Ready Now</i></b>"

    if imdb and imdb.get('poster'):
        try:
            k = await message.reply_photo(
                photo=imdb.get('poster'),
                quote=True,
                caption=cap[:1024],
                reply_markup=InlineKeyboardMarkup(btn)
            )
        except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
            global poster
            k = await message.reply_photo(
                photo=poster,
                quote=True,
                caption=cap[:1024], 
                reply_markup=InlineKeyboardMarkup(btn)
            )
            poster = k.photo.file_id
        except Exception as e:
            logger.exception(e)
            k = await message.reply_text(cap, quote=True, reply_markup=InlineKeyboardMarkup(btn))
    else:
        k = await message.reply_text(cap, quote=True, reply_markup=InlineKeyboardMarkup(btn))

    scheduler.add_job(
        delete_msg, 'date', args=[client, k, message.from_user.id], 
        run_date=datetime.now() + timedelta(seconds=seconds)
    )

    if spoll:
        await msg.message.delete()


async def advance_spell_check(msg):
    query = re.sub(
        r"\b(pl(i|e)*?(s|z+|ease|se|ese|(e+)s(e)?)|((send|snd|giv(e)?|\
            gib)(\sme)?)|movie(s)?|new|latest|br((o|u)h?)*|^h(e|a)?(l)*(o)*|\
            mal(ayalam)?|t(h)?amil|file|that|find|und(o)*|kit(t(i|y)?)?o(w)?|\
            thar(u)?(o)*w?|kittum(o)*|aya(k)*(um(o)*)?|full\smovie|any(one)|\
            with\ssubtitle(s)?)",
        "", msg.text, flags=re.IGNORECASE) 

    query = query.strip() + " movie"
    result = await google_search(query)
    logging.info(result)
    result_parsed = []

    if not result:
        k = await msg.reply(
            text="<b>●I could not find the file you requested😕</b>\n\n<b>● Is the movie you asked about released OTT..?</b>\n\n<U>● Pay attention to the following…</U>\n\n<b>● Ask for correct spelling.</b>\n\n<b>● Do not ask for movies that are not released on OTT platforms.</b>\n\n<b>● Also ask [movie name, language] like this..‌‌</b>.",
            quote=True,
        )
        scheduler.add_job(k.delete, 'date', run_date=datetime.now() + timedelta(seconds=60),misfire_grace_time=60)
        return

    regex = re.compile(r".*(imdb|wikipedia).*", re.IGNORECASE)  # look for imdb / wiki results
    gs = list(filter(regex.match, result))
    logging.info(gs)
    result_parsed = [re.sub(
        r'\b(\-([a-zA-Z-\s])\-\simdb|(\-\s)?imdb|(\-\s)?wikipedia|\(|\)|\-|reviews|full|all|episode(s)?|film|movie|series)',
        '', i, flags=re.IGNORECASE) for i in gs]

    if not result_parsed:
        reg = re.compile(r"watch(\s[a-zA-Z0-9_\s\-\(\)]*)*\|.*",
                         re.IGNORECASE)  # match something like Watch Niram | Amazon Prime
        for mv in result:
            match = reg.match(mv)
            if match:
                result_parsed.append(match.group(1))

    user = msg.from_user.id if msg.from_user else 0
    movielist = []
    result_parsed = list(dict.fromkeys(result_parsed))  # removing duplicates https://stackoverflow.com/a/7961425
    if len(result_parsed) > 3:
        result_parsed = result_parsed[:3]
        logging.info(result_parsed)
    if result_parsed:
        for mov in result_parsed:
            imdb_s = await get_poster(mov.strip(), bulk=True)  # searching each keyword in imdb
            if imdb_s:
                movielist += [movie.get('title') for movie in imdb_s]

    movielist += [(re.sub(r'(\-|\(|\)|_)', '', i, flags=re.IGNORECASE)).strip() for i in result_parsed]
    movielist = list(dict.fromkeys(movielist))  # removing duplicates

    if not movielist:
        k = await msg.reply(
            text="I couldn't find anything related to that. Check your spelling",
            quote=True,
        )
        scheduler.add_job(k.delete, 'date', run_date=datetime.now() + timedelta(seconds=8),misfire_grace_time=60)
        return

    SPELL_CHECK[msg.id] = movielist
    btn = [[
        InlineKeyboardButton(
            text=movie.strip(),
            callback_data=f"spolling#{user}#{i}",
        )
    ] for i, movie in enumerate(movielist)]

    btn.append([InlineKeyboardButton(text="Close", callback_data=f'spolling#{user}#close_spellcheck')])
    k = await msg.reply("I couldn't find anything related to that\nDid you mean any one of these?", True,
                    reply_markup=InlineKeyboardMarkup(btn))
    scheduler.add_job(k.delete, 'date', run_date=datetime.now() + timedelta(seconds=60),misfire_grace_time=60)


async def manual_filters(client: Client, message: Message, text=False):

    group_id = message.chat.id
    name = text or message.text
    reply_id = message.reply_to_message_id if message.reply_to_message else message.id
    keywords = await get_filters(group_id)
    seconds = await get_config("DELETE_TIME", DELETE_TIME)

    for keyword in reversed(sorted(keywords, key=len)):
        pattern = r"( |^|[^\w])" + re.escape(keyword) + r"( |$|[^\w])"
        if re.search(pattern, name, flags=re.IGNORECASE):
            reply_text, btn, alert, fileid = await find_filter(group_id, keyword)

            if reply_text:
                reply_text = reply_text.replace("\\n", "\n").replace("\\t", "\t")

            if btn is not None:
                try:
                    if fileid == "None":
                        k=await client.send_message(
                            group_id,
                            reply_text,
                            disable_web_page_preview=True,
                            reply_markup=InlineKeyboardMarkup(eval(btn)) if btn != "[]" else None,
                            reply_to_message_id=reply_id
                        )
                    else:
                        k=await message.reply_cached_media(
                            fileid,
                            caption=reply_text or "",
                            reply_markup=InlineKeyboardMarkup(eval(btn)) if btn != "[]" else None,
                            reply_to_message_id=reply_id
                        )
                except Exception as e:
                    logger.exception(e, exc_info=True)
                
                scheduler.add_job(
                    delete_msg, 'date', args=[client, k, message.from_user.id], 
                    run_date=datetime.now() + timedelta(seconds=seconds)
                )
                
                break
    else:
        return False


async def delete_msg(bot: Client, msg: Message, user_id: int): 
    
    await msg.delete()
    if not msg.reply_to_message:
        return 
    await msg.reply_to_message.delete()
    k = await msg.reply_to_message.reply(
        f"Hey {msg.reply_to_message.from_user.mention},\n\n"
        "<b>Your Request Has Been Deleted👍🏻</b>\n<i>(Due To Avoid Copyrights Issue😌)</i>\n\n<b>Iꜰ Yᴏᴜ Wᴀɴᴛ Tʜᴀᴛ Fɪʟᴇ, Rᴇqᴜᴇꜱᴛ Aɢᴀɪɴ ❤️</b>\n",
    )

    scheduler.add_job(k.delete, 'date', run_date=datetime.now() + timedelta(hours=2), misfire_grace_time=60)


@Client.on_callback_query(filters.regex(r"files?_?#.+"), group=-2)
async def file_cb(bot: Client, update: CallbackQuery):

    ident, file_id = update.data.split("#")
    files_ = await get_file_details(file_id)
    if not files_:
        return await update.answer('No such file exist.')

    files = files_[0]
    title = files.file_name
    size = get_size(files.file_size)
    f_caption = files.caption
    settings = await get_settings(update.message.chat.id)

    if CUSTOM_FILE_CAPTION:
        try:
            f_caption = CUSTOM_FILE_CAPTION.format(file_name='' if title is None else title,
                                                    file_size='' if size is None else size,
                                                    file_caption='' if f_caption is None else f_caption)
        except Exception as e:
            logger.exception(e)
        f_caption = f_caption

    if f_caption is None:
        f_caption = f"{files.file_name}"

    try:
        if (AUTH_CHANNEL or REQ_CHANNEL) and not await is_subscribed(bot, update):
            await update.answer(url=f"https://t.me/{temp.U_NAME}?start={ident}_{file_id}")
            return
        elif settings['botpm']:
            await update.answer(url=f"https://t.me/{temp.U_NAME}?start={ident}_{file_id}")
            return
        else:
            await bot.send_cached_media(
                chat_id=update.from_user.id,
                file_id=file_id,
                caption=f_caption,
                protect_content=True if ident == "filep" else False,
            )
            if not update.message.chat.type == enums.ChatType.PRIVATE:
                await update.answer('Check PM, I have sent files in pm', show_alert=True)
    except UserIsBlocked:
        await update.answer('You Are Blocked to use me', show_alert=True)
    except PeerIdInvalid:
        await update.answer(url=f"https://t.me/{temp.U_NAME}?start={ident}_{file_id}")
    except Exception as e:
        await update.answer(url=f"https://t.me/{temp.U_NAME}?start={ident}_{file_id}")
        logger.exception(e, exc_info=True)



def auto_restart():
    os.execl(executable,executable,"bot.py")


# scheduler.add_job(auto_restart,'interval', hours=10)

scheduler.start()
