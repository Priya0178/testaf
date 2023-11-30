import re
import logging
import base64
import asyncio

from struct import pack
from argparse import Namespace
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from motor.motor_asyncio import AsyncIOMotorClient
from motor.core import AgnosticCollection, AgnosticDatabase
from marshmallow.exceptions import ValidationError
from info import DATABASE_NAME, COLLECTION_NAME, USE_CAPTION_FILTER, DATABASE_URI, DATABASE_URIS
from utils import temp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

count = 0 

CLIENTS = dict(
    (x, AsyncIOMotorClient(y)) for x, y in enumerate(DATABASE_URIS)
)
P_COLLECTION = CLIENTS[0][DATABASE_NAME][COLLECTION_NAME]
NODE = 0

class Struct(Namespace):
    def __init__(self, k: dict):
        for a, b in k.items():
            if a == "_id":
                a = "file_id" 
            if isinstance(b, (list, tuple)):
               setattr(self, a, [Struct(x) if isinstance(x, dict) else x for x in b])
            else:
               setattr(self, a, Struct(b) if isinstance(b, dict) else b)


def get_db_col():

    global NODE

    client = CLIENTS[NODE]
    if NODE < len(DATABASE_URIS) - 1:
        NODE += 1
    else:
        NODE = 0

    database: AgnosticDatabase = client[DATABASE_NAME]
    collection: AgnosticCollection = database[COLLECTION_NAME]
    return database, collection


async def ensure_indexes():
    for client in CLIENTS.values():
        collection = client[DATABASE_NAME][COLLECTION_NAME]
        await collection.create_index([("file_name", "text")])


async def save_file(media, indextoall=False):
    """Save file in database"""

    file_id, file_ref = unpack_new_file_id(media.file_id)
    rbool = False
    rid = 0
    media.file_name = "NO_NAME" if media.file_name == None else media.file_name

    if indextoall:
        items = CLIENTS.items()
    else:
        items = [(0, CLIENTS[0])]

    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))

    for db_id, client in items:
        collection = client[DATABASE_NAME][COLLECTION_NAME]
        try:
            file = dict(
                _id=file_id,
                file_ref=file_ref,
                file_name=file_name,
                file_size=media.file_size,
                file_type=media.file_type,
                mime_type=media.mime_type,
                caption=media.caption.html if media.caption else None,
            )
            await collection.insert_one(file)
        except ValidationError:
            logger.exception(f'Error occurred while saving file in database - {db_id}')
            if rid != 1:
                rid = 2
                rbool = False
            # return False, 2
        except DuplicateKeyError:
            logger.warning(media.file_name + f" is already saved in database - {db_id}")
            if rid != 1:
                rid = 0
                rbool = False
            # return False, 0
        else:
            logger.info(media.file_name + f" is saved in database - {db_id}")
            rid = 1
            rbool = True
            # return True, 1
    
    return rbool, rid


async def get_search_results(query):
    """For given query return (results)"""

    query = query.strip()

    if not query:
        pattern = "."
    else:
        pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
        pattern = pattern.replace(' ', r'.*[\s\.\+\-_]')

    try:
        regex = re.compile(pattern, flags=re.IGNORECASE)
    except:
        return []

    if USE_CAPTION_FILTER:
        filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter = {'file_name': regex}


    # Get Database and Collection obj from db client
    _, collection = get_db_col()

    _ids = []
    obj_files = []

    cursor = collection.find(filter)

    # Sort by recent
    cursor.sort('$natural', -1)

    # Slice files according to offset and max results
    # cursor.skip(offset).limit(max_results)

    # Get list of files
    files = await cursor.to_list(length=600)
    for x in files:
        if x["_id"] in _ids:
            continue
        else:
            _ids.append(x["_id"])
            obj_files.append(Struct(x))

    return obj_files


async def get_inline_results(query, file_type=None, max_results=10, offset=0, filter=False):
    """For given query return (results, next_offset)"""

    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')
    
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return []

    if USE_CAPTION_FILTER:
        filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    else:
        filter = {'file_name': regex}

    if file_type:
        filter['file_type'] = file_type

    # Get Database and Collection obj from db client
    _, collection = get_db_col()

    total_results = await collection.count_documents(filter)
    next_offset = offset + max_results

    if next_offset > total_results:
        next_offset = ''

    _ids = []
    results = []

    cursor = collection.find(filter)
    # Sort by recent
    cursor.sort('$natural', -1)
    # Slice files according to offset and max results
    cursor.skip(offset).limit(max_results)
    # Get list of files
    files = await cursor.to_list(length=max_results)
    for x in files:
        if x["_id"] in _ids:
            continue
        else:
            _ids.append(x["_id"])
            results.append(Struct(x))

    return results, next_offset, total_results



async def get_file_details(query):
    # Get Database and Collection obj from db client
    _, collection = get_db_col()
    filter = {'_id': query}
    cursor = collection.find(filter)
    filedetails = await cursor.to_list(length=1)
    filedetails = [Struct(x) for x in filedetails]
    return filedetails


async def total_filter_Counts():
    # Get Database and Collection obj from db client
    _, collection = get_db_col()
    total_results = 0
    total_results += await collection.count_documents({})
    return total_results


def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0

    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0

            r += bytes([i])

    return base64.urlsafe_b64encode(r).decode().rstrip("=")


def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")


def unpack_new_file_id(new_file_id):
    """Return file_id, file_ref"""
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref


async def migrate_db():
    pcollection = P_COLLECTION
    # get all documents from primary collection 
    files = await (pcollection.find()).to_list(length=None)
    tasks = []
    for i, x in CLIENTS.items():
        if i == 0:
            continue
        collection = x[DATABASE_NAME][COLLECTION_NAME]
        # collection.drop()
        tasks.append(asyncio.create_task(_insert_collection(collection, files, i)))
    await asyncio.gather(*tasks)
    return True


async def _insert_collection(collection, files, db_id):
    
    validation_errors = 0        
    # copy all documents from primary collection to secondary collection
    for file in files:
        try:
            await collection.insert_one(file)
        except ValidationError:
            pass
        except DuplicateKeyError:
            pass

    logger.info(f"Database migrated to db {db_id}!")
    logger.info(f"Total Validation errors in db {db_id} = {validation_errors}")

