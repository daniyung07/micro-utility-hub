#tasks/routes.py

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import Task
from app.forms import TaskForm
from datetime import datetime

# Define the Tasks Blueprint
# NOTE: Removed 'url_prefix' from Blueprint definition here, as it's typically set
# in the main __init__.py upon registration for centralized URL management.
tasks = Blueprint('tasks', __name__, template_folder='templates')


@tasks.route('/')
@login_required
def index():
    """
    Displays the user's tasks, ordered by completion status (incomplete first)
    and then by date posted (newest first).
    Corresponds to: task_index.html
    """
    # 1. Order by completion status (False comes before True/Incomplete before Complete)
    # 2. Then order by date posted (descending for newest tasks)
    user_tasks = Task.query.filter_by(user_id=current_user.id).order_by(
        Task.completed,  # Incomplete tasks appear first
        Task.date_posted.desc()
    ).all()

    return render_template('task_index.html',
                           title='My To-Do List',
                           user_tasks=user_tasks,
                           active_page='tasks')


@tasks.route('/new', methods=['GET', 'POST'])
@login_required
def new_task():
    """
    Handles the form for creating a new task.
    Corresponds to: create_task.html
    """
    form = TaskForm()

    if form.validate_on_submit():
        task = Task(
            title=form.title.data,
            content=form.content.data,
            # Assigning the SQLAlchemy relationship object is cleaner than setting user_id directly
            user_id=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        flash('Task added successfully!', 'success')
        return redirect(url_for('tasks.index'))

    return render_template('create_task.html',
                           title='Add New Task',
                           form=form,
                           active_page='tasks')


@tasks.route('/<int:task_id>/complete', methods=['POST'])
@login_required
def complete_task(task_id):
    """
    Toggles the completion status of a task and redirects back to the index.
    """
    # Use task_id for clarity in the route
    task = Task.query.get_or_404(task_id)

    # CRITICAL: Authorization check
    if task.user_id != current_user.id:
        flash('Error: You are not authorized to modify this task.', 'error')
        return redirect(url_for('tasks.index'))

    # Toggle the status
    task.completed = not task.completed
    db.session.commit()

    if task.completed:
        flash(f'Task "{task.title}" marked as complete! 🎉', 'success')
    else:
        flash(f'Task "{task.title}" marked as incomplete.', 'info')  # Using 'info' for less urgent feedback

    return redirect(url_for('tasks.index'))


@tasks.route('/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    """
    Deletes a specific task.
    """
    # Use task_id for clarity in the route
    task = Task.query.get_or_404(task_id)

    # CRITICAL: Authorization check
    if task.user_id != current_user.id:
        flash('Error: You are not authorized to delete this task.', 'error')
        return redirect(url_for('tasks.index'))

    db.session.delete(task)
    db.session.commit()
    flash(f'Task "{task.title}" has been deleted.', 'success')
    return redirect(url_for('tasks.index'))