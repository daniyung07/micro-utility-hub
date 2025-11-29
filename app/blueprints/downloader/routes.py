#downloader/routes.py

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, send_file, current_app, jsonify,
    send_from_directory, abort
)
from flask_login import login_required, current_user
import os
import threading
import subprocess
import json
import re

from app.forms import YouTubeDownloaderForm

downloader = Blueprint('downloader', __name__, template_folder='templates')

# In-memory storage for download progress
download_tasks = {}
# Structure: { task_key: {'progress': %, 'status': '...', 'filepath': '...', 'thread': obj, 'process': obj,
#                         'cancel_requested': bool, 'error_message': '...', 'speed_str': '...', 'download_name': '...'} }

# --- Regex for parsing yt-dlp output ---
PROGRESS_RE = re.compile(
    # [download]   5.0% of  501.52MiB at  2.56MiB/s ETA 03:08
    r"\[download\]\s+(?P<percent>[\d\.]+)%\s+of\s+~?(?P<size>[\d\.]+\w{1,2}i?B)\s+at\s+(?P<speed>[\d\.]+\w{1,2}i?B/s)"
)


# --- Background Download Function (using yt-dlp) ---
def download_process_thread(app, url, format_id, task_key, filepath):
    """Downloads a video stream in a separate thread using yt-dlp subprocess."""
    global download_tasks

    with app.app_context():
        cookies_path = os.path.join(current_app.instance_path, 'cookies.txt')

        # --- FIX 1: Explicitly set FFmpeg path ---
        # This tells yt-dlp exactly where to find ffmpeg.exe
        ffmpeg_path = r'C:\ffmpeg'

        try:
            command = [
                'yt-dlp',
                '--cookies', cookies_path,
                '--ffmpeg-location', ffmpeg_path,  # <-- ADDED THIS LINE
                '-f', f"{format_id}+bestaudio",
                '-o', filepath,
                '--progress',
                '--no-playlist',
                '--newline',
                '-q', '--no-warnings',
                '--merge-output-format', 'mp4',
                url
            ]

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if task_key in download_tasks:
                download_tasks[task_key]['process'] = process

            print(f"DEBUG: Started yt-dlp process for {task_key}...")

            for line in iter(process.stdout.readline, ''):
                if not line:
                    break

                task_info = download_tasks.get(task_key, {})
                if task_info.get('cancel_requested'):
                    process.terminate()
                    raise Exception("Download cancelled by user.")

                match = PROGRESS_RE.search(line.strip())
                if match:
                    data = match.groupdict()
                    percentage = float(data['percent'])
                    speed = data['speed']

                    if task_key in download_tasks:
                        download_tasks[task_key]['progress'] = int(percentage)
                        download_tasks[task_key]['speed_str'] = speed
                        download_tasks[task_key]['status'] = 'downloading'

            process.stdout.close()
            return_code = process.wait()
            print(f"DEBUG: yt-dlp process for {task_key} finished with code {return_code}")

            task_info = download_tasks.get(task_key, {})
            if task_info.get('cancel_requested'):
                raise Exception("Download cancelled by user.")

            if return_code == 0:
                # --- FIX 2: Simplify file check ---
                # We told yt-dlp to create 'filepath'. We just
                # need to check if that one specific file exists.
                if os.path.exists(filepath):
                    task_info['filepath'] = filepath
                    task_info['download_name'] = os.path.basename(filepath)
                    task_info['status'] = 'complete'
                    task_info['progress'] = 100
                    task_info['speed_str'] = "Complete"
                else:
                    # This error is now 100% correct. It means the merge failed.
                    raise Exception("Download finished but output file not found. Merge failed.")
                # --- END FIX 2 ---

            else:
                raise Exception(f"yt-dlp exited with error code {return_code}")

        except Exception as e:
            print(f"DEBUG: Exception in download thread for {task_key}: {e}")
            if task_key in download_tasks:
                task_info = download_tasks[task_key]
                if "cancelled by user" in str(e):
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
                    current_app.logger.error(f"Download thread error for {task_key}: {e}")


@downloader.route('/download', methods=['GET', 'POST'])
@login_required
def download():
    """Handles the initial form display and processes URL to show download options."""
    form = YouTubeDownloaderForm()
    video_title = None
    download_options = []

    if form.validate_on_submit():
        url = form.youtube_url.data
        cookies_path = os.path.join(current_app.instance_path, 'cookies.txt')

        try:
            # Use yt-dlp to get video info as JSON
            command = [
                'yt-dlp',
                '--cookies', cookies_path,  # Use cookies to get all data
                '--no-update',  # <-- FIX: Stops checking for updates
                '--no-call-home',  # <-- FIX: Stops reporting errors
                '--dump-json',
                '--no-playlist',
                url
            ]

            # Use subprocess.run for a blocking call with a timeout
            result = subprocess.run(
                command,
                capture_output=True, text=True, encoding='utf-8',
                check=True, timeout=120  # 2-minute timeout
            )

            data = json.loads(result.stdout)
            video_title = data.get('title', 'Unknown Title')
            video_id = data.get('id', 'unknown_id')

            # Get video-only streams (yt-dlp will merge audio)
            streams = [
                f for f in data.get('formats', [])
                if f.get('vcodec') != 'none' and f.get('acodec') == 'none'
            ]
            streams.sort(key=lambda x: x.get('height', 0), reverse=True)  # Best quality first

            if streams:
                for stream in streams:
                    format_id = stream.get('format_id')
                    task_key = f"{video_id}_{format_id}_{current_user.id}"

                    # Pass URL and Title to the initiate step
                    initiate_url = url_for('downloader.initiate_download',
                                           format_id=format_id,
                                           task_key=task_key,
                                           url=url,
                                           title=video_title)

                    file_size = stream.get('filesize') or stream.get('filesize_approx') or 0
                    resolution = stream.get('resolution', stream.get('format_note', 'Unknown'))

                    download_options.append({
                        'resolution': resolution,
                        'url': initiate_url,
                        'task_key': task_key,
                        'size_mb': round(file_size / (1024 * 1024), 2)
                    })
                flash(f'Processing "{video_title}". Choose a download option below.', 'info')
            else:
                flash('No suitable MP4 streams found for this video.', 'error')

        except subprocess.TimeoutExpired:
            flash('Error: Timed out trying to get video data. The site might be slow or blocking (check cookies).',
                  'error')
        except subprocess.CalledProcessError as e:
            flash(f'Error fetching video data. Check URL. (yt-dlp error)', 'error')
            current_app.logger.error(f"yt-dlp JSON error: {e.stderr}")
        except Exception as e:
            flash(f'An unexpected error occurred: {e}', 'error')
            current_app.logger.error(f"Downloader processing error: {e}")

        return render_template('downloader.html', title='Downloader', form=form,
                               video_title=video_title, download_options=download_options,
                               active_page='downloader')

    return render_template('downloader.html', title='Downloader', form=form,
                           active_page='downloader')


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

    # Create a safe filename. We'll add .mp4, but yt-dlp might change it.
    if video_title:
        safe_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '.', '_', '-')).rstrip().strip()
        safe_title = safe_title[:60]  # Truncate long titles
        safe_filename = f"{safe_title}.mp4"
    else:
        safe_filename = f"{task_key.split('_')[0]}.mp4"

    download_dir = os.path.join(current_app.instance_path, 'downloads', str(current_user.id))
    os.makedirs(download_dir, exist_ok=True)
    filepath = os.path.join(download_dir, safe_filename)  # This is the *target* filepath

    app = current_app._get_current_object()  # <-- ADD THIS to get the real app

    thread = threading.Thread(
        target=download_process_thread,
        args=(app, url, format_id, task_key, filepath)  # <-- ADD 'app' as the first arg
    )

    download_tasks[task_key] = {
        'progress': 0, 'status': 'starting', 'thread': thread, 'process': None,
        # ... rest of the dict
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
        return jsonify({'status': 'not_found', 'message': 'Task not found or unauthorized.'}), 404

    response_data = {
        'status': task['status'],
        'progress': task['progress'],
        'speed_str': task.get('speed_str', '')
    }

    if task['status'] == 'complete':
        response_data['download_url'] = url_for('downloader.get_final_file', task_key=task_key)
    elif task['status'] == 'error':
        response_data['message'] = task.get('error_message', 'An unknown error occurred.')

    return jsonify(response_data)


@downloader.route('/get_final/<string:task_key>')
@login_required
def get_final_file(task_key):
    """Serves the completed download file."""
    global download_tasks
    task = download_tasks.get(task_key)

    if not task or not task_key.endswith(f"_{current_user.id}") or task['status'] != 'complete' or not task['filepath']:
        flash('Download not found, not complete, or unauthorized.', 'error')
        return redirect(url_for('downloader.download'))

    # Read the final, correct filepath and name from the task
    file_path = task['filepath']
    download_name = task.get('download_name', 'download.mp4')

    if os.path.exists(file_path):
        # Clean up the task from memory after serving it
        if task_key in download_tasks:
            del download_tasks[task_key]
        return send_file(file_path, as_attachment=True, download_name=download_name)
    else:
        flash('Error: Downloaded file is missing on the server.', 'error')
        if task_key in download_tasks: del download_tasks[task_key]
        return redirect(url_for('downloader.download'))


@downloader.route('/cancel/<string:task_key>', methods=['POST'])
@login_required
def cancel_download(task_key):
    """Attempts to cancel an ongoing download."""
    global download_tasks
    task = download_tasks.get(task_key)

    if not task or not task_key.endswith(f"_{current_user.id}"):
        return jsonify({'status': 'not_found'}), 404

    if task['status'] == 'downloading' or task['status'] == 'starting':
        print(f"DEBUG: Requesting cancellation for {task_key}")
        task['cancel_requested'] = True  # Set the flag for the thread

        process = task.get('process')
        if process:
            try:
                process.terminate()  # Terminate the subprocess
                print(f"DEBUG: Terminated process for {task_key}")
            except Exception as e:
                print(f"DEBUG: Error terminating process for {task_key}: {e}")

        return jsonify({'status': 'cancel_requested'})
    else:
        return jsonify({'status': task['status']})


# --- Routes for "My Downloads" page (No changes needed) ---

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
                # Check for all formats yt-dlp might save
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
    return render_template('downloader_files.html',
                           files=files_list,
                           active_page='my_files',
                           title='My Downloads')


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