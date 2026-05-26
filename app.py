import os
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect, text, func
from sqlalchemy.exc import IntegrityError
from itsdangerous import URLSafeTimedSerializer
from models import db, User, Prompt, Favorite
from forms import RegisterForm, LoginForm, PromptForm, CATEGORIES
from dotenv import load_dotenv
import threading
load_dotenv()

# ── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback-dev-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///prompts.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["ADMIN_EMAIL"] = os.environ.get("ADMIN_EMAIL", "admin@rohithbuilds.com")

# ── Flask-Mail Configuration ──────────────────────────────────────────────────
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = str(os.environ.get("MAIL_USE_TLS", "True")).lower() == "true"
app.config["MAIL_USE_SSL"] = str(os.environ.get("MAIL_USE_SSL", "False")).lower() == "true"
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER") or app.config["MAIL_USERNAME"]

# Ensure a sender is always available for SMTP providers like Gmail.
if not app.config["MAIL_DEFAULT_SENDER"] and app.config["MAIL_USERNAME"]:
    app.config["MAIL_DEFAULT_SENDER"] = app.config["MAIL_USERNAME"]

mail = Mail(app)
csrf = CSRFProtect(app)

db.init_app(app)

# Make csrf_token() available in all templates
@app.context_processor
def inject_csrf_token():
    is_admin = (
        current_user.is_authenticated
        and getattr(current_user, "email", None) == app.config["ADMIN_EMAIL"]
    )
    return dict(csrf_token=generate_csrf, is_admin=is_admin)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── Email Verification Helpers ────────────────────────────────────────────────
def generate_verification_token(email):
    """Generate a verification token for email confirmation."""
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    return serializer.dumps(email, salt="email-confirm-salt")


def verify_token(token, expiration=3600):
    """Verify a token and return the email if valid. Tokens expire after 1 hour."""
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    try:
        email = serializer.loads(token, salt="email-confirm-salt", max_age=expiration)
        return email
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
        msg = Message(
            subject="Verify Your Email - RohithBuilds",
            recipients=[user.email],
            html=html_content
        )

        # Pass app instance AND message — keeps context alive
        def send_async(flask_app, message):
            with flask_app.app_context():
                try:
                    mail.send(message)
                    print(f"✅ Email sent to {message.recipients}")
                except Exception as e:
                    print(f"❌ Mail error: {e}")

        t = threading.Thread(target=send_async, args=(app, msg))
        t.daemon = True
        t.start()
        return True  # returns instantly, never blocks

    except Exception as e:
        print(f"❌ Error building email: {e}")
        return False


    
    def send_async(app, message):
        with app.app_context():
            try:
                mail.send(message)
                print(f"✅ Verification email sent to {message.recipients}")
            except Exception as e:
                print(f"❌ Email failed: {e}")

    thread = threading.Thread(target=send_async, args=(app, msg))
    thread.daemon = True
    thread.start()
    return True  # Always returns immediately

# ── Seed data ─────────────────────────────────────────────────────────────────
SEED_PROMPTS = [
    {
        "title": "Ultimate Code Reviewer",
        "content": (
            "You are an expert senior software engineer conducting a thorough code review. "
            "Analyze the following code for:\n"
            "1. Bugs and logical errors\n"
            "2. Security vulnerabilities\n"
            "3. Performance optimizations\n"
            "4. Code style and best practices\n"
            "5. Missing edge cases\n\n"
            "Provide specific, actionable feedback with code examples where applicable. "
            "Be concise but thorough. Start with critical issues first.\n\n"
            "Code to review:\n[PASTE YOUR CODE HERE]"
        ),
        "category": "Coding",
    },
    {
        "title": "Viral Twitter Thread Generator",
        "content": (
            "You are a viral social media strategist who has written dozens of viral Twitter threads. "
            "Create a compelling Twitter thread about [TOPIC] that:\n"
            "- Hooks readers in the first tweet\n"
            "- Uses short punchy sentences\n"
            "- Includes surprising facts or insights\n"
            "- Has a strong call to action at the end\n"
            "- Is formatted as Tweet 1/, Tweet 2/, etc.\n\n"
            "Write 8-12 tweets. Make it shareable and valuable."
        ),
        "category": "Marketing",
    },
    {
        "title": "Startup Idea Validator",
        "content": (
            "Act as a seasoned startup mentor who has evaluated hundreds of business ideas. "
            "Evaluate this startup idea: [YOUR IDEA]\n\n"
            "Provide a structured analysis:\n"
            "✅ Strengths (what's working)\n"
            "❌ Weaknesses (critical gaps)\n"
            "🎯 Target market size estimate\n"
            "💰 Potential monetization models\n"
            "🚀 MVP suggestion (build in 2 weeks)\n"
            "⚠️ Top 3 risks to watch\n"
            "📊 Overall score: X/10\n\n"
            "Be brutally honest but constructive."
        ),
        "category": "Business",
    },
    {
        "title": "Essay Writing Assistant",
        "content": (
            "You are an expert academic writer and editor. Help me write a compelling essay on: [TOPIC]\n\n"
            "Requirements:\n"
            "- Word count: [SPECIFY]\n"
            "- Audience: [SPECIFY]\n"
            "- Tone: [formal/casual/persuasive]\n\n"
            "Structure:\n"
            "1. Attention-grabbing introduction with a hook\n"
            "2. Clear thesis statement\n"
            "3. 3 well-argued body paragraphs with evidence\n"
            "4. Counterargument addressed\n"
            "5. Strong conclusion with call to action\n\n"
            "Use varied sentence structure and active voice throughout."
        ),
        "category": "Writing",
    },
    {
        "title": "Personal Tutor - Any Subject",
        "content": (
            "You are a world-class tutor who adapts to any learning style. "
            "Teach me [TOPIC/CONCEPT] as if I am a [BEGINNER/INTERMEDIATE/EXPERT].\n\n"
            "Your teaching approach:\n"
            "- Start with a simple real-world analogy\n"
            "- Break into digestible steps\n"
            "- Give 2-3 practical examples\n"
            "- Include a quick exercise to test understanding\n"
            "- Anticipate my top 3 likely questions and answer them\n\n"
            "Make learning engaging and memorable, not dry and textbook-like."
        ),
        "category": "Education",
    },
    {
        "title": "Research Paper Summarizer",
        "content": (
            "You are an expert research analyst. Summarize the following research paper "
            "into a clear, accessible breakdown:\n\n"
            "[PASTE PAPER ABSTRACT OR FULL TEXT]\n\n"
            "Provide:\n"
            "📌 TL;DR (2 sentences max)\n"
            "🎯 Main research question\n"
            "🔬 Methodology used\n"
            "📊 Key findings (bullet points)\n"
            "💡 Real-world implications\n"
            "⚠️ Limitations acknowledged\n"
            "🔗 How it connects to related work\n\n"
            "Write for a smart non-expert audience."
        ),
        "category": "Research",
    },
    {
        "title": "Morning Productivity Planner",
        "content": (
            "You are a productivity coach. Based on my goals below, create my optimal daily schedule.\n\n"
            "My goals: [LIST YOUR GOALS]\n"
            "Available hours: [HOURS PER DAY]\n"
            "Energy peaks: [MORNING/AFTERNOON/EVENING]\n\n"
            "Create:\n"
            "⏰ Hour-by-hour schedule\n"
            "🎯 Top 3 priorities for today (MIT - Most Important Tasks)\n"
            "⚡ Energy management tips\n"
            "🚫 What to say NO to today\n"
            "📝 End-of-day review checklist\n\n"
            "Make it realistic and sustainable, not a superhuman schedule."
        ),
        "category": "Productivity",
    },
    {
        "title": "Short Story Generator",
        "content": (
            "You are an award-winning fiction writer. Write a captivating short story with these elements:\n\n"
            "Genre: [GENRE]\n"
            "Setting: [TIME AND PLACE]\n"
            "Main character: [BRIEF DESCRIPTION]\n"
            "Core conflict: [THE CENTRAL PROBLEM]\n"
            "Mood: [TENSE/MYSTERIOUS/HOPEFUL/etc.]\n\n"
            "Story requirements:\n"
            "- 600-800 words\n"
            "- Strong opening hook (first line must grab attention)\n"
            "- Show don't tell\n"
            "- Unexpected twist or memorable ending\n"
            "- Rich sensory details\n\n"
            "Make every word count."
        ),
        "category": "Creative",
    },
]


def seed_database():
    """Seed the database with sample data if empty."""
    if User.query.first():
        return  # Already seeded

    # Create a seed user
    seed_user = User(
         username="rohithbuilds",
        email="admin@rohithbuilds.com",
        password_hash=generate_password_hash("admin123"),
    )
    db.session.add(seed_user)
    db.session.flush()  # Get the ID

    # Add seed prompts
    for p in SEED_PROMPTS:
        prompt = Prompt(
            title=p["title"],
            content=p["content"],
            category=p["category"],
            likes=0,
            user_id=seed_user.id,
        )
        db.session.add(prompt)

    db.session.commit()
    print("✅ Database seeded successfully.")


# ── Routes: Auth ──────────────────────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = RegisterForm()
    if form.validate_on_submit():
        hashed_pw = generate_password_hash(form.password.data)
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=hashed_pw,
            is_verified=False,
        )
        db.session.add(user)
        try:
            db.session.commit()
            # Send verification email
            if send_verification_email(user):
                flash(
                    f"Welcome to PromptVault, {user.username.title()}! 🎉 Check {user.email} for your verification link and come back to start creating prompts.",
                    "success"
                )
            else:
                flash(
                    "Your account is ready! We couldn't send the email right now, but you can resend verification from your dashboard.",
                    "warning"
                )
            return redirect(url_for("login"))
        except IntegrityError:
            db.session.rollback()
            flash("Something went wrong. Please try again.", "danger")
    return render_template("register.html", form=form)


@app.route("/verify-email/<token>")
def verify_email(token):
    """Verify user email via token link."""
    email = verify_token(token)
    if not email:
        flash("The verification link is invalid or has expired. Please sign up again.", "danger")
        return redirect(url_for("register"))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash("User not found. Please sign up.", "danger")
        return redirect(url_for("register"))
    
    if user.is_verified:
        flash("Your email is already verified! You can log in now.", "info")
        return redirect(url_for("login"))
    
    user.is_verified = True
    db.session.commit()
    flash("✅ Email verified successfully! You can now log in and use all features.", "success")
    return redirect(url_for("login"))


@app.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    """Resend verification email if user is not verified."""
    if current_user.is_verified:
        flash("Your email is already verified!", "info")
        return redirect(url_for("dashboard"))
    
    if send_verification_email(current_user):
        flash(f"Verification email sent to {current_user.email}", "success")
    else:
        flash("Failed to send verification email. Please try again.", "danger")
    
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
            next_page = request.args.get("next")
            flash(f"Welcome back, {user.username}! 👋", "success")
            return redirect(next_page or url_for("dashboard"))
        flash("Invalid email or password. Please try again.", "danger")
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You've been logged out. See you soon!", "info")
    return redirect(url_for("index"))


# ── Routes: Pages ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    category = request.args.get("category", "")
    search = request.args.get("search", "")

    query = Prompt.query
    if category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(
            db.or_(
                Prompt.title.ilike(f"%{search}%"),
                Prompt.content.ilike(f"%{search}%"),
            )
        )

    prompts = query.order_by(Prompt.created_at.desc()).all()
    categories = [c[0] for c in CATEGORIES]

    # Get user favorites for heart button state
    user_favorites = set()
    if current_user.is_authenticated:
        favs = Favorite.query.filter_by(user_id=current_user.id).all()
        user_favorites = {f.prompt_id for f in favs}

    return render_template(
        "index.html",
        prompts=prompts,
        categories=categories,
        active_category=category,
        search=search,
        user_favorites=user_favorites,
    )


@app.route("/dashboard")
@login_required
def dashboard():
    my_prompts = Prompt.query.filter_by(user_id=current_user.id).order_by(Prompt.created_at.desc()).all()
    fav_count = Favorite.query.filter_by(user_id=current_user.id).count()
    total_likes = sum(p.likes for p in my_prompts)
    return render_template(
        "dashboard.html",
        prompts=my_prompts,
        fav_count=fav_count,
        total_likes=total_likes,
    )


@app.route("/prompt/<int:prompt_id>")
def prompt_detail(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    is_favorite = False
    if current_user.is_authenticated:
        is_favorite = Favorite.query.filter_by(
            user_id=current_user.id, prompt_id=prompt_id
        ).first() is not None
    return render_template("prompt_detail.html", prompt=prompt, is_favorite=is_favorite)


@app.route("/create", methods=["GET", "POST"])
@login_required
def create_prompt():
    if not current_user.is_verified:
        flash("Please verify your email before creating prompts. Check your inbox for the verification link.", "warning")
        return redirect(url_for("dashboard"))
    
    form = PromptForm()
    if form.validate_on_submit():
        prompt = Prompt(
            title=form.title.data,
            content=form.content.data,
            category=form.category.data,
            user_id=current_user.id,
        )
        db.session.add(prompt)
        db.session.commit()
        flash("Prompt published successfully! 🚀", "success")
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
        flash("Prompt updated successfully! ✅", "success")
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

    return render_template(
        "admin.html",
        user_count=user_count,
        prompt_count=prompt_count,
        total_likes=total_likes,
        total_copies=total_copies,
        top_prompts=top_prompts,
    )


@app.route("/favorites")
@login_required
def favorites():
    fav_records = Favorite.query.filter_by(user_id=current_user.id).all()
    prompt_ids = [f.prompt_id for f in fav_records]
    fav_prompts = Prompt.query.filter(Prompt.id.in_(prompt_ids)).all()
    return render_template("favorites.html", prompts=fav_prompts)


# ── Routes: AJAX API ──────────────────────────────────────────────────────────
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
    else:
        fav = Favorite(user_id=current_user.id, prompt_id=prompt_id)
        db.session.add(fav)
        db.session.commit()
        return jsonify({"status": "added"})


# ── Initialize DB on startup ───────────────────────────────────────────────
with app.app_context():
    db.create_all()
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    if "prompts" in table_names:
        prompt_columns = [col["name"] for col in inspector.get_columns("prompts")]
        if "copies" not in prompt_columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE prompts ADD COLUMN copies INTEGER DEFAULT 0"))
    if "users" in table_names:
        user_columns = [col["name"] for col in inspector.get_columns("users")]
        if "is_verified" not in user_columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT 0"))
    seed_database()

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
    )
