from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# SQLite database stored in a file called tasks.db
# This means tasks PERSIST even when the server restarts
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tasks.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ─── DATABASE MODEL ───────────────────────────────────────────────────────────
# Think of this class as defining the "shape" of each row in our tasks table
class Task(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    content    = db.Column(db.String(200), nullable=False)
    priority   = db.Column(db.String(10), default='medium')   # high / medium / low
    due_date   = db.Column(db.String(20), nullable=True)       # stored as string: YYYY-MM-DD
    completed  = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Task {self.id}: {self.content}>'


# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Home page — show all tasks, newest first."""
    # You can later add sorting/filtering here (e.g. sort by due_date or priority)
    tasks = Task.query.order_by(Task.created_at.desc()).all()
    return render_template('index.html', tasks=tasks)


@app.route('/add', methods=['POST'])
def add_task():
    """Add a new task from the form submission."""
    content  = request.form.get('content', '').strip()
    priority = request.form.get('priority', 'medium')
    due_date = request.form.get('due_date', None)

    if not content:
        return redirect(url_for('index'))   # Ignore empty submissions

    new_task = Task(
        content  = content,
        priority = priority,
        due_date = due_date if due_date else None
    )
    db.session.add(new_task)
    db.session.commit()

    return redirect(url_for('index'))


@app.route('/complete/<int:task_id>')
def complete_task(task_id):
    """Toggle a task's completed status."""
    task = Task.query.get_or_404(task_id)
    task.completed = not task.completed   # Flip true→false or false→true
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/delete/<int:task_id>')
def delete_task(task_id):
    """Permanently remove a task."""
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('index'))


# ─── STARTUP ──────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Create the database tables if they don't exist yet
    # This runs automatically the first time you start the app
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)