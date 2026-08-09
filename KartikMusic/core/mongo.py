from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_DB_URI
from ..logging import LOGGER


LOGGER(__name__).info("Connecting to your Mongo Database...")

try:
    # Motor async MongoDB client
    _mongo_async_ = AsyncIOMotorClient(
        MONGO_DB_URI,
        serverSelectionTimeoutMS=10000,
    )

    # Database name
    mongodb = _mongo_async_.get_default_database()

    LOGGER(__name__).info("Connected to your Mongo Database.")

except Exception as e:
    LOGGER(__name__).error(
        f"Failed to connect to your Mongo Database: {e}"
    )
    raise
