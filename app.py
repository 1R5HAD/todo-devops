import os
import resend
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

app = Flask(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

database_url = os.environ.get('DATABASE_URL', 'sqlite:///tasks.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Resend API key — set this in Render environment variables
resend.api_key = os.environ.get('RESEND_API_KEY', '')

db = SQLAlchemy(app)

# ─── AUTH SETUP ───────────────────────────────────────────────────────────────

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = ''


# ─── MODELS ───────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    tasks = db.relationship('Task', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Task(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    content    = db.Column(db.String(200), nullable=False)
    priority   = db.Column(db.String(10), default='medium')
    due_date   = db.Column(db.String(20), nullable=True)
    completed  = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── EMAIL HELPER ─────────────────────────────────────────────────────────────

def send_email(to, subject, body):
    """Send an email using Resend API."""
    try:
        resend.Emails.send({
            "from": "TaskFlow <onboarding@resend.dev>",  # Resend's free test sender
            "to": to,
            "subject": subject,
            "text": body
        })
        print(f"[Email] Sent to {to}")
        return True
    except Exception as e:
        print(f"[Email] Failed to send to {to}: {e}")
        return False


# ─── EMAIL NOTIFICATION JOB ───────────────────────────────────────────────────

def send_due_reminders():
    """
    Runs every day at 8AM IST.
    Finds all incomplete tasks due in exactly 2 days and emails the owner.
    """
    with app.app_context():
        target_date = (date.today() + timedelta(days=2)).strftime('%Y-%m-%d')
        print(f"[Scheduler] Checking for tasks due on {target_date}")

        upcoming_tasks = Task.query.filter_by(
            due_date=target_date,
            completed=False
        ).all()

        if not upcoming_tasks:
            print(f"[Scheduler] No tasks due on {target_date}")
            return

        # Group tasks by user so each user gets one email
        tasks_by_user = {}
        for task in upcoming_tasks:
            user = User.query.get(task.user_id)
            if user:
                if user.id not in tasks_by_user:
                    tasks_by_user[user.id] = {'user': user, 'tasks': []}
                tasks_by_user[user.id]['tasks'].append(task)

        for entry in tasks_by_user.values():
            user  = entry['user']
            tasks = entry['tasks']

            task_lines = '\n'.join(
                f"  • {t.content} [{t.priority.upper()} priority]"
                for t in tasks
            )

            subject = f"⏰ Reminder: You have {len(tasks)} task{'s' if len(tasks) > 1 else ''} due in 2 days!"
            body = f"""Hi {user.username},

This is a friendly reminder from TaskFlow.

The following task{'s' if len(tasks) > 1 else ''} {'are' if len(tasks) > 1 else 'is'} due on {target_date}:

{task_lines}

Don't forget to complete {'them' if len(tasks) > 1 else 'it'} on time!

Open your task list: https://todo-devops-jexx.onrender.com

— TaskFlow
"""
            send_email(user.email, subject, body)


# ─── SCHEDULER SETUP ──────────────────────────────────────────────────────────

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=send_due_reminders,
        trigger='cron',
        hour=8,
        minute=0,
        timezone='Asia/Kolkata',    # fires at 8:00 AM IST every day
        id='due_reminder'
    )
    scheduler.start()
    print("[Scheduler] Started — reminders fire daily at 8:00 AM IST")
    atexit.register(lambda: scheduler.shutdown())


# ─── ROUTES: AUTH ─────────────────────────────────────────────────────────────

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash('All fields are required.', 'error')
            return redirect(url_for('signup'))
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('signup'))
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return redirect(url_for('signup'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('signup'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('index'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ─── ROUTES: TASKS ────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    tasks = Task.query.filter_by(user_id=current_user.id)\
                      .order_by(Task.created_at.desc()).all()
    return render_template('index.html', tasks=tasks)


@app.route('/add', methods=['POST'])
@login_required
def add_task():
    content  = request.form.get('content', '').strip()
    priority = request.form.get('priority', 'medium')
    due_date = request.form.get('due_date', None)

    if not content:
        return redirect(url_for('index'))

    new_task = Task(
        content  = content,
        priority = priority,
        due_date = due_date if due_date else None,
        user_id  = current_user.id
    )
    db.session.add(new_task)
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/complete/<int:task_id>')
@login_required
def complete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    task.completed = not task.completed
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/delete/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return redirect(url_for('index'))


# ─── TEST EMAIL ROUTE (remove before final submission) ────────────────────────

@app.route('/test-email')
@login_required
def test_email():
    success = send_email(
        to=current_user.email,
        subject="✅ TaskFlow — Test Email",
        body=f"Hi {current_user.username},\n\nThis is a test email from TaskFlow.\n\nIf you received this, your email setup is working!\n\n— TaskFlow"
    )
    if success:
        return f"✅ Test email sent to {current_user.email} — check your inbox!"
    else:
        return f"❌ Failed to send email — check your RESEND_API_KEY on Render."


# ─── STARTUP ──────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

start_scheduler()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
