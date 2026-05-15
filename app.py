import os
import uuid
import shutil
import time
import threading
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
from yt_dlp.utils import download_range_func

app = Flask(__name__, static_folder='static')
CORS(app)

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

MAX_DISK_USAGE_MB = 2000
STALE_FILE_AGE_SECONDS = 600
MAX_CONCURRENT_JOBS = 3

COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')

jobs = {}
jobs_lock = threading.Lock()


def get_cookie_opts():
    opts = {}
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    else:
        browser = detect_browser()
        if browser:
            opts['cookiesfrombrowser'] = (browser,)
    return opts


def detect_browser():
    candidates = [
        ('brave', os.path.expanduser('~/Library/Application Support/BraveSoftware/Brave-Browser')),
        ('chrome', os.path.expanduser('~/Library/Application Support/Google/Chrome')),
        ('firefox', os.path.expanduser('~/Library/Application Support/Firefox')),
        ('safari', os.path.expanduser('~/Library/Safari')),
        ('edge', os.path.expanduser('~/Library/Application Support/Microsoft Edge')),
        ('chromium', os.path.expanduser('~/Library/Application Support/Chromium')),
    ]
    for name, path in candidates:
        if os.path.exists(path):
            return name
    return None


def get_dir_size_mb(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total / (1024 * 1024)


def cleanup_stale_jobs():
    now = time.time()
    try:
        for entry in os.listdir(DOWNLOAD_DIR):
            job_path = os.path.join(DOWNLOAD_DIR, entry)
            if os.path.isdir(job_path):
                age = now - os.path.getmtime(job_path)
                if age > STALE_FILE_AGE_SECONDS:
                    shutil.rmtree(job_path, ignore_errors=True)
    except OSError:
        pass

    with jobs_lock:
        stale_ids = [jid for jid, j in jobs.items()
                     if now - j.get('updated_at', 0) > STALE_FILE_AGE_SECONDS]
        for jid in stale_ids:
            jobs.pop(jid, None)


def schedule_cleanup(job_id, job_dir, delay=120):
    def _cleanup():
        time.sleep(delay)
        shutil.rmtree(job_dir, ignore_errors=True)
        with jobs_lock:
            jobs.pop(job_id, None)
    t = threading.Thread(target=_cleanup, daemon=True)
    t.start()


def active_job_count():
    with jobs_lock:
        return sum(1 for j in jobs.values() if j.get('status') == 'downloading')


def validate_youtube_url(url):
    import re
    patterns = [
        r'(https?://)?(www\.)?youtube\.com/watch\?v=[\w-]+',
        r'(https?://)?(www\.)?youtube\.com/shorts/[\w-]+',
        r'(https?://)?youtu\.be/[\w-]+',
        r'(https?://)?(www\.)?youtube\.com/embed/[\w-]+',
        r'(https?://)?(m\.)?youtube\.com/watch\?v=[\w-]+',
    ]
    return any(re.match(p, url) for p in patterns)


def classify_error(error_msg):
    msg = error_msg.lower()
    if 'sign in' in msg or 'login' in msg:
        return 'This video requires authentication. Make sure you are logged into YouTube in your browser and restart the server.'
    if 'private' in msg:
        return 'This video is private. You can only download public or unlisted videos.'
    if 'unavailable' in msg or ('not available' in msg and 'format' not in msg):
        return 'This video is unavailable. It may have been removed or is region-restricted.'
    if 'age' in msg and ('gate' in msg or 'restrict' in msg):
        return 'This video is age-restricted. Make sure you are logged into YouTube (18+) in your browser and restart the server.'
    if 'copyright' in msg:
        return 'This video was removed due to a copyright claim and cannot be downloaded.'
    if 'live' in msg and 'not' not in msg:
        return 'Live streams cannot be downloaded while they are in progress. Wait until the stream ends.'
    if '429' in msg or 'too many' in msg:
        return 'YouTube is rate-limiting requests. Wait a few minutes before trying again.'
    if '403' in msg or 'forbidden' in msg:
        return 'YouTube blocked the request. Try again in a few minutes, or restart your browser to refresh cookies.'
    if 'format' in msg and 'not available' in msg:
        return 'The selected quality is not available for this video. Try a different quality or "Best Available".'
    if 'network' in msg or 'connection' in msg or 'timed out' in msg or 'timeout' in msg:
        return 'Network error — could not reach YouTube. Check your internet connection and try again.'
    if 'no video' in msg or 'no suitable' in msg:
        return 'No downloadable format found for this video. Try selecting a different quality.'
    if 'ffmpeg' in msg:
        return 'Video processing failed (ffmpeg error). Try a different quality or format.'
    return f'Download failed: {error_msg}. Please try again.'


def run_download(job_id, url, format_type, quality, start_time, end_time):
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    def progress_hook(d):
        with jobs_lock:
            job = jobs.get(job_id)
            if not job:
                return
            job['updated_at'] = time.time()
            if d['status'] == 'downloading':
                job['status'] = 'downloading'
                job['downloaded_bytes'] = d.get('downloaded_bytes', 0)
                job['total_bytes'] = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                job['speed'] = d.get('speed', 0)
                job['eta'] = d.get('eta')
                if job['total_bytes'] > 0:
                    job['progress'] = round(job['downloaded_bytes'] / job['total_bytes'] * 100, 1)
            elif d['status'] == 'finished':
                job['status'] = 'processing'
                job['progress'] = 100

    try:
        if get_dir_size_mb(DOWNLOAD_DIR) > MAX_DISK_USAGE_MB:
            cleanup_stale_jobs()
            if get_dir_size_mb(DOWNLOAD_DIR) > MAX_DISK_USAGE_MB:
                with jobs_lock:
                    jobs[job_id]['status'] = 'error'
                    jobs[job_id]['error'] = 'Server storage is full. Previous downloads are being cleaned up — please try again in 2 minutes.'
                return

        ydl_opts = {
            'outtmpl': os.path.join(job_dir, '%(title).150s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [progress_hook],
            'socket_timeout': 30,
            'retries': 3,
            'fragment_retries': 3,
            **get_cookie_opts(),
        }

        if format_type == 'audio':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            if quality:
                ydl_opts['format'] = (
                    f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/'
                    f'bestvideo[height<={quality}]+bestaudio/'
                    f'best[height<={quality}]/best'
                )
            else:
                ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            ydl_opts['merge_output_format'] = 'mp4'

        if start_time is not None or end_time is not None:
            s = start_time if start_time is not None else 0
            e = end_time if end_time is not None else float('inf')
            ydl_opts['download_ranges'] = download_range_func(None, [(s, e)])
            ydl_opts['force_keyframes_at_cuts'] = True

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')

        files = [f for f in os.listdir(job_dir) if not f.startswith('.')]
        if not files:
            with jobs_lock:
                jobs[job_id]['status'] = 'error'
                jobs[job_id]['error'] = 'Download completed but no file was saved. This can happen with DRM-protected or premium-only content. Try a different video.'
            return

        downloaded_file = os.path.join(job_dir, files[0])
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        if not safe_title:
            safe_title = 'download'
        ext = os.path.splitext(downloaded_file)[1]
        download_name = f"{safe_title}{ext}"

        with jobs_lock:
            jobs[job_id]['status'] = 'done'
            jobs[job_id]['file_path'] = downloaded_file
            jobs[job_id]['file_name'] = download_name
            jobs[job_id]['updated_at'] = time.time()

        schedule_cleanup(job_id, job_dir, delay=120)

    except yt_dlp.utils.DownloadError as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        error_msg = str(e)
        user_msg = classify_error(error_msg)
        with jobs_lock:
            jobs[job_id]['status'] = 'error'
            jobs[job_id]['error'] = user_msg
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        with jobs_lock:
            jobs[job_id]['status'] = 'error'
            jobs[job_id]['error'] = f'Unexpected error: {str(e)}. Please try again.'


@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/api/info', methods=['POST'])
def video_info():
    data = request.json
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL is required'}), 400

    if not validate_youtube_url(url):
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'socket_timeout': 20, **get_cookie_opts()}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])

            available_qualities = set()
            for f in formats:
                height = f.get('height')
                if height and f.get('vcodec') != 'none':
                    available_qualities.add(height)

            quality_list = sorted(available_qualities, reverse=True)

            return jsonify({
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'channel': info.get('channel', 'Unknown'),
                'qualities': quality_list,
            })
    except Exception as e:
        error_msg = str(e)
        user_msg = classify_error(error_msg) if 'DownloadError' in type(e).__name__ or 'ExtractorError' in type(e).__name__ else error_msg
        return jsonify({'error': user_msg}), 400


@app.route('/api/download/start', methods=['POST'])
def start_download():
    data = request.json
    url = data.get('url', '').strip()
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    format_type = data.get('format', 'video')
    quality = data.get('quality')
    duration = data.get('duration', 0)

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    if not validate_youtube_url(url):
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    if start_time is not None and end_time is not None:
        if start_time >= end_time:
            return jsonify({'error': 'Start time must be before end time'}), 400

    if start_time is not None and duration and start_time >= duration:
        return jsonify({'error': 'Start time exceeds video duration'}), 400

    if active_job_count() >= MAX_CONCURRENT_JOBS:
        return jsonify({'error': f'Server is busy ({MAX_CONCURRENT_JOBS} downloads running). Please wait for a current download to finish and try again.'}), 429

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            'status': 'starting',
            'progress': 0,
            'downloaded_bytes': 0,
            'total_bytes': 0,
            'speed': 0,
            'eta': None,
            'error': None,
            'file_path': None,
            'file_name': None,
            'created_at': time.time(),
            'updated_at': time.time(),
        }

    t = threading.Thread(
        target=run_download,
        args=(job_id, url, format_type, quality, start_time, end_time),
        daemon=True
    )
    t.start()

    return jsonify({'job_id': job_id})


@app.route('/api/download/progress/<job_id>', methods=['GET'])
def download_progress(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    now = time.time()
    stall_seconds = now - job.get('updated_at', now)

    return jsonify({
        'status': job['status'],
        'progress': job.get('progress', 0),
        'downloaded_bytes': job.get('downloaded_bytes', 0),
        'total_bytes': job.get('total_bytes', 0),
        'speed': job.get('speed', 0),
        'eta': job.get('eta'),
        'error': job.get('error'),
        'stalled': stall_seconds > 30,
        'stall_seconds': round(stall_seconds, 1),
    })


@app.route('/api/download/file/<job_id>', methods=['GET'])
def download_file(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if job['status'] != 'done':
        return jsonify({'error': 'File not ready'}), 400

    file_path = job['file_path']
    file_name = job['file_name']

    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'File no longer available'}), 410

    return send_file(
        file_path,
        as_attachment=True,
        download_name=file_name
    )


@app.route('/api/download/cancel/<job_id>', methods=['POST'])
def cancel_download(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job['status'] = 'cancelled'

    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    shutil.rmtree(job_dir, ignore_errors=True)

    with jobs_lock:
        jobs.pop(job_id, None)

    return jsonify({'ok': True})


if __name__ == '__main__':
    cleanup_stale_jobs()
    app.run(debug=False, port=5000, threaded=True)
