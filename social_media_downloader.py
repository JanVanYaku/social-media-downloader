#######################################################################
# Author: Lehlohonolo Adolf Matobakele  
# Email: lehlohonolo.matobakele@gov.ls
# Contact: 00266 62320704
#######################################################################
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


DEFAULT_OUTPUT_DIR = Path("downloads")
SUPPORTED_MODES = {"audio", "video"}
SUPPORTED_PLAYLIST_MODES = {"ask", "single", "playlist"}
SUPPORTED_AUDIO_FORMATS = {"best", "aac", "flac", "m4a", "mp3", "opus", "vorbis", "wav"}
SUPPORTED_VIDEO_CONTAINERS = {"auto", "mkv", "mp4", "webm"}
SUPPORTED_COOKIE_BROWSERS = {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale"}
SUPPORTED_YOUTUBE_JS_RUNTIMES = {"auto", "bun", "deno", "node", "none", "quickjs"}
DEFAULT_VIDEO_QUALITY = "1080"
VIDEO_QUALITY_PRESETS = ["best", "2160", "1440", "1080", "720", "480", "360", "240"]
AUDIO_FILENAME = "%(artist,creator,uploader|Unknown Artist).120B - %(track,title|Unknown Title).120B [%(id)s].%(ext)s"
AUDIO_PLAYLIST_FILENAME = "%(playlist_index)03d - %(artist,creator,uploader|Unknown Artist).120B - %(track,title|Unknown Title).120B [%(id)s].%(ext)s"
MIN_YTDLP_VERSION = (2026, 8, 19)
MIN_YTDLP_VERSION_TEXT = "2026.08.19"
YOUTUBE_REMOTE_COMPONENTS = ("ejs:github", "ejs:npm")
DEFAULT_YOUTUBE_PLAYER_CLIENTS = "default,-android_vr"
BROWSER_COOKIE_ERROR_MARKERS = ("could not copy chrome cookie database", "failed to load cookies")
_YTDLP_VERSION_WARNING_PRINTED = False


class SimpleLogger:
    def __init__(self) -> None:
        self._youtube_help_printed = False
        self._browser_cookie_help_printed = False
        self.last_problem = ""

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug] "):
            return
        self.info(msg)

    def info(self, msg: str) -> None:
        if msg:
            print(msg, flush=True)

    def warning(self, msg: str) -> None:
        if msg:
            self.last_problem = msg
            print(f"Warning: {msg}", file=sys.stderr, flush=True)
            self._print_youtube_help_once(msg)
            self._print_browser_cookie_help_once(msg)

    def error(self, msg: str) -> None:
        if msg:
            self.last_problem = msg
            print(f"Error: {msg}", file=sys.stderr, flush=True)
            self._print_youtube_help_once(msg)
            self._print_browser_cookie_help_once(msg)

    def _print_youtube_help_once(self, msg: str) -> None:
        text = msg.lower()
        if self._youtube_help_printed:
            return
        if not any(marker in text for marker in ("http error 403", "sign in to confirm your age", "n challenge", "javascript runtime")):
            return
        self._youtube_help_printed = True
        print(
            "Tip: YouTube is blocking this media request. Try browser cookies "
            "such as --cookies-from-browser chrome, keep YouTube helpers enabled, "
            "and update yt-dlp with: python -m pip install --upgrade yt-dlp",
            file=sys.stderr,
            flush=True,
        )

    def _print_browser_cookie_help_once(self, msg: str) -> None:
        text = msg.lower()
        if self._browser_cookie_help_printed:
            return
        if not is_browser_cookie_error_text(text):
            return
        self._browser_cookie_help_printed = True
        print(
            "Tip: Browser cookies could not be read. Close Brave/Chrome completely, "
            "export a cookies.txt file and pass --cookies, or retry public media "
            "without --cookies-from-browser.",
            file=sys.stderr,
            flush=True,
        )


def require_ytdlp() -> Any:
    configure_ssl_cert_store()

    try:
        import yt_dlp
    except ImportError as exc:
        raise SystemExit(
            "yt-dlp is not installed. Install requirements first:\n"
            "  python -m pip install -r requirements.txt"
        ) from exc

    warn_if_outdated_ytdlp(yt_dlp)
    return yt_dlp


def configure_ssl_cert_store() -> None:
    """Use certifi's CA bundle when this Python install has no working default."""

    if os.environ.get("SSL_CERT_FILE"):
        return

    try:
        import certifi
    except ImportError:
        return

    os.environ["SSL_CERT_FILE"] = certifi.where()


def warn_if_outdated_ytdlp(yt_dlp: Any) -> None:
    global _YTDLP_VERSION_WARNING_PRINTED

    if _YTDLP_VERSION_WARNING_PRINTED:
        return

    try:
        from yt_dlp import version as ytdlp_version

        current = getattr(ytdlp_version, "__version__", "0")
    except Exception:
        return

    if parse_version_tuple(current) < MIN_YTDLP_VERSION:
        print(
            f"Warning: yt-dlp {current} is installed. YouTube download fixes need "
            f"yt-dlp {MIN_YTDLP_VERSION_TEXT} or newer. Update with:\n"
            "  python -m pip install --upgrade yt-dlp",
            file=sys.stderr,
        )
        _YTDLP_VERSION_WARNING_PRINTED = True


def parse_version_tuple(value: str) -> tuple[int, int, int]:
    parts = [int(part) for part in re.findall(r"\d+", value)[:3]]
    return tuple((parts + [0, 0, 0])[:3])


def enable_line_buffered_output() -> None:
    """Keep progress, warnings, and prompts in a sensible order on Windows."""

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except (AttributeError, OSError):
            pass


def get_ffmpeg_location() -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None

    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def clean_pasted_url(url: str) -> str:
    """Accept raw URLs and common Markdown/autolink text copied from chats."""

    cleaned = url.strip().strip("\"'").strip()

    markdown = re.fullmatch(r"\[[^\]]+\]\((https?://[^)\s]+)\)", cleaned)
    if markdown:
        cleaned = markdown.group(1)
    elif cleaned.startswith("<") and cleaned.endswith(">"):
        cleaned = cleaned[1:-1].strip()
    else:
        first_url = re.search(r"https?://[^\s<>\"]+", cleaned)
        if first_url and cleaned != first_url.group(0):
            cleaned = first_url.group(0)

    return cleaned.rstrip(".,;")


def validate_url(url: str) -> str:
    cleaned = clean_pasted_url(url)
    parsed = urlparse(cleaned)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("Please provide a valid http(s) media URL.")

    return cleaned


def prompt_for_url() -> str:
    value = input("Paste media link: ").strip()
    if not value:
        raise SystemExit("No URL provided.")
    return validate_url(value)


def prompt_for_mode() -> str:
    while True:
        value = input("Download as audio or video? [video/audio]: ").strip().lower()
        if not value:
            return "video"
        if value in SUPPORTED_MODES:
            return value
        print("Please type 'audio' or 'video'.")


def is_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "youtube.com" in host or "youtu.be" in host


def looks_like_playlist_url(url: str) -> bool:
    """Return True when a URL appears capable of resolving to multiple items."""

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parse_qs(parsed.query)

    if is_youtube_url(url):
        return "list" in query or path.startswith(("/playlist", "/channel", "/c/", "/user/", "/@", "/feeds/videos.xml"))

    playlist_markers = (
        "/playlist",
        "/playlists",
        "/channel",
        "/channels",
        "/album",
        "/albums",
        "/sets/",
        "/collection",
        "/profile",
        "/user/",
    )
    return any(marker in path for marker in playlist_markers)


def prompt_for_playlist_mode(url: str, args: argparse.Namespace) -> str:
    """Decide whether to download one item or the full playlist."""

    if args.allow_playlist:
        return "playlist"

    if args.playlist_items:
        return "playlist"

    if args.playlist_mode in {"single", "playlist"}:
        return args.playlist_mode

    if args.yes:
        return "single"

    if not looks_like_playlist_url(url):
        return "single"

    print("\nThis link looks like it may contain a playlist or multiple media items.")
    while True:
        value = input("Download one song/video or the full playlist? [one/playlist]: ").strip().lower()
        if not value:
            return "single"
        if value in {"one", "single", "song", "video", "item", "1"}:
            return "single"
        if value in {"playlist", "full", "all", "many"}:
            return "playlist"
        print("Please type 'one' or 'playlist'.")


def prompt_for_youtube_cookies(url: str, args: argparse.Namespace) -> None:
    """Offer browser cookies for YouTube links that may need login/age access."""

    if not is_youtube_url(url) or args.cookies or args.cookies_from_browser or args.yes or args.no_youtube_cookie_prompt:
        return

    print("\nSome YouTube playlist items may need your logged-in browser session, especially age-restricted media.")
    print("Choose a browser only if you are logged into YouTube there.")
    choices = "skip/chrome/edge/firefox/brave"
    while True:
        value = input(f"Use browser cookies? [{choices}]: ").strip().lower()
        if not value or value in {"skip", "no", "n"}:
            return
        if value in SUPPORTED_COOKIE_BROWSERS:
            args.cookies_from_browser = value
            print(f"Using YouTube cookies from {value}.")
            return
        print(f"Please type one of: {choices}")


def normalize_video_quality(value: str) -> str:
    """Normalize a video quality choice to 'best' or a numeric height."""

    cleaned = value.strip().lower().removesuffix("p")
    if cleaned in {"", "default"}:
        return DEFAULT_VIDEO_QUALITY
    if cleaned == "best":
        return "best"
    if cleaned.isdigit() and int(cleaned) > 0:
        return str(int(cleaned))
    raise SystemExit("--video-quality must be best or a resolution such as 1080, 720, or 480.")


def normalize_audio_format(value: str) -> str:
    """Normalize an audio format choice."""

    cleaned = value.strip().lower()
    if cleaned in {"", "default"}:
        return "mp3"
    if cleaned in SUPPORTED_AUDIO_FORMATS:
        return cleaned
    choices = ", ".join(sorted(SUPPORTED_AUDIO_FORMATS))
    raise SystemExit(f"--audio-format must be one of: {choices}")


def sanitize_filename_fragment(value: str | None, fallback: str) -> str:
    text = value or fallback
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:180] or fallback


def build_output_template(output_dir: Path, flat: bool, allow_playlist: bool, audio: bool = False) -> str:
    file_template = AUDIO_PLAYLIST_FILENAME if audio and allow_playlist else AUDIO_FILENAME if audio else None

    if flat:
        if allow_playlist:
            return str(output_dir / (file_template or "%(playlist_index)03d - %(title).180B [%(id)s].%(ext)s"))
        return str(output_dir / (file_template or "%(title).180B [%(id)s].%(ext)s"))
    if allow_playlist:
        return str(
            output_dir
            / "%(extractor_key)s"
            / "%(playlist_title).180B"
            / (file_template or "%(playlist_index)03d - %(title).180B [%(id)s].%(ext)s")
        )
    return str(output_dir / "%(extractor_key)s" / (file_template or "%(title).180B [%(id)s].%(ext)s"))


def parse_rate_limit(value: str | None) -> int | None:
    if not value:
        return None

    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmgt]?)(?:i?b?)?\s*", value, re.IGNORECASE)
    if not match:
        raise SystemExit('--rate-limit must look like "500K", "2M", or "1048576".')

    amount = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    return int(amount * multipliers[unit])


def build_youtube_js_runtime_options(args: argparse.Namespace) -> dict[str, dict[str, str]]:
    """Build yt-dlp's js_runtimes config, preferring Node when available."""

    choice = args.youtube_js_runtime.strip().lower()
    if choice == "none":
        return {}

    if choice == "auto":
        for runtime in ("node", "deno", "bun", "quickjs"):
            if runtime_path := shutil.which(runtime):
                return {runtime: {"path": runtime_path}}
        return {"node": {}, "deno": {}}

    runtime_path = shutil.which(choice)
    return {choice: {"path": runtime_path} if runtime_path else {}}


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def is_browser_cookie_error_text(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in BROWSER_COOKIE_ERROR_MARKERS)


def retry_without_browser_cookies(exc: Exception, args: argparse.Namespace) -> bool:
    if not getattr(args, "cookies_from_browser", None):
        return False
    if getattr(args, "_browser_cookie_fallback_used", False):
        return False
    if not is_browser_cookie_error_text(str(exc)):
        return False

    browser = args.cookies_from_browser
    args.cookies_from_browser = None
    args._browser_cookie_fallback_used = True
    print(
        f"Browser cookies from {browser} could not be loaded. Retrying without browser cookies.",
        file=sys.stderr,
        flush=True,
    )
    print(
        "If this media requires login, close the browser completely or export a cookies.txt file "
        "and pass it with --cookies.",
        file=sys.stderr,
        flush=True,
    )
    return True


def apply_youtube_helpers(options: dict[str, Any], args: argparse.Namespace) -> None:
    """Enable YouTube options that reduce 403 and n-challenge failures."""

    if not is_youtube_url(getattr(args, "url", "") or ""):
        return
    player_clients = split_csv(args.youtube_player_client)
    if player_clients:
        extractor_args = options.setdefault("extractor_args", {})
        youtube_args = extractor_args.setdefault("youtube", {})
        youtube_args["player_client"] = player_clients
    options["js_runtimes"] = build_youtube_js_runtime_options(args)
    if not args.no_youtube_remote_components:
        options["remote_components"] = list(YOUTUBE_REMOTE_COMPONENTS)


def common_options(args: argparse.Namespace, audio: bool = False) -> dict[str, Any]:
    skip_playlist_errors = bool(args.allow_playlist and not getattr(args, "stop_on_error", False))
    options: dict[str, Any] = {
        "logger": SimpleLogger(),
        "noplaylist": not args.allow_playlist,
        "outtmpl": build_output_template(args.output_dir, args.flat, args.allow_playlist, audio),
        "retries": args.retries,
        "fragment_retries": args.retries,
        "windowsfilenames": True,
        "trim_file_name": 180,
        "continuedl": True,
        "ignoreerrors": skip_playlist_errors,
        "skip_unavailable_fragments": True,
        "quiet": False,
        "no_warnings": False,
    }

    ffmpeg_location = get_ffmpeg_location()
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location

    if args.cookies:
        options["cookiefile"] = str(args.cookies)
    if args.cookies_from_browser:
        options["cookiesfrombrowser"] = (args.cookies_from_browser,)
    if args.playlist_items:
        options["playlist_items"] = args.playlist_items
    if args.download_archive:
        options["download_archive"] = str(args.download_archive)
    if args.write_info_json:
        options["writeinfojson"] = True
    if args.write_thumbnail:
        options["writethumbnail"] = True
    if args.rate_limit:
        options["ratelimit"] = parse_rate_limit(args.rate_limit)
    if getattr(args, "no_check_certificate", False):
        options["nocheckcertificate"] = True
    apply_youtube_helpers(options, args)

    return options


def video_options(args: argparse.Namespace) -> dict[str, Any]:
    options = common_options(args)
    video_quality = normalize_video_quality(args.video_quality)
    if video_quality == "best":
        options["format"] = "bestvideo*+bestaudio/best"
    else:
        options["format"] = (
            f"bestvideo[height<={video_quality}]+bestaudio/"
            f"best[height<={video_quality}]"
        )

    if args.video_container != "auto":
        options["merge_output_format"] = args.video_container

    return options


def audio_options(args: argparse.Namespace) -> dict[str, Any]:
    options = common_options(args, audio=True)
    options["format"] = "bestaudio/best"
    postprocessors: list[dict[str, Any]] = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": normalize_audio_format(args.audio_format),
            "preferredquality": args.audio_quality,
        }
    ]
    if not args.no_embed_metadata:
        postprocessors.append(
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
                "add_chapters": False,
                "add_infojson": False,
            }
        )
    if not args.no_embed_thumbnail:
        options["writethumbnail"] = True
        postprocessors.append(
            {
                "key": "EmbedThumbnail",
                "already_have_thumbnail": bool(args.write_thumbnail),
            }
        )
    options["postprocessors"] = postprocessors
    return options


def metadata_options(args: argparse.Namespace) -> dict[str, Any]:
    options = common_options(args)
    options.update(
        {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist" if args.allow_playlist else False,
            "ignoreerrors": True,
        }
    )
    return options


def format_duration(seconds: int | float | None) -> str:
    if not seconds:
        return "unknown"

    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def print_media_preview(info: dict[str, Any]) -> None:
    title = info.get("title") or "Unknown title"
    extractor = info.get("extractor_key") or info.get("extractor") or "Unknown site"
    uploader = info.get("uploader") or info.get("channel") or info.get("creator") or "unknown"
    duration = format_duration(info.get("duration"))
    playlist_count = info.get("playlist_count")
    accessible_count = count_accessible_entries(info)

    print("\nFound media:")
    print(f"  Title:    {title}")
    print(f"  Site:     {extractor}")
    print(f"  Uploader: {uploader}")
    print(f"  Duration: {duration}")
    if playlist_count and accessible_count is not None:
        print(f"  Items:    {accessible_count} unique/downloadable now / {playlist_count} reported by site")
        if accessible_count < playlist_count:
            missing = playlist_count - accessible_count
            print(f"  Missing:  {missing} entries were hidden, unavailable, or duplicates in this session.")
            print("            Try --cookies-from-browser chrome or --cookies if you can play them in your browser.")
    elif playlist_count:
        print(f"  Items:    {playlist_count}")
    elif accessible_count:
        print(f"  Items:    {accessible_count}")


def count_accessible_entries(info: dict[str, Any]) -> int | None:
    """Count playlist entries yt-dlp can see before download."""

    entries = info.get("entries")
    if not isinstance(entries, list):
        return None
    return sum(1 for entry in entries if entry)


def readable_size(bytes_value: int | float | None) -> str:
    """Return a compact file-size estimate."""

    if not bytes_value:
        return "unknown size"
    size = float(bytes_value)
    units = ["B", "KiB", "MiB", "GiB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return "unknown size"


def collect_video_heights(info: dict[str, Any] | None) -> list[tuple[int, str, int]]:
    """Collect available video heights from yt-dlp metadata."""

    if not info:
        return []

    candidates: list[dict[str, Any]] = []
    if isinstance(info.get("formats"), list):
        candidates.extend(format_item for format_item in info["formats"] if isinstance(format_item, dict))
    for entry in info.get("entries") or []:
        if isinstance(entry, dict) and isinstance(entry.get("formats"), list):
            candidates.extend(format_item for format_item in entry["formats"] if isinstance(format_item, dict))

    grouped: dict[int, dict[str, Any]] = {}
    for item in candidates:
        if item.get("vcodec") in {None, "none"}:
            continue
        height = item.get("height")
        if not isinstance(height, int) or height <= 0:
            continue
        size = item.get("filesize") or item.get("filesize_approx") or 0
        current = grouped.get(height)
        if current is None or size > (current.get("filesize") or current.get("filesize_approx") or 0):
            grouped[height] = item

    rows: list[tuple[int, str, int]] = []
    for height, item in grouped.items():
        ext = item.get("ext") or "unknown"
        size = int(item.get("filesize") or item.get("filesize_approx") or 0)
        rows.append((height, ext, size))
    return sorted(rows, key=lambda row: row[0], reverse=True)


def print_video_quality_choices(info: dict[str, Any] | None) -> None:
    """Print real available qualities when metadata provides them."""

    heights = collect_video_heights(info)
    print("\nVideo quality choices:")
    print("  best  - largest/best available file")
    if heights:
        for height, ext, size in heights:
            print(f"  {height}p - available as {ext}, estimated {readable_size(size)}")
    else:
        for preset in VIDEO_QUALITY_PRESETS[1:]:
            print(f"  {preset}p")


def prompt_for_video_quality(info: dict[str, Any] | None, args: argparse.Namespace) -> str:
    """Prompt for video quality unless it was provided by CLI."""

    if args.video_quality != "ask":
        return normalize_video_quality(args.video_quality)
    if args.yes:
        return DEFAULT_VIDEO_QUALITY

    print_video_quality_choices(info)
    while True:
        value = input(f"Choose video quality [default {DEFAULT_VIDEO_QUALITY}p]: ").strip()
        try:
            return normalize_video_quality(value)
        except SystemExit as exc:
            print(exc)


def prompt_for_audio_format(args: argparse.Namespace) -> str:
    """Prompt for desired audio extension unless it was provided by CLI."""

    if args.audio_format != "ask":
        return normalize_audio_format(args.audio_format)
    if args.yes:
        return "mp3"

    choices = ", ".join(["mp3", "m4a", "opus", "aac", "flac", "wav", "vorbis", "best"])
    print("\nAudio format choices:")
    print(f"  {choices}")
    print("  best keeps yt-dlp's best native audio, which may be opus/webm.")
    while True:
        value = input("Choose audio format [default mp3]: ").strip()
        try:
            return normalize_audio_format(value)
        except SystemExit as exc:
            print(exc)


def preview_media(url: str, args: argparse.Namespace) -> dict[str, Any] | None:
    yt_dlp = require_ytdlp()
    options = metadata_options(args)
    logger = options.get("logger")
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if isinstance(info, dict):
                print_media_preview(ydl.sanitize_info(info))
                return info
            problem = getattr(logger, "last_problem", "") or "No media metadata was returned."
            exc = RuntimeError(problem)
            if retry_without_browser_cookies(exc, args):
                return preview_media(url, args)
            print(
                f"Could not preview media before download: {exc}{download_failure_guidance(exc, args)}",
                file=sys.stderr,
            )
    except Exception as exc:
        if retry_without_browser_cookies(exc, args):
            return preview_media(url, args)
        print(
            f"Could not preview media before download: {exc}{download_failure_guidance(exc, args)}",
            file=sys.stderr,
        )
    return None


def confirm_download(mode: str, args: argparse.Namespace) -> None:
    if args.yes:
        return

    scope = "full playlist" if args.allow_playlist else "one item"
    if args.playlist_items:
        scope = f"{scope} items {args.playlist_items}"
    detail = f"{args.video_quality}p" if mode == "video" and args.video_quality != "best" else args.video_quality
    if mode == "audio":
        detail = args.audio_format
    answer = input(f"\nDownload {scope} as {detail} {mode}? [Y/n]: ").strip().lower()
    if answer in {"n", "no"}:
        raise SystemExit("Cancelled.")


def download_failure_guidance(exc: Exception, args: argparse.Namespace) -> str:
    text = str(exc).lower()
    guidance: list[str] = []

    if is_browser_cookie_error_text(text):
        guidance.extend(
            [
                "",
                "Browser cookies could not be loaded.",
                "- Close Brave/Chrome completely, then retry with --cookies-from-browser brave.",
                "- For public media, retry without --cookies-from-browser brave.",
                "- For login-only media, export a Netscape cookies.txt file and pass it with --cookies.",
            ]
        )

    if is_youtube_url(getattr(args, "url", "") or "") and ("http error 403" in text or "forbidden" in text):
        guidance.extend(
            [
                "",
                "YouTube blocked the media stream request.",
                f"- Make sure yt-dlp is at least {MIN_YTDLP_VERSION_TEXT}: python -m pip install --upgrade yt-dlp",
                "- If you can play the video in Brave, retry with: --cookies-from-browser brave",
                f"- The app now avoids the old android_vr client by default: --youtube-player-client {DEFAULT_YOUTUBE_PLAYER_CLIENTS}",
            ]
        )

    if "certificate_verify_failed" in text or "certificate verify failed" in text:
        guidance.extend(
            [
                "",
                "Your Python HTTPS certificate store rejected the site certificate.",
                "- First try updating yt-dlp and Python certificates.",
                "- As a last resort for this machine, retry with: --no-check-certificate",
            ]
        )

    return "\n".join(guidance)


def download_media(url: str, mode: str, args: argparse.Namespace) -> None:
    if mode == "audio":
        build_options = audio_options
    elif mode == "video":
        build_options = video_options
    else:
        raise SystemExit("Mode must be audio or video.")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    scope = "full playlist" if args.allow_playlist else "one item"
    if args.playlist_items:
        scope = f"{scope} items {args.playlist_items}"
    if mode == "video":
        detail = "best available" if args.video_quality == "best" else f"up to {args.video_quality}p"
    else:
        detail = f"{args.audio_format} audio"
    print(f"\nDownloading {scope} as {detail}...")
    print(f"Output folder: {args.output_dir.resolve()}")
    if args.allow_playlist and not args.stop_on_error:
        print("Playlist safety: unavailable, deleted, or private items will be skipped.")

    while True:
        yt_dlp = require_ytdlp()
        options = build_options(args)

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
        except Exception as exc:
            if retry_without_browser_cookies(exc, args):
                continue
            raise SystemExit(f"Download failed: {exc}{download_failure_guidance(exc, args)}") from exc
        break

    print("\nDownload complete.")


def validate_args(args: argparse.Namespace) -> None:
    if args.mode and args.mode not in SUPPORTED_MODES:
        raise SystemExit("--mode must be either audio or video.")

    if args.audio_format != "ask" and args.audio_format not in SUPPORTED_AUDIO_FORMATS:
        choices = ", ".join(sorted(SUPPORTED_AUDIO_FORMATS))
        raise SystemExit(f"--audio-format must be one of: {choices}")

    if args.video_quality != "ask":
        normalize_video_quality(args.video_quality)

    if args.video_container not in SUPPORTED_VIDEO_CONTAINERS:
        choices = ", ".join(sorted(SUPPORTED_VIDEO_CONTAINERS))
        raise SystemExit(f"--video-container must be one of: {choices}")

    if args.retries < 0:
        raise SystemExit("--retries cannot be negative.")

    if args.playlist_mode not in SUPPORTED_PLAYLIST_MODES:
        choices = ", ".join(sorted(SUPPORTED_PLAYLIST_MODES))
        raise SystemExit(f"--playlist-mode must be one of: {choices}")

    if args.cookies and not args.cookies.exists():
        raise SystemExit(f"Cookies file does not exist: {args.cookies}")

    if args.cookies and args.cookies_from_browser:
        raise SystemExit("Use either --cookies or --cookies-from-browser, not both.")

    if args.cookies_from_browser:
        args.cookies_from_browser = args.cookies_from_browser.strip().lower()
        if args.cookies_from_browser not in SUPPORTED_COOKIE_BROWSERS:
            choices = ", ".join(sorted(SUPPORTED_COOKIE_BROWSERS))
            raise SystemExit(f"--cookies-from-browser must be one of: {choices}")

    args.youtube_js_runtime = args.youtube_js_runtime.strip().lower()
    if args.youtube_js_runtime not in SUPPORTED_YOUTUBE_JS_RUNTIMES:
        choices = ", ".join(sorted(SUPPORTED_YOUTUBE_JS_RUNTIMES))
        raise SystemExit(f"--youtube-js-runtime must be one of: {choices}")

    args.youtube_player_client = args.youtube_player_client.strip()
    if not args.youtube_player_client:
        raise SystemExit("--youtube-player-client cannot be empty.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download user-provided social media links as best-quality video or audio. "
            "Use only for media you own, have permission to download, or may lawfully save."
        )
    )
    parser.add_argument("url", nargs="?", help="Media URL to download.")
    parser.add_argument(
        "--mode",
        choices=sorted(SUPPORTED_MODES),
        help="Download as audio or video. If omitted, the app asks.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder for downloads. Default: downloads",
    )
    parser.add_argument(
        "--audio-format",
        default="ask",
        help="Audio format: ask, mp3, m4a, opus, aac, flac, vorbis, wav, or best. Default: ask; interactive default is mp3.",
    )
    parser.add_argument(
        "--audio-quality",
        default="0",
        help='Audio quality for conversion. "0" is best for lossy formats. Default: 0',
    )
    parser.add_argument(
        "--no-embed-metadata",
        action="store_true",
        help="Do not embed title, artist, album, date, and other available tags into audio files.",
    )
    parser.add_argument(
        "--no-embed-thumbnail",
        action="store_true",
        help="Do not embed the thumbnail/cover art into audio files.",
    )
    parser.add_argument(
        "--video-container",
        default="auto",
        help="Merged video container: auto, mp4, mkv, or webm. Default: auto",
    )
    parser.add_argument(
        "--video-quality",
        default="ask",
        help="Video quality cap: ask, best, 2160, 1440, 1080, 720, 480, 360, or 240. Default: ask; interactive default is 1080.",
    )
    parser.add_argument(
        "--cookies",
        type=Path,
        help="Optional Netscape cookies.txt file for private/login-gated media.",
    )
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="Load login cookies from an installed browser, such as chrome, edge, firefox, or brave.",
    )
    parser.add_argument(
        "--no-youtube-cookie-prompt",
        action="store_true",
        help="Do not ask whether to use browser cookies on YouTube links.",
    )
    parser.add_argument(
        "--youtube-js-runtime",
        default="auto",
        help="JavaScript runtime for YouTube challenge solving: auto, node, deno, bun, quickjs, or none. Default: auto.",
    )
    parser.add_argument(
        "--youtube-player-client",
        default=DEFAULT_YOUTUBE_PLAYER_CLIENTS,
        help=(
            "Comma-separated YouTube clients for yt-dlp. Default: "
            f"{DEFAULT_YOUTUBE_PLAYER_CLIENTS}"
        ),
    )
    parser.add_argument(
        "--no-youtube-remote-components",
        action="store_true",
        help="Do not allow yt-dlp to fetch official YouTube challenge helper components.",
    )
    parser.add_argument(
        "--allow-playlist",
        action="store_true",
        help="Allow playlist/profile/channel URLs to download multiple items. Same as --playlist-mode playlist.",
    )
    parser.add_argument(
        "--playlist-mode",
        choices=sorted(SUPPORTED_PLAYLIST_MODES),
        default="ask",
        help="Playlist handling: ask, single, or playlist. Default: ask.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="In playlist mode, stop when one item is unavailable or fails. Default: skip failed playlist items.",
    )
    parser.add_argument(
        "--playlist-items",
        metavar="ITEM_SPEC",
        help='Playlist item range/list to request, such as "1-299", "157-299", "1,5,9", or "1:299".',
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Do not create per-site subfolders.",
    )
    parser.add_argument(
        "--write-info-json",
        action="store_true",
        help="Save yt-dlp metadata JSON next to the download.",
    )
    parser.add_argument(
        "--write-thumbnail",
        action="store_true",
        help="Save media thumbnail as a separate file. Audio cover art is embedded by default.",
    )
    parser.add_argument(
        "--download-archive",
        type=Path,
        help="Optional archive file to avoid re-downloading the same media.",
    )
    parser.add_argument(
        "--rate-limit",
        help='Optional download rate limit accepted by yt-dlp, such as "2M" or "500K".',
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=10,
        help="Retry count for downloads/fragments. Default: 10",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip final confirmation.",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip metadata preview before download.",
    )
    parser.add_argument(
        "--no-check-certificate",
        action="store_true",
        help="Disable HTTPS certificate checks for yt-dlp. Use only if certificate verification fails.",
    )
    return parser


def main() -> int:
    enable_line_buffered_output()

    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    print(
        "Use this tool only for media you own, have permission to download, "
        "or may lawfully save. It does not bypass DRM."
    )

    url = validate_url(args.url) if args.url else prompt_for_url()
    args.url = url
    playlist_mode = prompt_for_playlist_mode(url, args)
    args.allow_playlist = playlist_mode == "playlist"
    if playlist_mode == "playlist":
        print("Playlist mode: full playlist will be downloaded.")
    else:
        print("Playlist mode: one song/video only.")
    prompt_for_youtube_cookies(url, args)

    media_info = None
    if not args.no_preview:
        media_info = preview_media(url, args)

    mode = args.mode or prompt_for_mode()
    if mode == "video":
        args.video_quality = prompt_for_video_quality(media_info, args)
    if mode == "audio":
        args.audio_format = prompt_for_audio_format(args)

    confirm_download(mode, args)
    download_media(url, mode, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

