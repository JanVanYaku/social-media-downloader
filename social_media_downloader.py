#######################################################################
# Author: Lehlohonolo Adolf Matobakele  
# Email: lehlohonolo.matobakele@gov.ls
# Contacxt: 00266 62320704
#######################################################################
from __future__ import annotations

import argparse
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
YOUTUBE_REMOTE_COMPONENTS = ("ejs:github", "ejs:npm")


class SimpleLogger:
    def __init__(self) -> None:
        self._youtube_help_printed = False

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug] "):
            return
        self.info(msg)

    def info(self, msg: str) -> None:
        if msg:
            print(msg)

    def warning(self, msg: str) -> None:
        if msg:
            print(f"Warning: {msg}", file=sys.stderr)
            self._print_youtube_help_once(msg)

    def error(self, msg: str) -> None:
        if msg:
            print(f"Error: {msg}", file=sys.stderr)
            self._print_youtube_help_once(msg)

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
        )


def require_ytdlp() -> Any:
    try:
        import yt_dlp
    except ImportError as exc:
        raise SystemExit(
            "yt-dlp is not installed. Install requirements first:\n"
            "  python -m pip install -r requirements.txt"
        ) from exc

    return yt_dlp


def get_ffmpeg_location() -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None

    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def validate_url(url: str) -> str:
    cleaned = url.strip()
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


def apply_youtube_helpers(options: dict[str, Any], args: argparse.Namespace) -> None:
    """Enable YouTube options that reduce 403 and n-challenge failures."""

    if not is_youtube_url(getattr(args, "url", "") or ""):
        return
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
    try:
        with yt_dlp.YoutubeDL(metadata_options(args)) as ydl:
            info = ydl.extract_info(url, download=False)
            if isinstance(info, dict):
                print_media_preview(ydl.sanitize_info(info))
                return info
    except Exception as exc:
        print(f"Could not preview media before download: {exc}", file=sys.stderr)
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


def download_media(url: str, mode: str, args: argparse.Namespace) -> None:
    yt_dlp = require_ytdlp()

    if mode == "audio":
        options = audio_options(args)
    elif mode == "video":
        options = video_options(args)
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

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except Exception as exc:
        raise SystemExit(f"Download failed: {exc}") from exc

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

