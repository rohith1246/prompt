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
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback-dev-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///prompts.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["ADMIN_EMAIL"] = os.environ.get("ADMIN_EMAIL", "admin@rohithbuilds.com")

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
        html_content = render_template("email/verify_email.html", username=user.username.title(), verify_url=verify_url)
        resend.Emails.send({
            "from": "RohithBuilds <onboarding@resend.dev>",
            "to": user.email,
            "subject": "Verify Your Email - RohithBuilds",
            "html": html_content
        })
        print(f"✅ Email sent to {user.email} via Resend")
        return True
    except Exception as e:
        print(f"❌ Resend error: {e}")
        return False

SEED_PROMPTS = [
    {"title": "Ultimate Code Reviewer", "content": "You are an expert senior software engineer conducting a thorough code review. Analyze the following code for:\n1. Bugs and logical errors\n2. Security vulnerabilities\n3. Performance optimizations\n4. Code style and best practices\n5. Missing edge cases\n\nProvide specific, actionable feedback with code examples where applicable.\n\nCode to review:\n[PASTE YOUR CODE HERE]", "category": "Coding"},
    {"title": "Viral Twitter Thread Generator", "content": "You are a viral social media strategist. Create a compelling Twitter thread about [TOPIC] that:\n- Hooks readers in the first tweet\n- Uses short punchy sentences\n- Includes surprising facts or insights\n- Has a strong call to action at the end\n- Is formatted as Tweet 1/, Tweet 2/, etc.\n\nWrite 8-12 tweets. Make it shareable and valuable.", "category": "Marketing"},
    {"title": "Startup Idea Validator", "content": "Act as a seasoned startup mentor. Evaluate this startup idea: [YOUR IDEA]\n\nProvide:\n✅ Strengths\n❌ Weaknesses\n🎯 Target market size\n💰 Monetization models\n🚀 MVP suggestion\n⚠️ Top 3 risks\n📊 Overall score: X/10", "category": "Business"},
    {"title": "Essay Writing Assistant", "content": "You are an expert academic writer. Help me write a compelling essay on: [TOPIC]\n\nRequirements:\n- Word count: [SPECIFY]\n- Audience: [SPECIFY]\n- Tone: [formal/casual/persuasive]\n\nStructure:\n1. Attention-grabbing introduction\n2. Clear thesis statement\n3. 3 well-argued body paragraphs\n4. Counterargument addressed\n5. Strong conclusion", "category": "Writing"},
    {"title": "Personal Tutor - Any Subject", "content": "You are a world-class tutor. Teach me [TOPIC/CONCEPT] as if I am a [BEGINNER/INTERMEDIATE/EXPERT].\n\nApproach:\n- Start with a real-world analogy\n- Break into digestible steps\n- Give 2-3 practical examples\n- Include a quick exercise\n- Answer my top 3 likely questions", "category": "Education"},
    {"title": "Research Paper Summarizer", "content": "You are an expert research analyst. Summarize this paper:\n[PASTE PAPER HERE]\n\nProvide:\n📌 TL;DR (2 sentences)\n🎯 Main research question\n🔬 Methodology\n📊 Key findings\n💡 Real-world implications\n⚠️ Limitations", "category": "Research"},
    {"title": "Morning Productivity Planner", "content": "You are a productivity coach. Create my optimal daily schedule.\n\nMy goals: [LIST YOUR GOALS]\nAvailable hours: [HOURS PER DAY]\nEnergy peaks: [MORNING/AFTERNOON/EVENING]\n\nCreate:\n⏰ Hour-by-hour schedule\n🎯 Top 3 priorities (MIT)\n⚡ Energy management tips\n🚫 What to say NO to today", "category": "Productivity"},
    {"title": "Short Story Generator", "content": "You are an award-winning fiction writer. Write a short story:\n\nGenre: [GENRE]\nSetting: [TIME AND PLACE]\nMain character: [BRIEF DESCRIPTION]\nCore conflict: [THE CENTRAL PROBLEM]\nMood: [TENSE/MYSTERIOUS/HOPEFUL]\n\nRequirements:\n- 600-800 words\n- Strong opening hook\n- Unexpected twist or memorable ending", "category": "Creative"},
]

def seed_database():
    if User.query.first():
        return
    seed_user = User(username="rohithbuilds", email="admin@rohithbuilds.com", password_hash=generate_password_hash("admin123"), is_verified=True)
    db.session.add(seed_user)
    db.session.flush()
    for p in SEED_PROMPTS:
        db.session.add(Prompt(title=p["title"], content=p["content"], category=p["category"], likes=0, user_id=seed_user.id))
    db.session.commit()
    print("✅ Database seeded successfully.")

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data, password_hash=generate_password_hash(form.password.data), is_verified=False)
        db.session.add(user)
        try:
            db.session.commit()
            if send_verification_email(user):
                flash(f"Welcome {user.username.title()}! 🎉 Check {user.email} for your verification link.", "success")
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
        flash(f"Verification email sent to {current_user.email}", "success")
    else:
        flash("Failed to send email. Please try again.", "danger")
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash(f"Welcome back, {user.username}! 👋", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out. See you soon!", "info")
    return redirect(url_for("index"))

@app.route("/")
def index():
    category = request.args.get("category", "")
    search = request.args.get("search", "")
    query = Prompt.query
    if category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(db.or_(Prompt.title.ilike(f"%{search}%"), Prompt.content.ilike(f"%{search}%")))
    prompts = query.order_by(Prompt.created_at.desc()).all()
    categories = [c[0] for c in CATEGORIES]
    user_favorites = set()
    if current_user.is_authenticated:
        user_favorites = {f.prompt_id for f in Favorite.query.filter_by(user_id=current_user.id).all()}
    return render_template("index.html", prompts=prompts, categories=categories, active_category=category, search=search, user_favorites=user_favorites)

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
        return redirect(url_for("index"))
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
        return redirect(url_for("index"))
    db.session.delete(prompt)
    db.session.commit()
    flash("Prompt deleted.", "info")
    return redirect(url_for("dashboard"))

@app.route("/admin", endpoint="admin")
@login_required
def admin():
    if not (current_user.is_authenticated and getattr(current_user, "email", None) == app.config["ADMIN_EMAIL"]):
        flash("Admin access only.", "danger")
        return redirect(url_for("dashboard"))
    user_count = User.query.count()
    prompt_count = Prompt.query.count()
    total_likes = db.session.query(func.coalesce(func.sum(Prompt.likes), 0)).scalar() or 0
    total_copies = db.session.query(func.coalesce(func.sum(Prompt.copies), 0)).scalar() or 0
    top_prompts = Prompt.query.order_by(Prompt.likes.desc(), Prompt.copies.desc()).limit(10).all()
    return render_template("admin.html", user_count=user_count, prompt_count=prompt_count, total_likes=total_likes, total_copies=total_copies, top_prompts=top_prompts)

@app.route("/favorites")
@login_required
def favorites():
    fav_records = Favorite.query.filter_by(user_id=current_user.id).all()
    fav_prompts = Prompt.query.filter(Prompt.id.in_([f.prompt_id for f in fav_records])).all()
    return render_template("favorites.html", prompts=fav_prompts)

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
