# app/__init__.py

import os  # <--- Ensure os is imported
import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Globally initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '..', '.env'))


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key')

    # CRITICAL FIX: Use DATABASE_URL from environment for production
    # Fallback to SQLite for local development only
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'sqlite:///data.db'
    )
    # END CRITICAL FIX

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # --- RESTORED: Initialize extensions with the app ---
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    migrate.init_app(app, db)
    # --- END RESTORED ---

    # --- Database Initialization ---
    from . import models
    with app.app_context():
        # NOTE: db.create_all() only creates tables if they don't exist.
        # For a new PostgreSQL DB, this will create your tables.
        db.create_all()

        # --- Register Blueprints (MUST BE LAST) ---

    # 1. Import all blueprints
    from .blueprints.main.routes import main as main_bp
    from .blueprints.auth.routes import auth as auth_bp
    from .blueprints.blog.routes import blog as blog_bp
    from .blueprints.tasks.routes import tasks as tasks_bp
    from .blueprints.shortener.routes import short as shortener_bp
    from .blueprints.downloader.routes import downloader as downloader_bp

    # 2. Register all blueprints (Only once for each)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(blog_bp, url_prefix='/blog')
    app.register_blueprint(tasks_bp, url_prefix='/tasks')
    app.register_blueprint(shortener_bp, url_prefix='/links')
    app.register_blueprint(downloader_bp, url_prefix='/downloader')

    return app


# User Loader (CRITICAL: Must be able to access the User model)
from .models import User


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))