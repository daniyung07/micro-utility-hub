# utils.py

import os
import secrets
import string
import base64
import io
from flask import current_app, flash
from PIL import Image

# Define constants for secure code generation
CHARACTERS = string.ascii_letters + string.digits
SHORT_CODE_LENGTH = 6


def generate_short_code():
    """Generates a secure, random 6-character alphanumeric code."""
    return ''.join(secrets.choice(CHARACTERS) for i in range(SHORT_CODE_LENGTH))


# ------------------------------------------------------
# 1. SAVE PROFILE PICTURE (HANDLING BASE64 DATA)
# ------------------------------------------------------

def save_base64_picture(base64_data):
    """
    Decodes a Base64 image string (from client-side cropper),
    resizes the image, and saves it with a unique filename.

    Raises an Exception if file processing fails.
    """
    if not base64_data:
        return None

    try:
        # 1. Split off the metadata/header from the Base64 string
        header, encoded = base64_data.split(',', 1)
        data = base64.b64decode(encoded)

        # 2. Determine file extension
        if 'jpeg' in header or 'jpg' in header:
            file_ext = '.jpg'
        elif 'webp' in header:
            file_ext = '.webp'
        else:
            file_ext = '.png'

        # 3. Generate secure filename and path
        random_hex = secrets.token_hex(8)
        picture_fn = random_hex + file_ext
        picture_path = os.path.join(current_app.root_path, 'static/profile_pics', picture_fn)

        # 4. Resize and Save using Pillow
        output_size = (300, 300)
        img = Image.open(io.BytesIO(data))
        img.thumbnail(output_size)
        img.save(picture_path)

        return picture_fn

    except Exception as e:
        # CRITICAL: We raise a custom error so the route can catch it and flash the user.
        raise Exception("Image processing failed. Ensure file is a valid image format.")


# ------------------------------------------------------
# 2. DELETE PROFILE PICTURE (Synchronous and Safe)
# ------------------------------------------------------

def delete_picture(old_picture_fn):
    """Safely deletes ONE profile picture file from static/profile_pics."""

    if not old_picture_fn or old_picture_fn == 'default.jpg':
        return

    safe_dir = os.path.join(current_app.root_path, 'static/profile_pics')
    old_picture_path = os.path.join(safe_dir, old_picture_fn)

    # Check if file exists and is within the safe directory
    if os.path.abspath(old_picture_path).startswith(os.path.abspath(safe_dir)) and os.path.exists(old_picture_path):
        try:
            os.remove(old_picture_path)
        except OSError:
            # CRITICAL: Flash a user-facing warning if deletion fails (e.g., file lock)
            flash("Warning: Could not delete old profile image due to file lock.", 'warning')
            pass
