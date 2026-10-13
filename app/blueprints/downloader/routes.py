# downloader/routes.py

import os
import re
import shutil
import threading
import yt_dlp

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


def get_ffmpeg_dir():
    """Detect FFmpeg dynamically, with static-ffmpeg fallback for cloud environments like Render."""
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass

    ffmpeg_bin = shutil.which('ffmpeg')
    if ffmpeg_bin:
        return os.path.dirname(ffmpeg_bin)
    return None


def get_base_ydl_opts():
    """Returns baseline options for YoutubeDL with robust player client rotation to bypass datacenter bot checks."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'no_check_certificates': True,
        'geo_bypass': True,
        'socket_timeout': 30,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'android_creator', 'web']
            }
        }
    }
    ffmpeg_dir = get_ffmpeg_dir()
    if ffmpeg_dir:
        opts['ffmpeg_location'] = ffmpeg_dir

    return opts


# --- Background Download Function (using native yt-dlp API) ---
def download_process_thread(app, url, format_id, task_key, filepath):
    """Downloads a video stream in a separate thread using the native yt-dlp Python API."""
    global download_tasks

    with app.app_context():
        ffmpeg_dir = get_ffmpeg_dir()

        # Format selector: if ffmpeg is available, combine video+audio.
        # Otherwise fallback to best pre-merged stream so it never crashes.
        if ffmpeg_dir:
            if format_id == 'best':
                format_selector = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best'
            else:
                format_selector = f"{format_id}+bestaudio/best[ext=mp4]/{format_id}/best"
        else:
            if format_id == 'best':
                format_selector = 'best[ext=mp4]/best'
            else:
                format_selector = f"{format_id}/best[ext=mp4]/best"

        def progress_hook(d):
            task_info = download_tasks.get(task_key, {})
            if task_info.get('cancel_requested'):
                raise Exception("Download cancelled by user.")

            status = d.get('status')
            if status == 'downloading':
                downloaded = d.get('downloaded_bytes') or 0
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                if total > 0:
                    percent = int((downloaded / total) * 100)
                else:
                    raw_p = d.get('_percent_str', '0%')
                    match = re.search(r'([\d.]+)', raw_p)
                    percent = int(float(match.group(1))) if match else 0

                speed_str = d.get('_speed_str', '')
                task_info['progress'] = min(max(percent, 0), 98)
                task_info['speed_str'] = speed_str.strip() or 'Downloading...'
                task_info['status'] = 'downloading'

            elif status == 'finished':
                task_info['status'] = 'merging'
                task_info['speed_str'] = 'Finalizing and merging...'
                task_info['progress'] = 99

        ydl_opts = get_base_ydl_opts()
        ydl_opts.update({
            'format': format_selector,
            'outtmpl': filepath,
            'merge_output_format': 'mp4',
            'progress_hooks': [progress_hook],
            'noplaylist': True
        })

        try:
            current_app.logger.info(f"Starting download for {task_key} with format {format_selector}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            task_info = download_tasks.get(task_key, {})
            if task_info.get('cancel_requested'):
                raise Exception("Download cancelled by user.")

            # Resolve actual filepath
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
                    task_info['error_message'] = str(e).split(';')[0]
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
            ydl_opts = get_base_ydl_opts()
            ydl_opts['skip_download'] = True
            ydl_opts['noplaylist'] = True

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                data = ydl.extract_info(url, download=False)

            if not data:
                raise Exception("Could not retrieve video information.")

            video_title = data.get('title', 'Downloaded Video')
            video_id = str(data.get('id', 'video'))

            # Gather formats: ignore storyboards (mhtml)
            formats = data.get('formats', [])
            if not formats and data.get('url'):
                formats = [data]

            candidates = [
                f for f in formats
                if f.get('ext') != 'mhtml' and (f.get('vcodec') != 'none' or f.get('height') or f.get('ext') in ('mp4', 'webm', 'mkv'))
            ]

            # Sort best height/quality first
            candidates.sort(
                key=lambda x: (x.get('height') or 0, x.get('tbr') or 0, x.get('filesize') or 0),
                reverse=True
            )

            # 1. Always offer 'Best Available Quality' as the first option
            raw_key_best = f"{video_id}_best_{current_user.id}"
            task_key_best = "".join(c for c in raw_key_best if c.isalnum() or c in ('_', '-'))
            initiate_url_best = url_for(
                'downloader.initiate_download',
                format_id='best',
                task_key=task_key_best,
                url=url,
                title=video_title
            )
            download_options.append({
                'resolution': 'Best Available Quality (MP4)',
                'url': initiate_url_best,
                'task_key': task_key_best,
                'size_mb': 0
            })

            # 2. Add individual resolution options (deduplicated)
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
                    'resolution': f"{resolution} ({ext})",
                    'url': initiate_url,
                    'task_key': task_key,
                    'size_mb': size_mb
                })

            flash(f'Ready! Choose your download quality for "{video_title}".', 'info')

        except Exception as e:
            err_msg = str(e).split(';')[0].replace('ERROR:', '').strip()
            flash(f'Error fetching video data: {err_msg}', 'error')
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