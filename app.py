import os
import resend
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect, text, func
from sqlalchemy.exc import IntegrityError
from itsdangerous import URLSafeTimedSerializer
from models import db, User, Prompt, Favorite
from forms import RegisterForm, LoginForm, PromptForm, CATEGORIES
import sendgrid
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv
load_dotenv(override=True)
from gemini_helper import improve_prompt


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback-dev-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///prompts.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "connect_args": {"connect_timeout": 10}
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["ADMIN_EMAIL"] = os.environ.get("ADMIN_EMAIL", "rohithbuildsofficial@gmail.com")

resend.api_key = os.environ.get("RESEND_API_KEY")

csrf = CSRFProtect(app)
db.init_app(app)

@app.context_processor
def inject_csrf_token():
    is_admin = (current_user.is_authenticated and getattr(current_user, "email", None) == app.config["ADMIN_EMAIL"])
    return dict(csrf_token=generate_csrf, is_admin=is_admin)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def generate_verification_token(email):
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    return serializer.dumps(email, salt="email-confirm-salt")

def verify_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    try:
        return serializer.loads(token, salt="email-confirm-salt", max_age=expiration)
    except Exception:
        return None

def send_verification_email(user):
    token = generate_verification_token(user.email)
    verify_url = url_for("verify_email", token=token, _external=True)
    try:
        html_content = render_template(
            "email/verify_email.html",
            username=user.username.title(),
            verify_url=verify_url
        )
        sg = sendgrid.SendGridAPIClient(api_key=os.environ.get("SENDGRID_API_KEY"))
        message = Mail(
            from_email="rohithbuildsofficial@gmail.com",
            to_emails=user.email,
            subject="Verify Your Email - RohithBuilds",
            html_content=html_content
        )
        response = sg.send(message)
        print(f"✅ SendGrid sent: {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ SendGrid error: {e}")
        return False

def build_prompt_feed_context(category="", search=""):
    query = Prompt.query

    if category:
        query = query.filter_by(category=category)

    if search:
        search_term = f"%{search}%"
        query = query.filter(db.or_(Prompt.title.ilike(search_term), Prompt.content.ilike(search_term)))

    prompts = query.order_by(Prompt.created_at.desc(), Prompt.id.desc()).all()

    user_favorites = set()
    if current_user.is_authenticated:
        user_favorites = {favorite.prompt_id for favorite in Favorite.query.filter_by(user_id=current_user.id).all()}

    clear_search_params = {}
    if category:
        clear_search_params["category"] = category

    return {
        "prompts": prompts,
        "categories": [category_name for category_name, _ in CATEGORIES],
        "active_category": category,
        "search": search,
        "user_favorites": user_favorites,
        "prompt_count": len(prompts),
        "total_prompts": Prompt.query.count(),
        "clear_search_url": url_for("vault", **clear_search_params),
    }

SEED_PROMPTS = [
    {"title": "Ultimate Code Reviewer", "content": "You are an expert senior software engineer conducting a thorough code review...", "category": "Coding"},
    {"title": "Viral Twitter Thread Generator", "content": "You are a viral social media strategist...", "category": "Marketing"},
    {"title": "Startup Idea Validator", "content": "Act as a seasoned startup mentor...", "category": "Business"},
    {"title": "Essay Writing Assistant", "content": "You are an expert academic writer...", "category": "Writing"},
    {"title": "Personal Tutor - Any Subject", "content": "You are a world-class tutor...", "category": "Education"},
]

def seed_database():
    if User.query.first():
        return
    seed_user = User(username="rohithbuilds", email="rohithbuildsofficial@gmail.com", password_hash=generate_password_hash("admin123"), is_verified=True)
    db.session.add(seed_user)
    db.session.flush()
    for p in SEED_PROMPTS:
        db.session.add(Prompt(title=p["title"], content=p["content"], category=p["category"], likes=0, user_id=seed_user.id))
    db.session.commit()
    print("✅ Database seeded successfully.")

# ── NEW MAIN ROUTES ───────────────────────────────────────────────────────────────

@app.route("/")
def home():
    """New Clean Landing Page"""
    return render_template("home.html")

@app.route("/vault")
def vault():
    """Prompt Vault / Library"""
    feed = build_prompt_feed_context(
        category=request.args.get("category", "").strip(),
        search=request.args.get("search", "").strip(),
    )
    return render_template("vault.html", **feed)

@app.route("/learn")
def learn():
    """Daily Lessons Page (Image Cards)"""
    lessons = [
        {"day": 1, "title": "Day 1: Introduction to Prompt Engineering", "image": "images/lessons/day1.png", "desc": "Learn the fundamentals of writing great prompts."},
        {"day": 2, "title": "Day 2: Advanced Techniques", "image": "images/lessons/day2.png", "desc": "Master chain of thought and role prompting."},
        {"day": 3, "title": "Day 3: Creative Writing Prompts", "image": "images/lessons/day3.png", "desc": "Create compelling stories and content."},
        {"day": 4, "title": "Day 4: Coding & Development", "image": "images/lessons/day4.png", "desc": "Use AI to boost your programming skills."},
        {"day": 5, "title": "Day 5: Business & Productivity", "image": "images/lessons/day5.png", "desc": "Apply AI to real business problems."},
    ]
    return render_template("learn.html", lessons=lessons)

@app.route("/improve")
def improve_page():
    return render_template("improve.html")

# ── AUTH ROUTES ───────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data, password_hash=generate_password_hash(form.password.data), is_verified=False)
        db.session.add(user)
        try:
            db.session.commit()
            if send_verification_email(user):
                flash("Verification email sent. Please check spam/promotions folder.", "verification")
            else:
                flash("Account created! Email failed — resend from your dashboard.", "warning")
            return redirect(url_for("login"))
        except IntegrityError:
            db.session.rollback()
            flash("Something went wrong. Please try again.", "danger")
    return render_template("register.html", form=form)

@app.route("/verify-email/<token>")
def verify_email(token):
    email = verify_token(token)
    if not email:
        flash("Verification link is invalid or expired.", "danger")
        return redirect(url_for("register"))
    user = User.query.filter_by(email=email).first()
    if not user:
        flash("User not found. Please sign up.", "danger")
        return redirect(url_for("register"))
    if user.is_verified:
        flash("Email already verified! Log in now.", "info")
        return redirect(url_for("login"))
    user.is_verified = True
    db.session.commit()
    flash("✅ Email verified! You can now use all features.", "success")
    return redirect(url_for("login"))

@app.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    if current_user.is_verified:
        flash("Your email is already verified!", "info")
        return redirect(url_for("dashboard"))
    if send_verification_email(current_user):
        flash("Verification email sent. Please check spam/promotions folder.", "verification")
    else:
        flash("Failed to send email. Please try again.", "danger")
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash(f"Welcome back, {user.username}!", "success")
            if not user.is_verified:
                flash("Your account still needs verification. Check spam/promotions folder or resend from your dashboard.", "verification")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out. See you soon!", "info")
    return redirect(url_for("home"))

# ── API & OTHER ROUTES ───────────────────────────────────────────────────────────────

@app.route("/api/improve", methods=["POST"])
@csrf.exempt
def improve_prompt_api():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
        user_prompt = data.get("prompt")
        if not user_prompt:
            return jsonify({"error": "Prompt is required"}), 400
        improved = improve_prompt(user_prompt)
        return jsonify({"improved_prompt": improved})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/prompts")
def api_prompts():
    feed = build_prompt_feed_context(
        category=request.args.get("category", "").strip(),
        search=request.args.get("search", "").strip(),
    )
    html = render_template("partials/prompt_results.html", **feed)
    return jsonify({
        "html": html,
        "prompt_count": feed["prompt_count"],
        "total_prompts": feed["total_prompts"],
        "active_category": feed["active_category"],
        "search": feed["search"],
    })

@app.route("/dashboard")
@login_required
def dashboard():
    my_prompts = Prompt.query.filter_by(user_id=current_user.id).order_by(Prompt.created_at.desc()).all()
    fav_count = Favorite.query.filter_by(user_id=current_user.id).count()
    total_likes = sum(p.likes for p in my_prompts)
    return render_template("dashboard.html", prompts=my_prompts, fav_count=fav_count, total_likes=total_likes)

@app.route("/prompt/<int:prompt_id>")
def prompt_detail(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    is_favorite = False
    if current_user.is_authenticated:
        is_favorite = Favorite.query.filter_by(user_id=current_user.id, prompt_id=prompt_id).first() is not None
    return render_template("prompt_detail.html", prompt=prompt, is_favorite=is_favorite)

@app.route("/create", methods=["GET", "POST"])
@login_required
def create_prompt():
    if not current_user.is_verified:
        flash("Please verify your email before creating prompts.", "warning")
        return redirect(url_for("dashboard"))
    form = PromptForm()
    if form.validate_on_submit():
        prompt = Prompt(title=form.title.data, content=form.content.data, category=form.category.data, user_id=current_user.id)
        db.session.add(prompt)
        db.session.commit()
        flash("Prompt published! 🚀", "success")
        return redirect(url_for("prompt_detail", prompt_id=prompt.id))
    return render_template("create_prompt.html", form=form, edit_mode=False)

@app.route("/edit/<int:prompt_id>", methods=["GET", "POST"])
@login_required
def edit_prompt(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    if prompt.user_id != current_user.id:
        flash("You can only edit your own prompts.", "danger")
        return redirect(url_for("home"))
    if not current_user.is_verified:
        flash("Please verify your email before editing prompts.", "warning")
        return redirect(url_for("dashboard"))
    form = PromptForm(obj=prompt)
    if form.validate_on_submit():
        prompt.title = form.title.data
        prompt.content = form.content.data
        prompt.category = form.category.data
        db.session.commit()
        flash("Prompt updated! ✅", "success")
        return redirect(url_for("prompt_detail", prompt_id=prompt.id))
    return render_template("create_prompt.html", form=form, edit_mode=True, prompt=prompt)

@app.route("/delete/<int:prompt_id>", methods=["POST"])
@login_required
def delete_prompt(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    if prompt.user_id != current_user.id:
        flash("You can only delete your own prompts.", "danger")
        return redirect(url_for("home"))
    db.session.delete(prompt)
    db.session.commit()
    flash("Prompt deleted.", "info")
    return redirect(url_for("dashboard"))

@app.route("/favorites")
@login_required
def favorites():
    fav_records = Favorite.query.filter_by(user_id=current_user.id).all()
    fav_prompts = Prompt.query.filter(Prompt.id.in_([f.prompt_id for f in fav_records])).all()
    return render_template("favorites.html", prompts=fav_prompts)

# ── ADMIN ROUTES ──────────────────────────────────────────────────────────────

@app.route("/admin", endpoint="admin")
@login_required
def admin():
    if current_user.email != app.config["ADMIN_EMAIL"]:
        flash("Admin access only.", "danger")
        return redirect(url_for("dashboard"))
    user_count = User.query.count()
    prompt_count = Prompt.query.count()
    total_likes = db.session.query(func.coalesce(func.sum(Prompt.likes), 0)).scalar() or 0
    total_copies = db.session.query(func.coalesce(func.sum(Prompt.copies), 0)).scalar() or 0
    top_prompts = Prompt.query.order_by(Prompt.likes.desc(), Prompt.copies.desc()).limit(10).all()
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin.html",
        user_count=user_count, prompt_count=prompt_count,
        total_likes=total_likes, total_copies=total_copies,
        top_prompts=top_prompts, users=users, config=app.config)

@app.route("/admin/verify-user/<int:user_id>", methods=["POST"])
@login_required
def admin_verify_user(user_id):
    if current_user.email != app.config["ADMIN_EMAIL"]:
        flash("Admin access only.", "danger")
        return redirect(url_for("dashboard"))
    user = db.session.get(User, user_id)
    if user:
        user.is_verified = True
        db.session.commit()
        flash(f"✅ {user.username} verified successfully.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/delete-user/<int:user_id>", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    if current_user.email != app.config["ADMIN_EMAIL"]:
        flash("Admin access only.", "danger")
        return redirect(url_for("dashboard"))
    user = db.session.get(User, user_id)
    if user and user.email != app.config["ADMIN_EMAIL"]:
        db.session.delete(user)
        db.session.commit()
        flash("User deleted.", "info")
    return redirect(url_for("admin"))

@app.route("/admin/delete-prompt/<int:prompt_id>", methods=["POST"])
@login_required
def admin_delete_prompt(prompt_id):
    if current_user.email != app.config["ADMIN_EMAIL"]:
        flash("Admin access only.", "danger")
        return redirect(url_for("dashboard"))
    prompt = Prompt.query.get_or_404(prompt_id)
    db.session.delete(prompt)
    db.session.commit()
    flash("Prompt deleted.", "info")
    return redirect(url_for("admin"))

# ── AJAX API ──────────────────────────────────────────────────────────────────

@app.route("/api/like/<int:prompt_id>", methods=["POST"])
@csrf.exempt
@login_required
def like_prompt(prompt_id):
    if not current_user.is_verified:
        return jsonify({"error": "Please verify your email to like prompts."}), 403
    prompt = Prompt.query.get_or_404(prompt_id)
    prompt.likes += 1
    db.session.commit()
    return jsonify({"likes": prompt.likes})

@app.route("/api/copy/<int:prompt_id>", methods=["POST"])
@csrf.exempt
def record_copy(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    prompt.copies = (prompt.copies or 0) + 1
    db.session.commit()
    return jsonify({"copies": prompt.copies})

@app.route("/api/favorite/<int:prompt_id>", methods=["POST"])
@csrf.exempt
@login_required
def toggle_favorite(prompt_id):
    if not current_user.is_verified:
        return jsonify({"error": "Please verify your email to save favorites."}), 403
    prompt = Prompt.query.get_or_404(prompt_id)
    existing = Favorite.query.filter_by(user_id=current_user.id, prompt_id=prompt_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"status": "removed"})
    db.session.add(Favorite(user_id=current_user.id, prompt_id=prompt_id))
    db.session.commit()
    return jsonify({"status": "added"})

# ── DB INIT ───────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    if "prompts" in table_names:
        if "copies" not in [col["name"] for col in inspector.get_columns("prompts")]:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE prompts ADD COLUMN copies INTEGER DEFAULT 0"))
    if "users" in table_names:
        if "is_verified" not in [col["name"] for col in inspector.get_columns("users")]:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT 0"))
    seed_database()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")