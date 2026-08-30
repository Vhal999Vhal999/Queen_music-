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

API_URL = os.environ.get(
    "SHRUTI_API_URL",
    "https://api01.shrutibots.site",
).rstrip("/")

API_KEY = os.environ.get(
    "SHRUTI_API_KEY",
    "ShrutiBotsfhGT4c09sFRRuQIB6yCG",
)

DOWNLOAD_DIR = "downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# =========================================================
# HELPERS
# =========================================================

def time_to_seconds(value) -> int:
    """Convert HH:MM:SS / MM:SS into seconds safely."""
    if not value:
        return 0

    try:
        parts = [int(x) for x in str(value).split(":")]

        total = 0
        for part in parts:
            total = total * 60 + part

        return total

    except (TypeError, ValueError):
        return 0


def extract_video_id(link: str) -> str:
    """Extract YouTube video ID from URL or ID."""

    if not link:
        return ""

    link = str(link).strip()

    # Already an ID
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", link):
        return link

    patterns = [
        r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:[?&]v=)([A-Za-z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, link)

        if match:
            return match.group(1)

    return ""


def clean_youtube_url(link: str) -> str:
    """Return a clean YouTube watch URL."""

    video_id = extract_video_id(link)

    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    return str(link).split("&")[0]


def thumbnail_from_result(data: dict) -> str:
    """Safely extract thumbnail URL."""

    thumbnails = data.get("thumbnails") or []

    if not thumbnails:
        return ""

    try:
        return (
            thumbnails[-1]
            .get("url", "")
            .split("?")[0]
        )
    except Exception:
        return ""


# =========================================================
# API DOWNLOAD
# =========================================================

async def _api_download(
    link: str,
    media_type: str,
) -> str | None:
    """
    Download audio/video from configured API.

    Returns:
        Local file path or None.
    """

    video_id = extract_video_id(link)

    if not video_id:
        video_id = str(link).strip()

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

    # Existing file
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
        total=600 if media_type == "video" else 300,
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
                        "YouTube API returned HTTP %s for %s",
                        response.status,
                        video_id,
                    )

                    return None

                content_type = (
                    response.headers
                    .get("Content-Type", "")
                    .lower()
                )

                # -------------------------------------------------
                # Some APIs return JSON containing the real URL.
                # -------------------------------------------------

                if "json" in content_type:

                    try:
                        data = await response.json(
                            content_type=None
                        )
                    except Exception:
                        return None

                    download_url = (
                        data.get("url")
                        or data.get("download_url")
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
                                .iter_chunked(131072)
                            ):

                                if chunk:
                                    file.write(chunk)

                # -------------------------------------------------
                # API directly returns media.
                # -------------------------------------------------

                else:

                    with open(
                        file_path,
                        "wb",
                    ) as file:

                        async for chunk in (
                            response
                            .content
                            .iter_chunked(131072)
                        ):

                            if chunk:
                                file.write(chunk)

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

    # Remove broken file
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
# YOUTUBE API
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
            r"(?:youtube\.com|youtu\.be)",
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
            link = self.base + str(link)

        return bool(
            self.regex.search(
                str(link or "")
            )
        )


    # =====================================================
    # GET URL FROM MESSAGE
    # =====================================================

    async def url(
        self,
        message_1: Message,
    ) -> Union[str, None]:

        messages = [message_1]

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

            # Message entities
            if message.entities:

                for entity in message.entities:

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

            # Caption entities
            if message.caption_entities:

                for entity in message.caption_entities:

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

        query = str(query).strip()

        if not query:
            return []

        cache_key = (
            f"{query}|{limit}"
        )

        # Cache
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

                # Compatibility with older py_yt
                search = VideosSearch(
                    query,
                    limit=limit,
                )

            response = await search.next()

            results = (
                response or {}
            ).get("result") or []

            # Keep cache small
            async with self.cache_lock:

                self.search_cache[
                    cache_key
                ] = results

                if len(self.search_cache) > 200:

                    keys = list(
                        self.search_cache.keys()
                    )[:50]

                    for key in keys:
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
            link = self.base + str(link)

        link = clean_youtube_url(link)

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

        thumbnail = thumbnail_from_result(
            result
        )

        vidid = result.get("id")

        duration_sec = time_to_seconds(
            duration
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

        return (
            await self.details(
                link,
                videoid,
            )
        )[0]


    # =====================================================
    # DURATION
    # =====================================================

    async def duration(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        return (
            await self.details(
                link,
                videoid,
            )
        )[1]


    # =====================================================
    # THUMBNAIL
    # =====================================================

    async def thumbnail(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        return (
            await self.details(
                link,
                videoid,
            )
        )[3]


    # =====================================================
    # TRACK
    # =====================================================

    async def track(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + str(link)

        link = clean_youtube_url(link)

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

        vidid = result.get("id")

        yturl = (
            result.get("link")
            or self.base + vidid
        )

        thumbnail = thumbnail_from_result(
            result
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
    # VIDEO DOWNLOAD
    # =====================================================

    async def video(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + str(link)

        try:

            downloaded_file = (
                await download_video(link)
            )

            if downloaded_file:
                return (
                    1,
                    downloaded_file,
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

        link = str(link).split(
            "&"
        )[0]

        try:

            playlist = await Playlist.get(
                link
            )

            videos = (
                playlist or {}
            ).get("videos") or []

        except Exception as e:

            logger.warning(
                "Playlist fetch failed: %s",
                e,
            )

            return []

        ids = []

        seen = set()

        for data in videos[:int(limit)]:

            if not data:
                continue

            vid = data.get("id")

            if not vid:
                continue

            if vid in seen:
                continue

            seen.add(vid)

            ids.append(vid)

        return ids


    # =====================================================
    # AUTOPLAY / RELATED SONG
    # =====================================================

    async def get_related(
        self,
        video_id: str,
        video: bool = False,
        max_duration: int = 0,
    ):
        """
        Autoplay replacement for py_yt.Recommendations.

        This is intentionally independent of the
        Recommendations class because some py_yt versions
        don't provide it.

        Flow:

        1. Get current video's title with yt-dlp.
        2. Search YouTube for similar results.
        3. Remove current video.
        4. Remove live videos.
        5. Apply max duration.
        6. Randomly select another track.
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

            ytdl_options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
            }

            def extract():

                with yt_dlp.YoutubeDL(
                    ytdl_options
                ) as ydl:

                    return ydl.extract_info(
                        self.base + current_id,
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
        # Search related songs
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

            vid = data.get("id")

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

            # Maximum duration
            if (
                max_duration
                and duration_sec > max_duration
            ):
                continue

            # Ignore live streams
            if str(duration).lower() in {
                "live",
                "streamed",
            }:
                continue

            thumbnail = (
                thumbnail_from_result(
                    data
                )
            )

            link = (
                data.get("link")
                or self.base + vid
            )

            candidates.append(
                {
                    "id": vid,
                    "title": (
                        data.get("title")
                        or "Unknown"
                    ),
                    "duration": duration,
                    "duration_sec": duration_sec,
                    "thumbnail": thumbnail,
                    "link": link,
                    "channel": (
                        data.get("channel")
                        or {}
                    ).get(
                        "name",
                        "",
                    ),
                }
            )

        if not candidates:
            return None

        # Random related song
        selected = random.choice(
            candidates
        )

        # -------------------------------------------------
        # Track object
        # -------------------------------------------------

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
                "Failed creating autoplay Track: %s",
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
            link = self.base + str(link)

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
                "yt-dlp format error: %s",
                e,
            )

            return [], link

        formats_available = []

        for fmt in info.get(
            "formats",
            [],
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

                formats_available.append(
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
            formats_available,
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
            link = self.base + str(link)

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
            or query_type >= len(results)
        ):
            raise ValueError(
                "YouTube search result not available"
            )

        result = results[
            query_type
        ]

        title = (
            result.get("title")
            or "Unknown"
        )

        duration = (
            result.get("duration")
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
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + str(link)

        try:

            if video:

                downloaded_file = (
                    await download_video(
                        link
                    )
                )

            else:

                downloaded_file = (
                    await download_song(
                        link
                    )
                )

            if downloaded_file:

                return (
                    downloaded_file,
                    True,
                )

            return (
                None,
                False,
            )

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
# GLOBAL INSTANCE
# =========================================================

YouTube = YouTubeAPI()
