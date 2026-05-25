import os
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from models import db, User, Prompt, Favorite
from forms import RegisterForm, LoginForm, PromptForm, CATEGORIES

# ── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback-dev-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///prompts.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
csrf = CSRFProtect(app)

# Make csrf_token() available in all templates
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


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
        username="promptvault",
        email="admin@promptvault.ai",
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
        )
        db.session.add(user)
        try:
            db.session.commit()
            login_user(user)
            flash("Welcome to PromptVault! 🎉", "success")
            return redirect(url_for("dashboard"))
        except IntegrityError:
            db.session.rollback()
            flash("Something went wrong. Please try again.", "danger")
    return render_template("register.html", form=form)


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
    prompt = Prompt.query.get_or_404(prompt_id)
    prompt.likes += 1
    db.session.commit()
    return jsonify({"likes": prompt.likes})


@app.route("/api/favorite/<int:prompt_id>", methods=["POST"])
@csrf.exempt
@login_required
def toggle_favorite(prompt_id):
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


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_database()
    app.run(debug=True)