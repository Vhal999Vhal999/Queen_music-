#
# Copyright (C) 2025-present by TheAloneTeam@Github, < https://github.com/TheAloneTeam >.
#
# This file is part of < https://github.com/TheAloneTeam/KartikMusic > project,
# and is released under the "MIT License".
# Please see < https://github.com/TheAloneTeam/KartikMusic/blob/master/LICENSE >
#
# All rights reserved.
#

import asyncio
import os
import random
import re
from typing import Union

import aiohttp
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from py_yt import Playlist, VideosSearch

from KartikMusic import logger
from KartikMusic.helpers import Track


# =========================================================
# CONFIG
# =========================================================

API_URL = os.getenv(
    "SHRUTI_API_URL",
    "https://api01.shrutibots.site",
).rstrip("/")

API_KEY = os.getenv(
    "SHRUTI_API_KEY",
    "ShrutiBotsfhGT4c09sFRRuQIB6yCG",
)

DOWNLOAD_DIR = "downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# =========================================================
# HELPERS
# =========================================================

def time_to_seconds(value) -> int:
    """Convert HH:MM:SS / MM:SS to seconds safely."""
    if not value:
        return 0

    try:
        total = 0

        for part in str(value).split(":"):
            total = total * 60 + int(part)

        return total

    except (TypeError, ValueError):
        return 0


def extract_video_id(link: str) -> str:
    """Extract an 11-character YouTube video ID."""

    if not link:
        return ""

    link = str(link).strip()

    # Already a video ID
    if re.fullmatch(
        r"[A-Za-z0-9_-]{11}",
        link,
    ):
        return link

    patterns = [
        r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:[?&]v=)([A-Za-z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            link,
        )

        if match:
            return match.group(1)

    return ""


def clean_youtube_url(link: str) -> str:
    """Clean YouTube URL."""

    if not link:
        return ""

    video_id = extract_video_id(link)

    if video_id:
        return (
            "https://www.youtube.com/watch?v="
            + video_id
        )

    return str(link).split("&")[0]


def thumbnail_from_result(data: dict) -> str:
    """Safely get thumbnail."""

    try:
        thumbnails = data.get(
            "thumbnails"
        ) or []

        if not thumbnails:
            return ""

        return (
            thumbnails[-1]
            .get("url", "")
            .split("?")[0]
        )

    except Exception:
        return ""


# =========================================================
# DOWNLOAD HELPERS
# =========================================================

async def _api_download(
    link: str,
    media_type: str,
) -> str | None:
    """
    Download audio/video using configured API.

    Returns local file path on success.
    """

    video_id = extract_video_id(
        link
    )

    if not video_id:
        video_id = str(
            link or ""
        ).strip()

    if not video_id:
        return None

    extension = (
        "mp4"
        if media_type == "video"
        else "mp3"
    )

    file_path = os.path.join(
        DOWNLOAD_DIR,
        f"{video_id}.{extension}",
    )

    # Use cached file
    if (
        os.path.exists(file_path)
        and os.path.getsize(file_path) > 1024
    ):
        return file_path

    params = {
        "url": video_id,
        "type": media_type,
    }

    if API_KEY:
        params["api_key"] = API_KEY

    timeout = aiohttp.ClientTimeout(
        total=600,
        connect=15,
        sock_read=120,
    )

    try:

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                f"{API_URL}/download",
                params=params,
            ) as response:

                if response.status != 200:

                    logger.warning(
                        "Download API returned HTTP %s for %s",
                        response.status,
                        video_id,
                    )

                    return None

                content_type = (
                    response.headers
                    .get(
                        "Content-Type",
                        "",
                    )
                    .lower()
                )

                # -----------------------------------------
                # JSON response
                # -----------------------------------------

                if "json" in content_type:

                    try:

                        data = await response.json(
                            content_type=None
                        )

                    except Exception:

                        return None

                    download_url = (
                        data.get("url")
                        or data.get(
                            "download_url"
                        )
                        or data.get("link")
                        or data.get("result")
                    )

                    if not isinstance(
                        download_url,
                        str,
                    ):
                        return None

                    if not download_url.startswith(
                        "http"
                    ):
                        return None

                    async with session.get(
                        download_url
                    ) as media_response:

                        if media_response.status not in (
                            200,
                            206,
                        ):
                            return None

                        with open(
                            file_path,
                            "wb",
                        ) as file:

                            async for chunk in (
                                media_response
                                .content
                                .iter_chunked(
                                    131072
                                )
                            ):

                                if chunk:
                                    file.write(
                                        chunk
                                    )

                # -----------------------------------------
                # Direct media response
                # -----------------------------------------

                else:

                    with open(
                        file_path,
                        "wb",
                    ) as file:

                        async for chunk in (
                            response
                            .content
                            .iter_chunked(
                                131072
                            )
                        ):

                            if chunk:
                                file.write(
                                    chunk
                                )

        if (
            os.path.exists(file_path)
            and os.path.getsize(file_path) > 1024
        ):
            return file_path

    except asyncio.CancelledError:
        raise

    except Exception as e:

        logger.warning(
            "API download failed for %s: %s",
            video_id,
            e,
        )

    # Remove incomplete file
    try:

        if os.path.exists(file_path):
            os.remove(file_path)

    except OSError:
        pass

    return None


async def download_song(
    link: str,
) -> str | None:

    return await _api_download(
        link,
        "audio",
    )


async def download_video(
    link: str,
) -> str | None:

    return await _api_download(
        link,
        "video",
    )


# =========================================================
# YOUTUBE API CLASS
# =========================================================

class YouTubeAPI:

    def __init__(self):

        self.base = (
            "https://www.youtube.com/watch?v="
        )

        self.listbase = (
            "https://www.youtube.com/playlist?list="
        )

        self.regex = re.compile(
            r"(youtube\.com|youtu\.be)",
            re.I,
        )

        self.search_cache = {}

        self.cache_lock = asyncio.Lock()


    # =====================================================
    # EXISTS
    # =====================================================

    async def exists(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = (
                self.base
                + str(link)
            )

        return bool(
            self.regex.search(
                str(link or "")
            )
        )


    # =====================================================
    # MESSAGE URL
    # =====================================================

    async def url(
        self,
        message_1: Message,
    ) -> Union[str, None]:

        messages = [
            message_1
        ]

        if message_1.reply_to_message:
            messages.append(
                message_1.reply_to_message
            )

        for message in messages:

            text = (
                message.text
                or message.caption
                or ""
            )

            entities = (
                message.entities
                or []
            )

            for entity in entities:

                if entity.type == (
                    MessageEntityType.URL
                ):

                    return text[
                        entity.offset:
                        entity.offset
                        + entity.length
                    ]

                if entity.type == (
                    MessageEntityType.TEXT_LINK
                ):

                    return entity.url

            caption_entities = (
                message.caption_entities
                or []
            )

            for entity in caption_entities:

                if entity.type == (
                    MessageEntityType.TEXT_LINK
                ):

                    return entity.url

                if entity.type == (
                    MessageEntityType.URL
                ):

                    return text[
                        entity.offset:
                        entity.offset
                        + entity.length
                    ]

        return None


    # =====================================================
    # SEARCH
    # =====================================================

    async def _search(
        self,
        query: str,
        limit: int = 1,
    ):

        query = str(
            query or ""
        ).strip()

        if not query:
            return []

        cache_key = (
            f"{query}|{limit}"
        )

        async with self.cache_lock:

            cached = self.search_cache.get(
                cache_key
            )

            if cached:
                return cached

        try:

            try:

                search = VideosSearch(
                    query,
                    limit=limit,
                    with_live=False,
                )

            except TypeError:

                # Old py_yt compatibility
                search = VideosSearch(
                    query,
                    limit=limit,
                )

            response = (
                await search.next()
            )

            results = (
                response or {}
            ).get("result") or []

            async with self.cache_lock:

                self.search_cache[
                    cache_key
                ] = results

                # Prevent unlimited cache growth
                if len(
                    self.search_cache
                ) > 200:

                    old_keys = list(
                        self.search_cache.keys()
                    )[:50]

                    for key in old_keys:

                        self.search_cache.pop(
                            key,
                            None,
                        )

            return results

        except Exception as e:

            logger.warning(
                "YouTube search failed: %s",
                e,
            )

            return []


    # =====================================================
    # DETAILS
    # =====================================================

    async def details(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = (
                self.base
                + str(link)
            )

        link = clean_youtube_url(
            link
        )

        results = await self._search(
            link,
            1,
        )

        if not results:

            raise ValueError(
                "YouTube video not found"
            )

        result = results[0]

        title = (
            result.get("title")
            or "Unknown"
        )

        duration = (
            result.get("duration")
            or "00:00"
        )

        duration_sec = (
            time_to_seconds(
                duration
            )
        )

        thumbnail = (
            thumbnail_from_result(
                result
            )
        )

        vidid = result.get(
            "id"
        )

        return (
            title,
            duration,
            duration_sec,
            thumbnail,
            vidid,
        )


    # =====================================================
    # TITLE
    # =====================================================

    async def title(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        data = await self.details(
            link,
            videoid,
        )

        return data[0]


    # =====================================================
    # DURATION
    # =====================================================

    async def duration(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        data = await self.details(
            link,
            videoid,
        )

        return data[1]


    # =====================================================
    # THUMBNAIL
    # =====================================================

    async def thumbnail(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        data = await self.details(
            link,
            videoid,
        )

        return data[3]


    # =====================================================
    # TRACK
    # =====================================================

    async def track(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = (
                self.base
                + str(link)
            )

        link = clean_youtube_url(
            link
        )

        results = await self._search(
            link,
            1,
        )

        if not results:

            raise ValueError(
                "YouTube track not found"
            )

        result = results[0]

        title = (
            result.get("title")
            or "Unknown"
        )

        duration_min = (
            result.get("duration")
            or "00:00"
        )

        vidid = result.get(
            "id"
        )

        yturl = (
            result.get("link")
            or self.base + vidid
        )

        thumbnail = (
            thumbnail_from_result(
                result
            )
        )

        track_details = {
            "title": title,
            "link": yturl,
            "vidid": vidid,
            "duration_min": duration_min,
            "thumb": thumbnail,
        }

        return (
            track_details,
            vidid,
        )


    # =====================================================
    # VIDEO
    # =====================================================

    async def video(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = (
                self.base
                + str(link)
            )

        try:

            file_path = await download_video(
                link
            )

            if file_path:

                return (
                    1,
                    file_path,
                )

            return (
                0,
                "Video download failed",
            )

        except Exception as e:

            return (
                0,
                f"Video download error: {e}",
            )


    # =====================================================
    # PLAYLIST
    # =====================================================

    async def playlist(
        self,
        link,
        limit,
        user_id,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = (
                self.listbase
                + str(link)
            )

        link = str(
            link
        ).split("&")[0]

        try:

            playlist = await Playlist.get(
                link
            )

            videos = (
                playlist or {}
            ).get("videos") or []

        except Exception as e:

            logger.warning(
                "Playlist error: %s",
                e,
            )

            return []

        ids = []

        seen = set()

        for data in videos[
            : int(limit)
        ]:

            if not data:
                continue

            vid = data.get(
                "id"
            )

            if not vid:
                continue

            if vid in seen:
                continue

            seen.add(
                vid
            )

            ids.append(
                vid
            )

        return ids


    # =====================================================
    # AUTOPLAY
    # =====================================================

    async def get_related(
        self,
        video_id: str,
        video: bool = False,
        max_duration: int = 0,
    ):
        """
        Find another YouTube song for autoplay.

        Does NOT use py_yt.Recommendations,
        so it works with py_yt versions where
        Recommendations is unavailable.
        """

        current_id = extract_video_id(
            video_id
        )

        if not current_id:
            return None

        # -------------------------------------------------
        # Get current video title
        # -------------------------------------------------

        try:

            options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
            }

            def extract():

                with yt_dlp.YoutubeDL(
                    options
                ) as ydl:

                    return ydl.extract_info(
                        self.base
                        + current_id,
                        download=False,
                    )

            info = await asyncio.to_thread(
                extract
            )

            title = (
                info.get("title")
                or ""
            )

        except Exception as e:

            logger.warning(
                "Autoplay title lookup failed: %s",
                e,
            )

            return None

        if not title:
            return None

        # -------------------------------------------------
        # Search similar songs
        # -------------------------------------------------

        results = await self._search(
            f"{title} song",
            10,
        )

        if not results:
            return None

        candidates = []

        for data in results:

            if not data:
                continue

            vid = data.get(
                "id"
            )

            # Don't play same song
            if not vid:
                continue

            if vid == current_id:
                continue

            duration = (
                data.get("duration")
                or "00:00"
            )

            duration_sec = (
                time_to_seconds(
                    duration
                )
            )

            # Duration filter
            if (
                max_duration
                and duration_sec > max_duration
            ):
                continue

            # No live streams
            if str(
                duration
            ).lower() in {
                "live",
                "streamed",
            }:

                continue

            candidates.append(
                {
                    "id": vid,
                    "title": (
                        data.get(
                            "title"
                        )
                        or "Unknown"
                    ),
                    "duration": duration,
                    "duration_sec": duration_sec,
                    "thumbnail": (
                        thumbnail_from_result(
                            data
                        )
                    ),
                    "link": (
                        data.get(
                            "link"
                        )
                        or self.base + vid
                    ),
                    "channel": (
                        data.get(
                            "channel"
                        )
                        or {}
                    ).get(
                        "name",
                        "",
                    ),
                }
            )

        if not candidates:
            return None

        selected = random.choice(
            candidates
        )

        try:

            return Track(
                id=selected["id"],
                channel_name=selected[
                    "channel"
                ],
                duration=selected[
                    "duration"
                ],
                duration_sec=selected[
                    "duration_sec"
                ],
                title=selected[
                    "title"
                ][:25],
                thumbnail=selected[
                    "thumbnail"
                ],
                url=selected[
                    "link"
                ],
                user="Autoplay",
                video=video,
            )

        except Exception as e:

            logger.error(
                "Autoplay Track creation failed: %s",
                e,
            )

            return None


    # =====================================================
    # FORMATS
    # =====================================================

    async def formats(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = (
                self.base
                + str(link)
            )

        link = clean_youtube_url(
            link
        )

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }

        def extract():

            with yt_dlp.YoutubeDL(
                options
            ) as ydl:

                return ydl.extract_info(
                    link,
                    download=False,
                )

        try:

            info = await asyncio.to_thread(
                extract
            )

        except Exception as e:

            logger.error(
                "Format extraction failed: %s",
                e,
            )

            return (
                [],
                link,
            )

        available = []

        for fmt in (
            info.get(
                "formats"
            )
            or []
        ):

            try:

                format_name = str(
                    fmt.get(
                        "format",
                        "",
                    )
                )

                if "dash" in (
                    format_name.lower()
                ):
                    continue

                available.append(
                    {
                        "format": fmt.get(
                            "format"
                        ),
                        "filesize": fmt.get(
                            "filesize"
                        ),
                        "format_id": fmt.get(
                            "format_id"
                        ),
                        "ext": fmt.get(
                            "ext"
                        ),
                        "format_note": fmt.get(
                            "format_note"
                        ),
                        "yturl": link,
                    }
                )

            except Exception:
                continue

        return (
            available,
            link,
        )


    # =====================================================
    # SLIDER
    # =====================================================

    async def slider(
        self,
        link: str,
        query_type: int,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = (
                self.base
                + str(link)
            )

        link = clean_youtube_url(
            link
        )

        try:

            try:

                search = VideosSearch(
                    link,
                    limit=10,
                    with_live=False,
                )

            except TypeError:

                search = VideosSearch(
                    link,
                    limit=10,
                )

            response = (
                await search.next()
            )

            results = (
                response or {}
            ).get("result") or []

        except Exception as e:

            logger.warning(
                "Slider search failed: %s",
                e,
            )

            raise ValueError(
                "YouTube search failed"
            )

        if (
            not results
            or query_type < 0
            or query_type >= len(
                results
            )
        ):

            raise ValueError(
                "YouTube result not available"
            )

        result = results[
            query_type
        ]

        title = (
            result.get(
                "title"
            )
            or "Unknown"
        )

        duration = (
            result.get(
                "duration"
            )
            or "00:00"
        )

        vidid = result.get(
            "id"
        )

        thumbnail = (
            thumbnail_from_result(
                result
            )
        )

        return (
            title,
            duration,
            thumbnail,
            vidid,
        )


    # =====================================================
    # DOWNLOAD
    # =====================================================

    async def download(
        self,
        link: str,
        mystic=None,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ):

        if videoid:
            link = (
                self.base
                + str(link)
            )

        try:

            if video:

                file_path = (
                    await download_video(
                        link
                    )
                )

            else:

                file_path = (
                    await download_song(
                        link
                    )
                )

            if file_path:

                return (
                    file_path,
                    True,
                )

            return (
                None,
                False,
            )

        except asyncio.CancelledError:
            raise

        except Exception as e:

            logger.error(
                "YouTube download error: %s",
                e,
            )

            return (
                None,
                False,
            )


# =========================================================
# IMPORTANT
# =========================================================
#
# DO NOT write:
#
#     YouTube = YouTubeAPI()
#
# because that creates an object and breaks:
#
#     yt = YouTube()
#
# Instead YouTube must remain a class/alias.
# =========================================================

YouTube = YouTubeAPI
