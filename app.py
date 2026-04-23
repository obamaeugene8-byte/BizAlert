from flask import Flask, request, redirect, url_for, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import hashlib
import os

# -----------------------------
# APP SETUP
# -----------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "fallback_secret")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# -----------------------------
# DATABASE MODELS
# -----------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    paid = db.Column(db.Boolean, default=False)

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    message = db.Column(db.Text)
    score = db.Column(db.Integer)

class Rule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    keyword = db.Column(db.String(100))
    weight = db.Column(db.Integer)

# ✅ FIX: create tables inside app context
with app.app_context():
    db.create_all()

# -----------------------------
# LOGIN HANDLER
# -----------------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -----------------------------
# RISK ENGINE
# -----------------------------
def calculate_risk(user_id, text):
    text = text.lower()
    rules = Rule.query.filter_by(user_id=user_id).all()

    score = 0
    for r in rules:
        if r.keyword in text:
            score += r.weight

    return min(score, 10)

def build_message(score, event):
    if score >= 8:
        return f"🚨 CRITICAL: {event} | Risk {score}/10"
    elif score >= 5:
        return f"⚠️ WARNING: {event} | Risk {score}/10"
    else:
        return f"ℹ️ INFO: {event} | Risk {score}/10"

def process_event(user_id, event_text):
    score = calculate_risk(user_id, event_text)
    message = build_message(score, event_text)

    alert = Alert(user_id=user_id, message=message, score=score)
    db.session.add(alert)
    db.session.commit()

    return message

# -----------------------------
# ROUTES
# -----------------------------

@app.route('/')
@login_required
def dashboard():
    if not current_user.paid and not current_user.is_admin:
        return "<h2>Access denied. Please subscribe.</h2>"

    alerts = Alert.query.filter_by(user_id=current_user.id).all()
    return render_template("dashboard.html", alerts=alerts)

# -----------------------------
# LOGIN
# -----------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()

        user = User.query.filter_by(email=email, password=password).first()

        if user:
            login_user(user)
            return redirect(url_for('dashboard'))

    return render_template("login.html")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# -----------------------------
# ADMIN PANEL
# -----------------------------
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        return "Unauthorized"

    users = User.query.all()
    return render_template("admin.html", users=users)

# -----------------------------
# CREATE USER
# -----------------------------
@app.route('/admin/create_user', methods=['POST'])
@login_required
def create_user():
    if not current_user.is_admin:
        return "Unauthorized"

    email = request.form['email']
    password = hashlib.sha256(request.form['password'].encode()).hexdigest()

    user = User(email=email, password=password, paid=False)
    db.session.add(user)
    db.session.commit()

    return redirect(url_for('admin'))

# -----------------------------
# TOGGLE PAYMENT
# -----------------------------
@app.route('/admin/toggle/<int:user_id>')
@login_required
def toggle(user_id):
    if not current_user.is_admin:
        return "Unauthorized"

    user = User.query.get(user_id)
    user.paid = not user.paid
    db.session.commit()

    return redirect(url_for('admin'))

# -----------------------------
# ADD RULE
# -----------------------------
@app.route('/admin/add_rule', methods=['POST'])
@login_required
def add_rule():
    if not current_user.is_admin:
        return "Unauthorized"

    rule = Rule(
        user_id=request.form['user_id'],
        keyword=request.form['keyword'],
        weight=int(request.form['weight'])
    )

    db.session.add(rule)
    db.session.commit()

    return redirect(url_for('admin'))

# -----------------------------
# EVENT API (INTEGRATION POINT)
# -----------------------------
@app.route('/event', methods=['POST'])
def event():
    data = request.json

    user_id = data.get('user_id')
    event_text = data.get('event')

    user = User.query.get(user_id)

    if not user or not user.paid:
        return jsonify({"status": "blocked"})

    message = process_event(user_id, event_text)

    return jsonify({
        "status": "ok",
        "message": message
    })

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)
