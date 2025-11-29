#blog/routes.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models import Post
from app.forms import PostForm
from sqlalchemy import or_

blog = Blueprint('blog', __name__, template_folder='templates')  # Removed url_prefix as it is set in __init__.py


@blog.route('/')
def blog_index():
    """
    Displays all blog posts with search filtering capabilities.
    Corresponds to: blog_index.html
    """
    search_query = request.args.get('search')
    query = Post.query

    # Apply Search Filter (Title OR Content, case-insensitive)
    if search_query:
        query = query.filter(
            or_(
                # Use ilike for case-insensitive matching
                Post.title.ilike(f'%{search_query}%'),
                Post.content.ilike(f'%{search_query}%')
            )
        )

    # Order by date posted (newest first)
    posts = query.order_by(Post.date_posted.desc()).all()
    return render_template('blog_index.html', title='Blog Index', posts=posts, active_page='blog')


@blog.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    """
    Handles form submission for creating a new post.
    Corresponds to: create_post.html
    """
    form = PostForm()
    if form.validate_on_submit():
        post = Post(
            title=form.title.data,
            content=form.content.data,
            # REFACTOR: Use the relationship attribute 'post_author' instead of 'user_id'
            post_author=current_user
        )

        db.session.add(post)
        db.session.commit()

        flash('Your post has been created!', 'success')
        # Redirect to the view page of the newly created post
        return redirect(url_for('blog.blog_index', post_id=post.id))

    return render_template('create_post.html', title='New Post', form=form, active_page='blog')


@blog.route("/post/<int:post_id>/view", methods=['GET'])
def view_post(post_id):
    """
    Displays a single blog post.
    Corresponds to: view_post.html
    """
    post = Post.query.get_or_404(post_id)
    return render_template('view_post.html', title=post.title, post=post, active_page='blog')


@blog.route("/post/<int:post_id>/edit", methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    """
    Handles editing an existing post, restricted to the author.
    Corresponds to: edit_post.html
    """
    post = Post.query.get_or_404(post_id)

    # CRITICAL: Authorization check
    if post.post_author.id != current_user.id:
        # REFACTOR: Use 'error' flash category for authorization failures
        flash('You are not authorized to edit this post.', 'error')
        return redirect(url_for('blog.view_post', post_id=post.id))  # Redirect back to view page

    # Instantiate form with existing post data (obj=post)
    form = PostForm(obj=post)

    if form.validate_on_submit():
        # Update the post object with new form data
        post.title = form.title.data
        post.content = form.content.data
        db.session.commit()
        flash('Your post has been updated!', 'success')
        return redirect(url_for('blog.view_post', post_id=post.id))  # Redirect to view after edit

    # Handle GET request (pre-populate form)
    return render_template('edit_post.html', title='Edit Post', form=form, post=post, active_page='blog')


@blog.route("/post/<int:post_id>/delete", methods=['POST'])
@login_required
def delete_post(post_id):
    """
    Deletes a post, restricted to the author.
    """
    post = Post.query.get_or_404(post_id)

    # CRITICAL: Authorization check
    if post.post_author.id != current_user.id:
        # REFACTOR: Use 'error' flash category for authorization failures
        flash('You are not authorized to delete this post.', 'error')
        return redirect(url_for('blog.view_post', post_id=post.id))  # Redirect back to view page

    db.session.delete(post)
    db.session.commit()

    flash('Your post has been deleted!', 'success')
    return redirect(url_for('blog.blog_index'))