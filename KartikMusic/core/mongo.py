# -----------------------------------------------
# 🔸 StrangerMusic Project
# 🔹 Developed & Maintained by: Shashank Shukla (https://github.com/itzshukla)
# 📅 Copyright © 2022 – All Rights Reserved
#
# 📖 License:
# This source code is open for educational and non-commercial use ONLY.
# You are required to retain this credit in all copies or substantial portions of this file.
# Commercial use, redistribution, or removal of this notice is strictly prohibited
# without prior written permission from the author.
#
# ❤️ Made with dedication and love by ItzShukla
# -----------------------------------------------

from random import randint
from time import time

from motor.motor_asyncio import AsyncIOMotorClient

from KartikMusic import config, logger, userbot



LOGGER.info("Connecting to your Mongo Database...")

try:
    # Old Motor-compatible async MongoDB client.
    _mongo_async_ = AsyncIOMotorClient(
        MONGO_DB_URI,
        serverSelectionTimeoutMS=10000,
    )

    # Database name remains exactly the same: Anon
    mongodb = _mongo_async_.Anon

    LOGGER(__name__).info("Mongo Database client initialized.")

except Exception as e:
    LOGGER(__name__).error(f"Failed to initialize Mongo Database: {e}")
    raise


async def ping_database():
    """Check that MongoDB is reachable."""
    await _mongo_async_.admin.command("ping")
    return True


async def close_database():
    """Close the MongoDB connection."""
    _mongo_async_.close()
    
