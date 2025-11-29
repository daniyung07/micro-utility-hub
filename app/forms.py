#forms.py

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, EmailField, PasswordField, SubmitField, TextAreaField, URLField
)
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, URL
)

# --- Authentication Forms ---
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20, message='Username must be 3-20 characters.')])
    email = EmailField('Email', validators=[DataRequired(), Email(message='Invalid email address.')])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, message='Password must be at least 6 characters.')])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit = SubmitField('Sign Up')

class LoginForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class RequestResetForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Reset Password')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, message='Password must be at least 6 characters.')])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit = SubmitField('Submit')


class EditProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(),
                                                   Length(min=3, max=20, message='Username must be 3-20 characters.')])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    country = StringField('Country', validators=[DataRequired()])
    state = StringField('State', validators=[DataRequired()])
    image_data_uri = StringField('Cropped Image Data')

    submit = SubmitField('Update')

# --- Utility Forms ---
class PostForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=100)])
    content = TextAreaField('Content', validators=[DataRequired()])
    submit = SubmitField('Post')

class TaskForm(FlaskForm):
    title = StringField('Task Title', validators=[DataRequired(), Length(max=100)])
    content = TextAreaField('Details', validators=[DataRequired()])
    submit = SubmitField('Add Task')

class ShortenerForm(FlaskForm):
    original_url = URLField('URL to Shorten', validators=[DataRequired(), URL()])
    submit = SubmitField('Shorten')

class YouTubeDownloaderForm(FlaskForm):
    youtube_url = StringField('YouTube Video URL', validators=[DataRequired(), URL(message='Please enter a valid YouTube URL.')])
    submit = SubmitField('Download Video')