# app/blueprints/main/routes.py

from flask import Blueprint, render_template, redirect, url_for, request  # Removed current_app
from flask_login import current_user
# We rely on app/__init__.py and flask to make the DB available
from app.models import Post

main = Blueprint('main', __name__, template_folder='templates')


@main.route('/')
@main.route('/home')
def home():
    """
    Renders the homepage/dashboard, safely fetching recent posts.
    """

    # CRITICAL: This query must run safely within the request context.
    # We rely on Flask to activate the context for the duration of this function call.
    posts = Post.query.order_by(Post.date_posted.desc()).limit(5).all()

    return render_template('home.html',
                           title='Dashboard',
                           posts=posts,
                           active_page='home')


@main.route('/about')
def about():
    """
    Renders the static About page.
    Corresponds to: about.html
    """
    # CRITICAL: Pass 'active_page' for navigation highlighting
    return render_template('about.html',
                           title='About This Project',
                           active_page='about')