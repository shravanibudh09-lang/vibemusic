"""
Vibe Music - Web Music Player
Diploma Project - 3rd Year

Stack:
    Frontend : HTML, CSS, JavaScript (templates/, static/)
    Backend  : Python (Flask)
    Database : SQLite (SQL database, file-based)

Pages:
    /            Home - upload, now playing (with album art), full playlist
    /artists     Grid of artists ("albums")
    /artist/<n>  Songs by one artist
    /favorites   Favorited songs
    /login       Login page
    /register    Create account page

Setup:
    pip install flask

Run:
    python app.py

Then open http://127.0.0.1:5000 in your browser.
"""

import os
import sqlite3
from functools import wraps
from flask import (
    Flask, request, jsonify, render_template, send_from_directory,
    session, redirect, url_for, flash
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# On Render, attach a persistent disk mounted at /var/data (see deploy steps).
# Locally, this env var is unset, so everything falls back to the project folder.
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)

UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
COVER_FOLDER = os.path.join(UPLOAD_FOLDER, "covers")
DATABASE = os.path.join(DATA_DIR, "vibemusic.db")
ALLOWED_EXTENSIONS = {"mp3", "wav", "ogg"}
ALLOWED_COVER_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["COVER_FOLDER"] = COVER_FOLDER
# Used to sign the session cookie. Change this to a random value for real deployments.
app.secret_key = "vibemusic-dev-secret-change-me"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COVER_FOLDER, exist_ok=True)


# ---------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            artist TEXT DEFAULT 'Unknown Artist',
            filename TEXT NOT NULL,
            cover TEXT,
            is_favorite INTEGER DEFAULT 0,
            added_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Lightweight migration for DBs created before cover/is_favorite existed.
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(songs)")}
    if "cover" not in existing_cols:
        conn.execute("ALTER TABLE songs ADD COLUMN cover TEXT")
    if "is_favorite" not in existing_cols:
        conn.execute("ALTER TABLE songs ADD COLUMN is_favorite INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_cover(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_COVER_EXTENSIONS


# ---------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Login required"}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    if not username or not password:
        return render_template("register.html", error="Username and password are required.")
    if password != confirm:
        return render_template("register.html", error="Passwords do not match.")
    if len(password) < 4:
        return render_template("register.html", error="Password must be at least 4 characters.")

    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        return render_template("register.html", error="That username is already taken.")

    conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return redirect(url_for("index"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Incorrect username or password.")

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    next_url = request.args.get("next") or url_for("index")
    return redirect(next_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/artists")
@login_required
def artists_page():
    return render_template("artists.html")


@app.route("/artist/<artist_name>")
@login_required
def artist_page(artist_name):
    return render_template("artist.html", artist_name=artist_name)


@app.route("/favorites")
@login_required
def favorites_page():
    return render_template("favorites.html")


# ---------------------------------------------------------------
# API: list songs (optionally filtered by artist or favorite)
# ---------------------------------------------------------------
@app.route("/api/songs", methods=["GET"])
@login_required
def get_songs():
    artist = request.args.get("artist")
    favorite_only = request.args.get("favorite")

    query = "SELECT * FROM songs"
    conditions = []
    params = []

    if artist:
        conditions.append("artist = ?")
        params.append(artist)
    if favorite_only:
        conditions.append("is_favorite = 1")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY added_on DESC"

    conn = get_db()
    songs = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(song) for song in songs])


# ---------------------------------------------------------------
# API: list distinct artists with song count + a cover thumbnail
# ---------------------------------------------------------------
@app.route("/api/artists", methods=["GET"])
@login_required
def get_artists():
    conn = get_db()
    rows = conn.execute("SELECT * FROM songs ORDER BY added_on DESC").fetchall()
    conn.close()

    artists = {}
    for song in rows:
        name = song["artist"]
        if name not in artists:
            artists[name] = {"artist": name, "count": 0, "cover": None}
        artists[name]["count"] += 1
        if artists[name]["cover"] is None and song["cover"]:
            artists[name]["cover"] = song["cover"]

    return jsonify(sorted(artists.values(), key=lambda a: a["artist"].lower()))


# ---------------------------------------------------------------
# API: upload a new song (with optional cover image)
# ---------------------------------------------------------------
@app.route("/api/upload", methods=["POST"])
@login_required
def upload_song():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    title = request.form.get("title", "").strip()
    artist = request.form.get("artist", "").strip() or "Unknown Artist"

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    # Avoid overwriting a file with the same name
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(filepath):
        filename = f"{base}_{counter}{ext}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        counter += 1

    file.save(filepath)

    if not title:
        title = base

    # Optional cover image
    cover_filename = None
    cover_file = request.files.get("cover")
    if cover_file and cover_file.filename:
        if allowed_cover(cover_file.filename):
            cover_filename = secure_filename(cover_file.filename)
            cover_path = os.path.join(app.config["COVER_FOLDER"], cover_filename)
            cbase, cext = os.path.splitext(cover_filename)
            ccounter = 1
            while os.path.exists(cover_path):
                cover_filename = f"{cbase}_{ccounter}{cext}"
                cover_path = os.path.join(app.config["COVER_FOLDER"], cover_filename)
                ccounter += 1
            cover_file.save(cover_path)
        else:
            return jsonify({"error": "Unsupported cover image type"}), 400

    conn = get_db()
    conn.execute(
        "INSERT INTO songs (title, artist, filename, cover) VALUES (?, ?, ?, ?)",
        (title, artist, filename, cover_filename),
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Song uploaded successfully"}), 201


# ---------------------------------------------------------------
# API: toggle favorite status
# ---------------------------------------------------------------
@app.route("/api/songs/<int:song_id>/favorite", methods=["POST"])
@login_required
def toggle_favorite(song_id):
    conn = get_db()
    song = conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()

    if song is None:
        conn.close()
        return jsonify({"error": "Song not found"}), 404

    new_state = 0 if song["is_favorite"] else 1
    conn.execute("UPDATE songs SET is_favorite = ? WHERE id = ?", (new_state, song_id))
    conn.commit()
    conn.close()

    return jsonify({"id": song_id, "is_favorite": new_state})


# ---------------------------------------------------------------
# API: delete a song
# ---------------------------------------------------------------
@app.route("/api/songs/<int:song_id>", methods=["DELETE"])
@login_required
def delete_song(song_id):
    conn = get_db()
    song = conn.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()

    if song is None:
        conn.close()
        return jsonify({"error": "Song not found"}), 404

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], song["filename"])
    if os.path.exists(filepath):
        os.remove(filepath)

    if song["cover"]:
        cover_path = os.path.join(app.config["COVER_FOLDER"], song["cover"])
        if os.path.exists(cover_path):
            os.remove(cover_path)

    conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
    conn.commit()
    conn.close()

    return jsonify({"message": "Song deleted"})


# ---------------------------------------------------------------
# Serve uploaded audio / cover files
# ---------------------------------------------------------------
@app.route("/static/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


init_db()

if __name__ == "_main_":
  port = int(os.environ.get("PORT", 5000))
debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
app.run(debug=debug, host="0.0.0.0", port=port)
