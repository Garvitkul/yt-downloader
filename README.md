# YT Downloader

A local web app to download YouTube videos, audio, or clips.

## Features

- Download full videos in any available quality (1080p, 720p, 480p, etc.)
- Download audio only (MP3)
- Trim clips by specifying start and end times — only downloads the requested portion
- Real-time progress bar with speed and ETA
- Auto-detects browser cookies for authenticated downloads

## Setup

```bash
./setup.sh
```

This checks and installs all dependencies (Python, ffmpeg, pip packages, venv).

## Usage

```bash
./run.sh
```

Open **http://127.0.0.1:5000** in your browser.

1. Paste a YouTube URL and click **Fetch**
2. Choose format (video/audio) and quality
3. Optionally set a time range to trim a clip
4. Click **Download**

## Requirements

- Python 3.9+

## Notes

- Works out of the box for most public YouTube videos.
- If you get a "sign in" or "age-restricted" error, make sure you're logged into YouTube in your browser. The app automatically reads cookies from the first available browser (Brave → Chrome → Firefox → Safari → Edge) to authenticate with YouTube.
- If auto-detection doesn't work, you can manually export cookies:
  1. Install a browser extension: [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (Chrome/Brave/Edge) or [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) (Firefox)
  2. Go to youtube.com while logged in
  3. Export cookies using the extension
  4. Save the file as `cookies.txt` in the project root (`yt-downloader/cookies.txt`)

## Project Structure

```
yt-downloader/
├── app.py              # Backend server
├── static/index.html   # Frontend UI
├── requirements.txt    # Python dependencies
├── setup.sh            # One-time setup
├── run.sh              # Start server
└── venv/               # Virtual environment
```

<img width="1726" height="823" alt="image" src="https://github.com/user-attachments/assets/91ebb1f7-3514-42f2-a1c1-3c5d793500d2" />
