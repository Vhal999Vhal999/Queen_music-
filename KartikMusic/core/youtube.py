#
# Copyright (C) 2025-present by TheAloneTeam@Github
#

import asyncio
import os
import re
import time
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
    os.getenv(
        "API_URL",
        "https://api01.shrutibots.site",
    ),
).rstrip("/")

API_KEY = os.getenv(
    "SHRUTI_API_KEY",
    os.getenv("ShrutiBotsfhGT4c09sFRRuQIB6yCG", ""),
).strip()

DOWNLOAD_DIR = "downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# =========================================================
# HELPERS
# =========================================================

def extract_video_id(link: str) -> str:
    if not link:
        return ""

    link = str(link).strip()

    if re.fullmatch(r"[A-Za-z0-9_-]{11}", link):
        return link

    patterns = (
        r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:[?&]v=)([A-Za-z0-9_-]{11})",
    )

    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return match.group(1)

    return ""


def clean_url(link: str) -> str:
    vid = extract_video_id(link)

    if vid:
        return f"https://www.youtube.com/watch?v={vid}"

    return str(link).split("&")[0]


def time_to_seconds(value) -> int:
    if not value:
        return 0

    try:
        parts = str(value).split(":")
        total = 0

        for part in parts:
            total = total * 60 + int(part)

        return total

    except Exception:
        return 0


def thumbnail_from(data: dict) -> str:
    try:
        thumbnails = data.get("thumbnails") or []

        if thumbnails:
            return (
                thumbnails[-1]
                .get("url", "")
                .split("?")[0]
            )
    except Exception:
        pass

    return ""


# =========================================================
# FAST DIRECT STREAM URL
# =========================================================

def api_stream_url(
    video_id: str,
    video: bool = False,
) -> str | None:

    if not video_id:
        return None

    if not API_KEY:
        return None

    extension = "mp4" if video else "mp3"

    return (
        f"{API_URL}/downloads/"
        f"{API_KEY}/youtube.com/"
        f"{video_id}.{extension}"
    )


# =========================================================
# API DOWNLOAD FALLBACK
# =========================================================

async def api_download_file(
    video_id: str,
    video: bool = False,
) -> str | None:

    if not video_id:
        return None

    extension = "mp4" if video else "mp3"

    file_path = os.path.join(
        DOWNLOAD_DIR,
        f"{video_id}.{extension}",
    )

    if (
        os.path.exists(file_path)
        and os.path.getsize(file_path) > 1024
    ):
        return file_path

    params = {
        "url": video_id,
        "type": "video" if video else "audio",
    }

    if API_KEY:
        params["api_key"] = API_KEY

    timeout = aiohttp.ClientTimeout(
        total=600,
        connect=15,
        sock_read=180,
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
                        "API download HTTP %s for %s",
                        response.status,
                        video_id,
                    )
                    return None

                content_type = (
                    response.headers
                    .get("Content-Type", "")
                    .lower()
                )

                # API returned JSON
                if "json" in content_type:

                    data = await response.json(
                        content_type=None
                    )

                    stream = (
                        data.get("url")
                        or data.get("download_url")
                        or data.get("link")
                    )

                    if not stream:
                        return None

                    async with session.get(
                        stream
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
            "API file download failed: %s",
            e,
        )

    return None


# =========================================================
# YT-DLP FALLBACK
# =========================================================

async def ytdlp_download(
    video_id: str,
    video: bool = False,
) -> str | None:

    if not video_id:
        return None

    extension = "mp4" if video else "mp3"

    expected = os.path.join(
        DOWNLOAD_DIR,
        f"{video_id}.{extension}",
    )

    if (
        os.path.exists(expected)
        and os.path.getsize(expected) > 1024
    ):
        return expected

    url = (
        f"https://www.youtube.com/watch?v="
        f"{video_id}"
    )

    if video:

        opts = {
            "format": (
                "bestvideo[ext=mp4]+"
                "bestaudio[ext=m4a]/"
                "best[ext=mp4]/best"
            ),
            "outtmpl": os.path.join(
                DOWNLOAD_DIR,
                f"{video_id}.%(ext)s",
            ),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 2,
            "fragment_retries": 2,
        }

    else:

        opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(
                DOWNLOAD_DIR,
                f"{video_id}.%(ext)s",
            ),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 2,
            "fragment_retries": 2,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

    try:

        def run():
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        await asyncio.to_thread(run)

        if (
            os.path.exists(expected)
            and os.path.getsize(expected) > 1024
        ):
            return expected

        for name in os.listdir(
            DOWNLOAD_DIR
        ):

            if name.startswith(
                video_id + "."
            ):

                path = os.path.join(
                    DOWNLOAD_DIR,
                    name,
                )

                if (
                    os.path.isfile(path)
                    and os.path.getsize(path) > 1024
                ):
                    return path

    except asyncio.CancelledError:
        raise

    except Exception as e:
        logger.warning(
            "yt-dlp failed: %s",
            e,
        )

    return None


# =========================================================
# DOWNLOAD FUNCTIONS
# =========================================================

async def download_song(
    link: str,
) -> str | None:

    video_id = extract_video_id(link)

    if not video_id:
        return None

    # IMPORTANT:
    # Direct URL is returned first.
    # This allows ffmpeg/PyTgCalls to start streaming
    # without waiting for the complete MP3 download.
    stream = api_stream_url(
        video_id,
        video=False,
    )

    if stream:
        return stream

    # Fallback
    return await api_download_file(
        video_id,
        video=False,
    ) or await ytdlp_download(
        video_id,
        video=False,
    )


async def download_video(
    link: str,
) -> str | None:

    video_id = extract_video_id(link)

    if not video_id:
        return None

    stream = api_stream_url(
        video_id,
        video=True,
    )

    if stream:
        return stream

    return await api_download_file(
        video_id,
        video=True,
    ) or await ytdlp_download(
        video_id,
        video=True,
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

        self.search_cache = {}

        self._session = None

        self._prefetch_cache = {}

    # =====================================================
    # SESSION
    # =====================================================

    async def session(self):

        if (
            self._session is None
            or self._session.closed
        ):

            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=30,
                    connect=8,
                )
            )

        return self._session

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
            re.search(
                r"(youtube\.com|youtu\.be)",
                str(link),
                re.I,
            )
        )

    # =====================================================
    # URL
    # =====================================================

    async def url(
        self,
        message_1: Message,
    ):

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

            entities = (
                message.caption_entities
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

        key = (
            f"{query}:{limit}"
        )

        cached = self.search_cache.get(
            key
        )

        if cached:
            return cached

        try:

            search = VideosSearch(
                query,
                limit=limit,
                with_live=False,
            )

            result = await search.next()

            results = (
                result.get("result")
                if result
                else []
            ) or []

            self.search_cache[key] = results

            return results

        except TypeError:

            try:

                search = VideosSearch(
                    query,
                    limit=limit,
                )

                result = await search.next()

                results = (
                    result.get("result")
                    if result
                    else []
                ) or []

                self.search_cache[key] = results

                return results

            except Exception as e:

                logger.error(
                    "Search error: %s",
                    e,
                )

        except Exception as e:

            logger.error(
                "Search error: %s",
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

        link = clean_url(link)

        results = await self._search(
            link,
            1,
        )

        if not results:
            raise ValueError(
                "YouTube result not found"
            )

        data = results[0]

        title = (
            data.get("title")
            or "Unknown"
        )

        duration = (
            data.get("duration")
            or "00:00"
        )

        duration_sec = time_to_seconds(
            duration
        )

        thumbnail = thumbnail_from(
            data
        )

        vidid = data.get("id")

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
            link = self.base + str(link)

        link = clean_url(link)

        results = await self._search(
            link,
            1,
        )

        if not results:
            raise ValueError(
                "YouTube track not found"
            )

        data = results[0]

        vidid = data.get("id")

        if not vidid:
            raise ValueError(
                "YouTube video ID missing"
            )

        title = (
            data.get("title")
            or "Unknown"
        )

        duration = (
            data.get("duration")
            or "00:00"
        )

        yturl = (
            data.get("link")
            or self.base + vidid
        )

        thumbnail = thumbnail_from(
            data
        )

        track_details = {
            "title": title,
            "link": yturl,
            "vidid": vidid,
            "duration_min": duration,
            "thumb": thumbnail,
        }

        return (
            track_details,
            vidid,
        )

    # =====================================================
    # RELATED / AUTOPLAY
    # =====================================================

    async def get_related(
        self,
        video_id: str,
        video: bool = False,
        max_duration: int = 0,
    ) -> Track | None:

        vid = extract_video_id(
            video_id
        )

        if not vid:
            return None

        try:

            current = await self._search(
                vid,
                1,
            )

            title = ""

            if current:
                title = (
                    current[0].get("title")
                    or ""
                )

            if not title:
                return None

            queries = [
                f"{title} song",
                f"{title} music",
            ]

            candidates = []

            for query in queries:

                results = await self._search(
                    query,
                    10,
                )

                for data in results:

                    item_id = data.get(
                        "id"
                    )

                    if not item_id:
                        continue

                    if item_id == vid:
                        continue

                    duration = (
                        data.get(
                            "duration"
                        )
                        or "00:00"
                    )

                    duration_sec = (
                        time_to_seconds(
                            duration
                        )
                    )

                    if not duration_sec:
                        continue

                    if (
                        max_duration
                        and duration_sec
                        > max_duration
                    ):
                        continue

                    if any(
                        x["id"] == item_id
                        for x in candidates
                    ):
                        continue

                    candidates.append(
                        {
                            "id": item_id,
                            "title": (
                                data.get(
                                    "title"
                                )
                                or "Unknown"
                            ),
                            "duration": duration,
                            "duration_sec": duration_sec,
                            "thumbnail": thumbnail_from(
                                data
                            ),
                            "link": (
                                data.get(
                                    "link"
                                )
                                or self.base
                                + item_id
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

                if candidates:
                    break

            if not candidates:
                return None

            selected = candidates[
                int(
                    time.time()
                    * 1000
                )
                % len(candidates)
            ]

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
                "Autoplay related error: %s",
                e,
            )

        return None

    # =====================================================
    # PREFETCH
    # =====================================================

    async def prefetch(
        self,
        link: str,
        video: bool = False,
    ):

        vid = extract_video_id(link)

        if not vid:
            return False

        key = (
            f"{vid}:"
            f"{'video' if video else 'audio'}"
        )

        now = time.time()

        if (
            key in self._prefetch_cache
            and now
            - self._prefetch_cache[key]
            < 30
        ):
            return True

        self._prefetch_cache[key] = now

        try:

            # Just warm the API endpoint.
            # Do not download the entire file.
            stream = api_stream_url(
                vid,
                video,
            )

            if not stream:
                return False

            client = await self.session()

            async with client.head(
                stream,
                allow_redirects=True,
            ) as response:

                return response.status in (
                    200,
                    206,
                    302,
                    307,
                )

        except Exception:

            return False

    # =====================================================
    # VIDEO
    # =====================================================

    async def video(
        self,
        link: str,
        videoid: Union[bool, str] = None,
    ):

        if videoid:
            link = self.base + str(link)

        result = await download_video(
            link
        )

        if result:
            return 1, result

        return (
            0,
            "Video download failed",
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

            plist = await Playlist.get(
                link
            )

            videos = (
                plist.get("videos")
                or []
            )

            ids = []
            seen = set()

            for data in videos[
                : int(limit)
            ]:

                vid = data.get(
                    "id"
                )

                if not vid:
                    continue

                if vid in seen:
                    continue

                seen.add(vid)
                ids.append(vid)

            return ids

        except Exception as e:

            logger.warning(
                "Playlist error: %s",
                e,
            )

            return []

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

        link = clean_url(link)

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }

        try:

            def get_info():

                with yt_dlp.YoutubeDL(
                    options
                ) as ydl:

                    return ydl.extract_info(
                        link,
                        download=False,
                    )

            info = await asyncio.to_thread(
                get_info
            )

            available = []

            for fmt in (
                info.get("formats")
                or []
            ):

                try:

                    if (
                        "dash"
                        in str(
                            fmt.get(
                                "format",
                                "",
                            )
                        ).lower()
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

            return available, link

        except Exception:

            return [], link

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

        link = clean_url(link)

        results = await self._search(
            link,
            10,
        )

        if (
            not results
            or query_type >= len(results)
        ):
            raise ValueError(
                "YouTube result not found"
            )

        data = results[
            query_type
        ]

        return (
            data.get("title")
            or "Unknown",
            data.get("duration")
            or "00:00",
            thumbnail_from(data),
            data.get("id"),
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
    ) -> str | None:

        if videoid:
            link = self.base + str(link)

        if not link:
            return None

        try:

            # FAST PATH
            # Returns direct API URL.
            # call.py can give this URL directly
            # to ffmpeg/PyTgCalls.

            result = await (
                download_video(link)
                if video
                else download_song(link)
            )

            if result:
                return result

        except asyncio.CancelledError:
            raise

        except Exception as e:

            logger.error(
                "YouTube download error: %s",
                e,
            )

        return None

    # =====================================================
    # CLOSE
    # =====================================================

    async def close(self):

        if (
            self._session
            and not self._session.closed
        ):

            await self._session.close()


# =========================================================
# IMPORTANT
# =========================================================
#
# Your code uses:
#
#     yt = YouTube()
#
# Therefore YouTube MUST be a class.
#
# DO NOT write:
#
#     YouTube = YouTubeAPI()
#
# =========================================================

YouTube = YouTubeAPI
