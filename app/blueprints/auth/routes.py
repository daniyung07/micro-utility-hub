#auth/routes.py

import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, current_user, logout_user, login_required
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import User
from app.forms import RegistrationForm, LoginForm, RequestResetForm, ResetPasswordForm, EditProfileForm
from app.utils import save_base64_picture, delete_picture  # Helper for saving images


# --- HELPER FUNCTION: SIMULATED EMAIL ---
def send_reset_email(user):
    """Generates reset token and simulates sending email (logs URL to console)."""
    token = user.get_reset_token()
    reset_url = url_for('auth.reset_token', token=token, _external=True)
    print(f"\n--- PASSWORD RESET LINK (Test Only) ---")
    print(f"To: {user.email}")
    print(f"LINK: {reset_url}\n")
    print("----------------------------------------\n")


auth = Blueprint('auth', __name__, template_folder='templates', url_prefix='/auth')


# ----------------------------------------------------
# 1. LOGIN / LOGOUT / REGISTER
# ----------------------------------------------------

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256')
        user = User(
            username=form.username.data.strip().lower(),
            email=form.email.data.strip().lower(),
            password_hash=hashed_password
        )
        try:
            db.session.add(user)
            db.session.commit()
            flash('Your account has been created! You are now able to log in.', 'success')
            return redirect(url_for('auth.login'))
        except IntegrityError:
            db.session.rollback()
            flash('Registration failed. Username or email already exists.', 'danger')
        except Exception:
            db.session.rollback()
            flash('An unexpected error occurred during registration.', 'danger')

    return render_template('register.html', title='Register', form=form)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            flash(f"Welcome back, {user.username}!", 'success')
            return redirect(next_page) if next_page else redirect(url_for('main.home'))
        else:
            flash('Login Unsuccessful. Please check email and password.', 'danger')

    return render_template('login.html', title='Login', form=form)


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.home'))


# ----------------------------------------------------
# 2. PASSWORD RESET FLOW
# ----------------------------------------------------

@auth.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()

        if user:
            # CRITICAL: Send the secure token email (simulated)
            send_reset_email(user)
            flash('An email has been sent with instructions to reset your password.', 'info')
            return redirect(url_for('auth.login'))
        else:
            # Vague response for security reasons
            flash('If an account exists for that email, instructions have been sent.', 'info')
            return redirect(url_for('auth.login'))

    return render_template('reset_request.html', title='Request Reset', form=form)


@auth.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    # Verify the token is valid and not expired
    user = User.verify_reset_token(token)
    if not user:
        flash('That is an invalid or expired token.', 'danger')
        return redirect(url_for('auth.login'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        # Hash and save the new password
        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256')

        user.password_hash = hashed_password
        db.session.commit()

        flash('Your password has been reset. You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_token.html', title='Reset Password', form=form)

# ----------------------------------------------------
# 3. PROFILE MANAGEMENT (PRIVATE/EDITING VIEW)
# ----------------------------------------------------

@auth.route("/profile", methods=['GET', 'POST'])
@login_required
def profile():
    # Instantiate form with current user's data on GET request
    # NOTE: obj=current_user loads initial data, but doesn't handle validation/submission logic automatically
    form = EditProfileForm(obj=current_user)

    if form.validate_on_submit():

        # --- 1. UNIQUNESS CHECKS ---
        # The form is instantiated with the *current* user data, so we only need to check if the data changed
        # AND if the new value is already taken.

        # Check email uniqueness if email was changed
        if form.email.data != current_user.email:
            if User.query.filter_by(email=form.email.data).first():
                flash('Email already taken by another user. Update failed.', 'error')  # Changed danger to error
                return redirect(url_for('auth.profile'))

        # Check username uniqueness if username was changed
        if form.username.data != current_user.username:
            if User.query.filter_by(username=form.username.data).first():
                flash('Username already taken by another user. Update failed.', 'error')  # Changed danger to error
                return redirect(url_for('auth.profile'))

        # --- 2. IMAGE REPLACEMENT LOGIC ---

        # 1. Initialize variables for potential image update
        new_image_file = None
        cropped_data = request.form.get('image_data_uri')  # Data from Cropper.js

        if cropped_data:
            old_picture = current_user.image_file
            try:
                # Save the new Base64 image and get its unique filename
                new_image_file = save_base64_picture(cropped_data)

                # Delete the old file only after the new one is successfully saved
                delete_picture(old_picture)

            except Exception as e:
                # If image processing fails, flash the error and halt the entire process.
                # No DB operation has occurred yet, so no rollback is strictly necessary,
                # but we flash and redirect immediately.
                flash(str(e), 'error')  # Changed danger to error
                return redirect(url_for('auth.profile'))

        # --- 3. APPLY ALL UPDATES & COMMIT (Consolidated logic) ---

        # Apply text updates (runs after successful image handling or if no image was provided)
        current_user.username = form.username.data.strip().lower()
        current_user.email = form.email.data.strip().lower()
        current_user.country = form.country.data
        current_user.state = form.state.data

        # Apply image update if a new file was successfully created
        if new_image_file:
            current_user.image_file = new_image_file

        try:
            db.session.commit()
            flash('Your profile has been updated successfully.', 'success')
            return redirect(url_for('auth.user_profile', username=current_user.username))
        except IntegrityError:
            # Catching rare commit errors (e.g., unexpected race condition)
            db.session.rollback()
            flash('An unexpected error occurred during profile update.', 'error')  # Changed danger to error
            return redirect(url_for('auth.profile'))

    # GET request or form validation failed
    return render_template('profile.html', title='Account Settings', form=form, active_page='profile')


# ----------------------------------------------------
# 4. PUBLIC PROFILE VIEW (READ-ONLY)
# ----------------------------------------------------

@auth.route("/profile/<username>", methods=['GET'])
def user_profile(username):
    # Retrieve the target user object or abort with a 404
    user = User.query.filter_by(username=username).first()

    if user is None:
        abort(404)

    # Render the public, read-only template
    return render_template('public_profile.html',
                           profile_user=user,
                           title=f"{user.username}'s Profile",
                           active_page='profile'
                           )