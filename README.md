# Social Media Downloader App

Python CLI for downloading a user-provided media link as either best-quality video or best-quality audio.

It uses `yt-dlp`, which supports thousands of media sites and is commonly used for YouTube, TikTok, Instagram, Facebook, Twitter/X, and many others. Site support can change whenever platforms change their pages or access rules, so keep `yt-dlp` updated.

Use this only for media you own, have permission to download, or may lawfully save. This app does not bypass DRM.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Interactive Use

Run the app, paste the link, then choose `audio` or `video`:

```powershell
python .\social_media_downloader.py
```

## Download Video

```powershell
python .\social_media_downloader.py "https://example.com/media-link" --mode video
```

The video mode asks yt-dlp for the best available video plus best available audio, then merges them when needed.

Force a common container:

```powershell
python .\social_media_downloader.py "https://example.com/media-link" --mode video --video-container mp4
```

## Download Audio

Best native audio:

```powershell
python .\social_media_downloader.py "https://example.com/media-link" --mode audio
```

Convert to MP3:

```powershell
python .\social_media_downloader.py "https://example.com/media-link" --mode audio --audio-format mp3
```

## Output Folder

```powershell
python .\social_media_downloader.py "https://example.com/media-link" --mode video --output-dir .\downloads
```

By default, downloads are saved in per-site folders under `downloads`.

## Login-Gated Media

Some TikTok, Instagram, Facebook, Twitter/X, or age/private YouTube links may require cookies from a browser session. Export a Netscape-format `cookies.txt` file and pass it like this:

```powershell
python .\social_media_downloader.py "https://example.com/private-link" --mode video --cookies .\cookies.txt
```

Do not commit cookies or secrets. The `.gitignore` excludes common cookie filenames.

## Useful Options

```powershell
python .\social_media_downloader.py "URL" --mode video --write-info-json --write-thumbnail
python .\social_media_downloader.py "URL" --mode audio --download-archive .\downloaded.txt
python .\social_media_downloader.py "URL" --mode video --allow-playlist
```

Playlists are disabled by default so a pasted profile/channel/playlist URL does not unexpectedly download many files.

## Notes

- Install updates with `python -m pip install --upgrade yt-dlp`.
- Some platforms block downloads, change frequently, or require login cookies.
- Downloading copyrighted or private media without permission may violate law or platform terms.
- `imageio-ffmpeg` is included so merging video/audio and audio extraction can work without a separate FFmpeg install in many environments.

Official docs used:

- [yt-dlp GitHub repository](https://github.com/yt-dlp/yt-dlp)
- [Embedding yt-dlp in Python](https://yt-dlp-yt-dlp.mintlify.app/advanced/embedding)
