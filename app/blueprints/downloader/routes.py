# downloader/routes.py

import os
import sys
import shutil
import threading
import subprocess
import json
import re

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, send_file, current_app, jsonify,
    send_from_directory, abort
)
from flask_login import login_required, current_user

from app.forms import YouTubeDownloaderForm

downloader = Blueprint('downloader', __name__, template_folder='templates')

# In-memory storage for download progress
download_tasks = {}

# --- Regex for parsing yt-dlp output ---
PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<percent>[\d\.]+)%(?:\s+of\s+~?\s*(?P<size>[\d\.]+\w+))?(?:\s+at\s+(?P<speed>[\d\.]+\w+/s))?"
)

# Standard extractor arguments for bypassing bot verification on YouTube
EXTRACTOR_ARGS = [
    '--extractor-args', 'youtube:player_client=ios,android,web',
    '--no-check-certificates',
    '--no-playlist'
]


def get_ytdlp_cmd():
    """Always invoke yt-dlp using the active Python interpreter module."""
    return [sys.executable, '-m', 'yt_dlp']


def get_ffmpeg_args():
    """Detect FFmpeg dynamically, with static-ffmpeg fallback for cloud environments like Render."""
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass

    ffmpeg_bin = shutil.which('ffmpeg')
    if ffmpeg_bin:
        return ['--ffmpeg-location', os.path.dirname(ffmpeg_bin)]
    return []


def get_cookie_args():
    """Only pass cookie file if it actually exists and has content."""
    cookies_path = os.path.join(current_app.instance_path, 'cookies.txt')
    if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 20:
        return ['--cookies', cookies_path]
    return []


# --- Background Download Function (using yt-dlp) ---
def download_process_thread(app, url, format_id, task_key, filepath):
    """Downloads a video stream in a separate thread using yt-dlp."""
    global download_tasks

    with app.app_context():
        ffmpeg_args = get_ffmpeg_args()
        cookie_args = get_cookie_args()

        # Format selector: if ffmpeg is available, combine video+audio.
        # Otherwise fallback to best pre-merged stream so it never crashes without ffmpeg.
        if ffmpeg_args:
            if format_id == 'best':
                format_selector = 'bestvideo+bestaudio/best[ext=mp4]/best'
            else:
                format_selector = f"{format_id}+bestaudio/best[ext=mp4]/{format_id}/best"
        else:
            format_selector = f"best[ext=mp4]/{format_id}/best"

        try:
            command = (
                get_ytdlp_cmd()
                + ['-f', format_selector, '-o', filepath, '--progress', '--newline', '-q', '--no-warnings']
                + ffmpeg_args
                + cookie_args
                + EXTRACTOR_ARGS
                + ['--merge-output-format', 'mp4', url]
            )

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if task_key in download_tasks:
                download_tasks[task_key]['process'] = process

            current_app.logger.info(f"Started yt-dlp process for {task_key}")

            for line in iter(process.stdout.readline, ''):
                if not line:
                    break

                task_info = download_tasks.get(task_key, {})
                if task_info.get('cancel_requested'):
                    process.terminate()
                    raise Exception("Download cancelled by user.")

                line_clean = line.strip()

                if "[Merger]" in line_clean or "Merging formats" in line_clean:
                    task_info['status'] = 'merging'
                    task_info['speed_str'] = 'Merging audio & video...'
                    task_info['progress'] = 98
                    continue

                match = PROGRESS_RE.search(line_clean)
                if match:
                    data = match.groupdict()
                    percentage = float(data.get('percent', 0))
                    speed = data.get('speed') or 'Downloading...'

                    if task_key in download_tasks:
                        download_tasks[task_key]['progress'] = int(percentage)
                        download_tasks[task_key]['speed_str'] = speed
                        download_tasks[task_key]['status'] = 'downloading'

            process.stdout.close()
            return_code = process.wait()
            current_app.logger.info(f"yt-dlp for {task_key} finished with exit code {return_code}")

            task_info = download_tasks.get(task_key, {})
            if task_info.get('cancel_requested'):
                raise Exception("Download cancelled by user.")

            if return_code == 0:
                # Resolve actual filepath in case yt-dlp saved under a different extension (e.g. .mkv, .webm)
                actual_filepath = filepath
                if not os.path.exists(actual_filepath):
                    base_no_ext, _ = os.path.splitext(filepath)
                    parent_dir = os.path.dirname(filepath)
                    if os.path.exists(parent_dir):
                        candidates = [
                            os.path.join(parent_dir, f) for f in os.listdir(parent_dir)
                            if os.path.join(parent_dir, f).startswith(base_no_ext) and not f.endswith('.part')
                        ]
                        if candidates:
                            actual_filepath = candidates[0]

                if os.path.exists(actual_filepath):
                    task_info['filepath'] = actual_filepath
                    task_info['download_name'] = os.path.basename(actual_filepath)
                    task_info['status'] = 'complete'
                    task_info['progress'] = 100
                    task_info['speed_str'] = "Complete"
                else:
                    raise Exception("Download finished, but output file could not be located on the server.")
            else:
                raise Exception(f"Downloader failed with exit code {return_code}")

        except Exception as e:
            current_app.logger.error(f"Download thread error for {task_key}: {e}")
            if task_key in download_tasks:
                task_info = download_tasks[task_key]
                if "cancelled by user" in str(e).lower():
                    task_info['status'] = 'cancelled'
                    task_info['speed_str'] = 'Cancelled'
                    if os.path.exists(filepath):
                        try:
                            os.remove(filepath)
                        except OSError:
                            pass
                else:
                    task_info['status'] = 'error'
                    task_info['error_message'] = str(e)
                    task_info['speed_str'] = 'Error'


@downloader.route('/download', methods=['GET', 'POST'])
@login_required
def download():
    """Handles the form submission, fetches video metadata and displays download options."""
    form = YouTubeDownloaderForm()
    video_title = None
    download_options = []

    if form.validate_on_submit():
        url = form.youtube_url.data.strip()

        try:
            cmd = (
                get_ytdlp_cmd()
                + ['--no-update', '--no-call-home', '--dump-json']
                + EXTRACTOR_ARGS
                + get_cookie_args()
                + [url]
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                check=True,
                timeout=90
            )

            data = json.loads(result.stdout)
            video_title = data.get('title', 'Downloaded Video')
            video_id = str(data.get('id', 'video'))

            # Gather formats: support both separate video streams and pre-merged progressive streams
            formats = data.get('formats', [])
            if not formats and data.get('url'):
                formats = [data]

            candidates = [
                f for f in formats
                if f.get('vcodec') != 'none' or (not f.get('vcodec') and f.get('ext') in ('mp4', 'webm', 'mkv'))
            ]
            if not candidates and formats:
                candidates = formats
            elif not candidates:
                candidates = [{'format_id': 'best', 'resolution': 'Best Available', 'ext': 'mp4'}]

            # Sort best resolution / height first
            candidates.sort(
                key=lambda x: (x.get('height') or 0, x.get('tbr') or 0, x.get('filesize') or 0),
                reverse=True
            )

            # Deduplicate by resolution to keep dropdown intuitive
            seen_resolutions = set()
            for stream in candidates:
                format_id = str(stream.get('format_id', 'best'))
                resolution = (
                    stream.get('resolution')
                    or stream.get('format_note')
                    or (f"{stream.get('height')}p" if stream.get('height') else 'Standard Quality')
                )
                ext = stream.get('ext', 'mp4')
                res_key = f"{resolution} ({ext})"

                if res_key in seen_resolutions:
                    continue
                seen_resolutions.add(res_key)

                # Clean task key
                raw_key = f"{video_id}_{format_id}_{current_user.id}"
                task_key = "".join(c for c in raw_key if c.isalnum() or c in ('_', '-'))

                initiate_url = url_for(
                    'downloader.initiate_download',
                    format_id=format_id,
                    task_key=task_key,
                    url=url,
                    title=video_title
                )

                file_size = stream.get('filesize') or stream.get('filesize_approx') or 0
                size_mb = round(file_size / (1024 * 1024), 2) if file_size else 0

                download_options.append({
                    'resolution': resolution,
                    'url': initiate_url,
                    'task_key': task_key,
                    'size_mb': size_mb
                })

            if download_options:
                flash(f'Ready! Choose your download quality for "{video_title}".', 'info')
            else:
                flash('No downloadable video streams found for this URL.', 'error')

        except subprocess.TimeoutExpired:
            flash('Request timed out while fetching video data. Please try again.', 'error')
        except subprocess.CalledProcessError as e:
            flash('Error fetching video data. Please check the URL or try a different link.', 'error')
            current_app.logger.error(f"yt-dlp JSON error: {e.stderr}")
        except Exception as e:
            flash(f'An unexpected error occurred: {e}', 'error')
            current_app.logger.error(f"Downloader processing error: {e}")

        return render_template(
            'downloader.html',
            title='Downloader',
            form=form,
            video_title=video_title,
            download_options=download_options,
            active_page='downloader'
        )

    return render_template('downloader.html', title='Downloader', form=form, active_page='downloader')


@downloader.route('/initiate/<string:format_id>/<string:task_key>')
@login_required
def initiate_download(format_id, task_key):
    """Starts the download process in a background thread."""
    global download_tasks

    if task_key in download_tasks and download_tasks[task_key]['status'] == 'downloading':
        return jsonify({'status': 'already_running', 'progress': download_tasks[task_key]['progress']})

    url = request.args.get('url')
    video_title = request.args.get('title')

    if not url:
        return jsonify({'status': 'error', 'message': 'Missing URL parameter.'}), 400

    # Create a safe filename
    if video_title:
        safe_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '.', '_', '-')).rstrip().strip()
        safe_title = safe_title[:60]
        safe_filename = f"{safe_title}.mp4"
    else:
        safe_filename = f"{task_key.split('_')[0]}.mp4"

    download_dir = os.path.join(current_app.instance_path, 'downloads', str(current_user.id))
    os.makedirs(download_dir, exist_ok=True)
    filepath = os.path.join(download_dir, safe_filename)

    app = current_app._get_current_object()

    thread = threading.Thread(
        target=download_process_thread,
        args=(app, url, format_id, task_key, filepath)
    )

    download_tasks[task_key] = {
        'progress': 0,
        'status': 'starting',
        'thread': thread,
        'process': None,
        'cancel_requested': False,
        'error_message': None,
        'speed_str': 'Starting...',
        'filepath': None,
        'download_name': safe_filename
    }
    thread.start()

    return jsonify({'status': 'started', 'task_key': task_key})


@downloader.route('/status/<string:task_key>')
@login_required
def download_status(task_key):
    """Provides the current status, progress, and speed for a download task."""
    global download_tasks
    task = download_tasks.get(task_key)

    if not task or not task_key.endswith(f"_{current_user.id}"):
        return jsonify({'status': 'not_found', 'message': 'Task not found or expired.'}), 404

    response_data = {
        'status': task.get('status', 'starting'),
        'progress': task.get('progress', 0),
        'speed_str': task.get('speed_str', '')
    }

    if task.get('status') == 'complete':
        response_data['download_url'] = url_for('downloader.get_final_file', task_key=task_key)
    elif task.get('status') == 'error':
        response_data['message'] = task.get('error_message', 'An unknown error occurred.')

    return jsonify(response_data)


@downloader.route('/get_final/<string:task_key>')
@login_required
def get_final_file(task_key):
    """Serves the completed download file."""
    global download_tasks
    task = download_tasks.get(task_key)

    if not task or not task_key.endswith(f"_{current_user.id}") or task.get('status') != 'complete' or not task.get('filepath'):
        flash('Download not found, not complete, or unauthorized.', 'error')
        return redirect(url_for('downloader.download'))

    file_path = task['filepath']
    download_name = task.get('download_name', os.path.basename(file_path))

    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True, download_name=download_name)
    else:
        flash('Error: Downloaded file is missing on the server.', 'error')
        return redirect(url_for('downloader.download'))


@downloader.route('/cancel/<string:task_key>', methods=['POST'])
@login_required
def cancel_download(task_key):
    """Attempts to cancel an ongoing download."""
    global download_tasks
    task = download_tasks.get(task_key)

    if not task or not task_key.endswith(f"_{current_user.id}"):
        return jsonify({'status': 'not_found'}), 404

    if task.get('status') in ('downloading', 'starting', 'merging'):
        task['cancel_requested'] = True
        process = task.get('process')
        if process:
            try:
                process.terminate()
            except Exception as e:
                current_app.logger.warning(f"Error terminating process for {task_key}: {e}")
        return jsonify({'status': 'cancel_requested'})

    return jsonify({'status': task.get('status', 'unknown')})


# --- Routes for "My Downloads" page ---

@downloader.route('/my-files')
@login_required
def my_files():
    """Displays a list of all files downloaded by the user."""
    files_list = []
    user_download_dir = os.path.join(current_app.instance_path, 'downloads', str(current_user.id))
    if os.path.exists(user_download_dir):
        try:
            filenames = os.listdir(user_download_dir)
            for f in filenames:
                if f.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.m4a')):
                    filepath = os.path.join(user_download_dir, f)
                    try:
                        file_size_mb = round(os.path.getsize(filepath) / (1024 * 1024), 2)
                        files_list.append({'name': f, 'size_mb': file_size_mb})
                    except OSError:
                        continue
        except Exception as e:
            flash(f"Error reading downloads directory: {e}", "error")
            current_app.logger.error(f"Error listing files for user {current_user.id}: {e}")

    files_list.sort(key=lambda x: x['name'])
    return render_template(
        'downloader_files.html',
        files=files_list,
        active_page='my_files',
        title='My Downloads'
    )


@downloader.route('/get-file/<path:filename>')
@login_required
def get_file(filename):
    """Securely serves a file from the user's specific download directory."""
    user_download_dir = os.path.join(current_app.instance_path, 'downloads', str(current_user.id))

    if '/' in filename or '\\' in filename:
        abort(400, "Invalid filename (path traversal detected).")

    try:
        return send_from_directory(user_download_dir, filename, as_attachment=True)
    except FileNotFoundError:
        abort(404)
    except Exception as e:
        current_app.logger.error(f"Error serving file {filename} for user {current_user.id}: {e}")
        abort(500)


@downloader.route('/delete-file/<path:filename>', methods=['POST'])
@login_required
def delete_file(filename):
    """Deletes a file from the user's specific download directory."""
    user_download_dir = os.path.join(current_app.instance_path, 'downloads', str(current_user.id))

    if '/' in filename or '\\' in filename:
        abort(400, "Invalid filename (path traversal detected).")

    file_path = os.path.join(user_download_dir, filename)

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            flash(f'"{filename}" has been deleted successfully.', 'success')
        else:
            flash('File not found.', 'error')
    except Exception as e:
        flash(f'Error deleting file: {e}', 'error')
        current_app.logger.error(f"Error deleting file {filename} for user {current_user.id}: {e}")

    return redirect(url_for('downloader.my_files'))