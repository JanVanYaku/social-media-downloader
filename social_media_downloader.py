from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_OUTPUT_DIR = Path("downloads")
SUPPORTED_MODES = {"audio", "video"}
SUPPORTED_AUDIO_FORMATS = {"best", "aac", "flac", "m4a", "mp3", "opus", "vorbis", "wav"}
SUPPORTED_VIDEO_CONTAINERS = {"auto", "mkv", "mp4", "webm"}


class SimpleLogger:
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

    def error(self, msg: str) -> None:
        if msg:
            print(f"Error: {msg}", file=sys.stderr)


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


def sanitize_filename_fragment(value: str | None, fallback: str) -> str:
    text = value or fallback
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:180] or fallback


def build_output_template(output_dir: Path, flat: bool) -> str:
    if flat:
        return str(output_dir / "%(title).180B [%(id)s].%(ext)s")
    return str(output_dir / "%(extractor_key)s" / "%(title).180B [%(id)s].%(ext)s")


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


def common_options(args: argparse.Namespace) -> dict[str, Any]:
    options: dict[str, Any] = {
        "logger": SimpleLogger(),
        "noplaylist": not args.allow_playlist,
        "outtmpl": build_output_template(args.output_dir, args.flat),
        "retries": args.retries,
        "fragment_retries": args.retries,
        "windowsfilenames": True,
        "trim_file_name": 180,
        "continuedl": True,
        "ignoreerrors": False,
        "quiet": False,
        "no_warnings": False,
    }

    ffmpeg_location = get_ffmpeg_location()
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location

    if args.cookies:
        options["cookiefile"] = str(args.cookies)
    if args.download_archive:
        options["download_archive"] = str(args.download_archive)
    if args.write_info_json:
        options["writeinfojson"] = True
    if args.write_thumbnail:
        options["writethumbnail"] = True
    if args.rate_limit:
        options["ratelimit"] = parse_rate_limit(args.rate_limit)

    return options


def video_options(args: argparse.Namespace) -> dict[str, Any]:
    options = common_options(args)
    options["format"] = "bestvideo*+bestaudio/best"

    if args.video_container != "auto":
        options["merge_output_format"] = args.video_container

    return options


def audio_options(args: argparse.Namespace) -> dict[str, Any]:
    options = common_options(args)
    options["format"] = "bestaudio/best"
    options["postprocessors"] = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": args.audio_format,
            "preferredquality": args.audio_quality,
        }
    ]
    return options


def metadata_options(args: argparse.Namespace) -> dict[str, Any]:
    options = common_options(args)
    options.update(
        {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
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

    print("\nFound media:")
    print(f"  Title:    {title}")
    print(f"  Site:     {extractor}")
    print(f"  Uploader: {uploader}")
    print(f"  Duration: {duration}")


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

    answer = input(f"\nDownload best available {mode}? [Y/n]: ").strip().lower()
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

    print(f"\nDownloading best available {mode}...")
    print(f"Output folder: {args.output_dir.resolve()}")

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    print("\nDownload complete.")


def validate_args(args: argparse.Namespace) -> None:
    if args.mode and args.mode not in SUPPORTED_MODES:
        raise SystemExit("--mode must be either audio or video.")

    if args.audio_format not in SUPPORTED_AUDIO_FORMATS:
        choices = ", ".join(sorted(SUPPORTED_AUDIO_FORMATS))
        raise SystemExit(f"--audio-format must be one of: {choices}")

    if args.video_container not in SUPPORTED_VIDEO_CONTAINERS:
        choices = ", ".join(sorted(SUPPORTED_VIDEO_CONTAINERS))
        raise SystemExit(f"--video-container must be one of: {choices}")

    if args.retries < 0:
        raise SystemExit("--retries cannot be negative.")

    if args.cookies and not args.cookies.exists():
        raise SystemExit(f"Cookies file does not exist: {args.cookies}")


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
        default="best",
        help="Audio format: best, mp3, m4a, opus, aac, flac, vorbis, or wav. Default: best",
    )
    parser.add_argument(
        "--audio-quality",
        default="0",
        help='Audio quality for conversion. "0" is best for lossy formats. Default: 0',
    )
    parser.add_argument(
        "--video-container",
        default="auto",
        help="Merged video container: auto, mp4, mkv, or webm. Default: auto",
    )
    parser.add_argument(
        "--cookies",
        type=Path,
        help="Optional Netscape cookies.txt file for private/login-gated media.",
    )
    parser.add_argument(
        "--allow-playlist",
        action="store_true",
        help="Allow playlist/profile/channel URLs to download multiple items.",
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
        help="Save media thumbnail when available.",
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
    if not args.no_preview:
        preview_media(url, args)

    mode = args.mode or prompt_for_mode()
    confirm_download(mode, args)
    download_media(url, mode, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
