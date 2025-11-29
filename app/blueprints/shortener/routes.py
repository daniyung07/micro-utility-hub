from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import ShortLink
from app.forms import ShortenerForm
from app.utils import generate_short_code

# Define the Shortener Blueprint
# NOTE: url_prefix='/links' is defined in the main __init__.py upon registration,
# but it is also acceptable to define it here for module clarity.
short = Blueprint('shortener', __name__, template_folder='templates')


@short.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """
    Handles displaying the form and processing the creation of a new short link.
    Corresponds to: shortener_create.html
    """
    form = ShortenerForm()

    if form.validate_on_submit():
        original_url = form.original_url.data

        # 1. NEW CHECK: Look up if the long URL already exists to prevent duplicates
        existing_link = ShortLink.query.filter_by(url=original_url).first()

        if existing_link:
            flash(f"This URL has already been shortened! Code: /links/{existing_link.short_url}", 'info')
            return redirect(url_for('shortener.index'))

        # 2. Generate a unique short code
        max_attempts = 5
        short_code = None

        for _ in range(max_attempts):
            code = generate_short_code()
            if not ShortLink.query.filter_by(short_url=code).first():
                short_code = code
                break

        if not short_code:
            flash('Error: Could not generate a unique short code after several attempts. Please try again.', 'error')
            return redirect(url_for('shortener.create'))

        # 3. Create and commit the new ShortLink object
        new_link = ShortLink(
            url=original_url,
            short_url=short_code,
            link_creator=current_user  # Using the cleaner SQLAlchemy relationship assignment
        )

        try:
            db.session.add(new_link)
            db.session.commit()
            flash(f'Success! Your short link is ready: /links/{short_code}', 'success')
            return redirect(url_for('shortener.index'))
        except IntegrityError:
            # Catches a database error (unlikely given the NEW CHECK above, but safe)
            db.session.rollback()
            flash('An error occurred. The URL might already be registered.', 'error')
            return redirect(url_for('shortener.create'))
        except Exception:
            db.session.rollback()
            flash('An internal error occurred while saving the link. Please try again.', 'error')

    return render_template('shortener_create.html',
                           title='Shorten URL',
                           form=form,
                           active_page='shortener')


@short.route('/')
@login_required
def index():
    """
    Displays all short links created by the current user, ordered newest first.
    Corresponds to: shortener_index.html
    """
    # Ordering links by ID descending (newest links at the top)
    user_links = ShortLink.query.filter_by(user_id=current_user.id).order_by(ShortLink.id.desc()).all()

    return render_template('shortener_index.html',
                           title='Manage Links',
                           links=user_links,
                           active_page='shortener')


@short.route('/<string:code>')
def redirect_to_url(code):
    """
    Handles the redirection from the short code to the original URL.
    The blueprint prefix (e.g., /links) handles the initial path.
    """
    link = ShortLink.query.filter_by(short_url=code).first()

    if link:
        # Increment click count and redirect
        link.clicks += 1
        db.session.commit()
        return redirect(link.url)
    else:
        # Custom flash error instead of dedicated 404 template (for consistency)
        flash(f'Error: The short link "{code}" does not exist.', 'error')
        return redirect(url_for('main.home'))


@short.route('/<int:link_id>/delete', methods=['POST'])
@login_required
def delete_link(link_id):
    """
    Deletes a specific short link.
    """
    link = ShortLink.query.get_or_404(link_id)

    # CRITICAL: Authorization check
    # Check against user_id property for robustness
    if link.user_id != current_user.id:
        flash('Error: You are not authorized to delete this link.', 'error')
        return redirect(url_for('shortener.index'))

    db.session.delete(link)
    db.session.commit()

    flash(f'Short link /links/{link.short_url} has been permanently deleted.', 'success')
    return redirect(url_for('shortener.index'))