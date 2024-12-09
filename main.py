from __future__ import annotations
import os
import sys
from flask import Flask, Response, stream_with_context, render_template
from flask_cors import CORS
from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.exceptions import BadRequest
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey, Float, Boolean
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.sql.expression import func

import dotenv
dotenv.load_dotenv()

#### Setup db ####
db = SQLAlchemy()

class AudioFile(db.Model):
    __tablename__ = 'audio_files'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text)
    url_id: Mapped[str] = mapped_column(Text)
    chunks: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean)

    def __repr__(self) -> str:
        return f'<AudioFile {self.title} {self.url_id}>'

#### App ####
app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', '/uploads/')
app.secret_key = os.getenv('SECRET_KEY')

db.init_app(app)
with app.app_context() as ctx:
    db.create_all()

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def get_metadata_content(title, url_id):
    return f"Now Playing: <a href=\"https://www.youtube.com/watch?v={url_id}\" target=\"_blank\">{title}</a>"

def get_value(key, default: int | None = None):
    value = request.args.get(key)
    if not value:
        if default is None:
            raise BadRequest(f'Missing {key}')
        return default
    try:
        return int(value)
    except ValueError:
        if default is None:
            raise BadRequest(f'Invalid {key}: {value}')
        return default

def get_path(song_url_id: str, i: int):
    return os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(f"{song_url_id}{i}.mp3"))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get', methods=['GET'])
def get():
    """
    Get a random song from the database
    """
    prev_song_id = get_value('prev_song', -1)

    # Get a random song that is not the current song and is active
    songs = db.session.query(AudioFile).filter_by(active=True).filter(AudioFile.id != prev_song_id).order_by(func.random()).all()
    prev_song = db.session.query(AudioFile).filter_by(id=prev_song_id).first()
    if prev_song:
        songs.append(prev_song) # Check this song last

    if not songs:
        return jsonify({'error': 'No songs found'}), 404

    for song in songs:
        missing_chunks = []
        for i in range(song.chunks):
            path = get_path(song.url_id, i)
            if not os.path.exists(path):
                missing_chunks.append(i)
            if os.path.getsize(path) == 0:
                missing_chunks.append(i)
        if missing_chunks:
            print(f"Song {song.id} is missing chunks: {missing_chunks}")
            continue

        max_available_chunks = song.chunks
        return jsonify({'current_track': song.id, "max_chunks": max_available_chunks})

    return jsonify({'error': 'No songs found - all candidates songs are unavailable'}), 404

@app.route('/play', methods=['GET'])
def play():
    """
    Main endpoint for our app. This gets a specified number of chunks of a specific song and returns them to the client
    - current_track: the id of the song to play
    """

    # Get the current track
    current_track = get_value('current_track')
    current_chunk = get_value('current_chunk', 0)

    if current_chunk < 0:
        return jsonify({'error': f'Invalid chunk: {current_chunk}'}), 404

    # Get the song
    song = db.session.query(AudioFile).filter_by(id=current_track).first()
    if not song:
        return jsonify({'error': f'Song not found: {current_track}'}), 404

    path = get_path(song.url_id, current_chunk)
    with open(path, 'rb') as f:
        data = f.read()
    return Response(data, mimetype='audio/mpeg')

@app.route('/metadata', methods=['GET'])
def metadata():
    """
    Get the metadata for the current track
    """
    current_track = get_value('current_track')

    song = db.session.query(AudioFile).filter_by(id=current_track).first()
    if not song:
        return jsonify({'error': f'Song not found: {current_track}'}), 404

    return jsonify({"html": get_metadata_content(song.title, song.url_id)})

@app.route('/upload', methods=['POST'])
def upload():
    secret = request.form['secret']
    if secret != app.secret_key:
        return jsonify({"error": "Invalid secret"}), 400

    if "current_track" in request.form and "current_chunk" in request.form:
        current_track = request.form['current_track']
        try:
            current_track = int(current_track)
        except ValueError:
            return jsonify({"error": f"Invalid current_track ({current_track})"}), 400

        current_chunk = request.form['current_chunk']
        try:
            current_chunk = int(current_chunk)
        except ValueError:
            return jsonify({"error": f"Invalid current_chunk ({current_chunk})"}), 400

        if current_chunk < 0:
            return jsonify({"error": f"Invalid current_chunk ({current_chunk})"}), 400

        song = db.session.query(AudioFile).filter_by(id=current_track).first()
        if not song:
            return jsonify({"error": f"Song not found: {current_track}"}), 404

        if current_chunk >= song.chunks:
            return jsonify({"error": f"Invalid current_chunk ({current_chunk}), max = {song.chunks}"}), 400

        file = request.files['file']
        if file is None:
            return jsonify({"error": "No file uploaded"}), 400

        file.save(get_path(song.url_id, current_chunk))
        return jsonify({"message": "File uploaded successfully"})

    url_id = request.form['url_id']
    title = request.form['title']
    chunks = request.form['chunks']

    try:
        chunks = int(chunks)
    except ValueError:
        return jsonify({"error": f"Invalid chunk count: {chunks}"}), 400

    if chunks < 1:
        return jsonify({"error": f"Invalid chunk count: {chunks}"}), 400

    if len(url_id) != 11:
        return jsonify({"error": f"Invalid URL ID: {url_id}"}), 400

    exist_url_id = db.session.query(AudioFile).filter_by(url_id=url_id).first()
    if exist_url_id:
        return jsonify({"error": f"URL ID {url_id} already exists"}), 400

    entry = {
        "title": title,
        "chunks": chunks,
        "url_id": url_id,
        "active": True
    }

    audio_file = AudioFile(**entry)
    db.session.add(audio_file)
    db.session.commit()
    return jsonify({"message": "Entry made successfully", "id": audio_file.id})


@app.route('/remove', methods=['DELETE'])
def remove_file():
    secret = request.form['secret']
    if secret != app.secret_key:
        return jsonify({"error": "Invalid secret"}), 400

    audio_id = request.form['id']
    audio = AudioFile.query.get(audio_id)
    if not audio:
        return jsonify({"error": "File not found"}), 404

    # Remove file from disk
    files = [x for x in os.listdir(app.config['UPLOAD_FOLDER']) if x.startswith(audio.url_id)]
    for file in files:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], file))
    # Remove from db
    db.session.delete(audio)
    db.session.commit()
    return jsonify({"message": "File removed successfully"})

@app.route('/toggle', methods=['POST'])
def toggle_file():
    secret = request.form['secret']
    if secret != app.secret_key:
        return jsonify({"error": "Invalid secret"}), 400

    audio_id = request.form['id']
    target = request.form['target']
    assert isinstance(target, bool) #type checking
    audio = db.session.query(AudioFile).filter_by(id=audio_id).first()
    if audio:
        audio.active = target
        db.session.commit()
        return jsonify({"message": "File toggled successfully"})
    return jsonify({"error": "File not found"}), 404

@app.route('/listdir', methods=['GET'])
def list_files():
    secret = request.form['secret']
    if secret != app.secret_key:
        return jsonify({"error": "Invalid secret"}), 400

    os.system(f"ls -l {app.config['UPLOAD_FOLDER']}")
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return jsonify(files)

if __name__ == '__main__':
    app.run(debug=True, port=8123)
