#models.py

import datetime
from app import db  # Make sure db is imported from your app package (__init__.py)
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
# Correct import for Timed Serializer
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask import current_app


# --- User Model ---
class User(db.Model, UserMixin):
    __tablename__ = 'user'  # Optional: Explicit table name

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False, index=True)  # Added index
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)  # Added index
    password_hash = db.Column(db.String(150), nullable=False)  # Increased length slightly for future hash methods
    image_file = db.Column(db.String(30), nullable=False, default='default.jpg')  # Increased length for hex filenames
    country = db.Column(db.String(50), nullable=True)
    state = db.Column(db.String(50), nullable=True)

    # Relationships (Using 'lazy=True' is standard, 'dynamic' is an alternative if needed)
    # Corrected backref names to match model names (lowercase)
    posts = db.relationship('Post', backref='post_author', lazy=True, cascade="all, delete-orphan")
    tasks = db.relationship('Task', backref='task_owner', lazy=True, cascade="all, delete-orphan")
    short_links = db.relationship('ShortLink', backref='link_creator', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        """Hashes the password and stores it."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Checks if the provided password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

        # In app/models.py within the User class

    def get_reset_token(self, expires_sec=1800):
        """Generates a timed reset token."""
        s = Serializer(current_app.config['SECRET_KEY'])
        # FIX: Remove .decode('utf-8') as dumps() is already returning a string
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_token(token, expires_sec=1800):
        """Verifies a reset token and returns the User if valid and not expired."""
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            # loads expects bytes or string, pass max_age for expiration check
            user_id = s.loads(token, max_age=expires_sec)['user_id']
        except Exception:  # Catches SignatureExpired, BadSignature, etc.
            return None
        return User.query.get(user_id)

    def __repr__(self):
        return f"<User {self.username}>"


# --- Post Model ---
class Post(db.Model):
    __tablename__ = 'post'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)  # Added index
    # Foreign Key referencing 'user.id' (table name . column name)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"<Post {self.title}>"


# --- Task Model ---
class Task(db.Model):
    __tablename__ = 'task'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)  # Changed from Text - Text is usually for longer content
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)  # Added index
    completed = db.Column(db.Boolean, nullable=False, default=False, index=True)  # Added index
    # Foreign Key referencing 'user.id'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"<Task {self.title} (User: {self.user_id})>"


# --- ShortLink Model ---
class ShortLink(db.Model):
    __tablename__ = 'short_link'

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(2048), nullable=False)  # Kept original URL length
    short_url = db.Column(db.String(10), nullable=False, unique=True, index=True)  # Added index
    clicks = db.Column(db.Integer, nullable=False, default=0)
    date_created = db.Column(db.DateTime, nullable=True, default=datetime.datetime.utcnow,
                             index=True)  # Added date_created + index
    # Foreign Key referencing 'user.id'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"<ShortLink {self.short_url} -> {self.url[:30]}>"