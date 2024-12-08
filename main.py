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

CHUNK_SIZE = 32768 # 32KB

#### Setup db ####
db = SQLAlchemy()

class AudioFile(db.Model):
    __tablename__ = 'audio_files'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    url_id: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean)

    ACCEPTED_FORMATS = {
        'wav': 'audio/x-wav',
        'mp3': 'audio/mpeg',
        'ogg': 'audio/ogg',
    }

    def __repr__(self) -> str:
        return f'<AudioFile {self.title} {self.filename}>'

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

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get', methods=['GET'])
def get():
    """
    Get a random song from the database
    """
    prev_song = get_value('prev_song', -1)
    print("Previous song:", prev_song)

    # Get a random song that is not the current song and is active
    song = db.session.query(AudioFile).filter_by(active=True).filter(AudioFile.id != prev_song).order_by(func.random()).first()

    if not song:
        return jsonify({'error': 'No songs found'}), 404

    song_file = os.path.join(app.config['UPLOAD_FOLDER'], song.filename)
    if not os.path.exists(song_file):
        # TODO handle more gracefully
        return jsonify({'error': f'Song file not found: {song.filename}'}), 404

    max_available_chunks = os.path.getsize(song_file) // CHUNK_SIZE
    return jsonify({'current_track': song.id, "max_chunks": max_available_chunks})

@app.route('/play', methods=['GET'])
def play():
    """
    Main endpoint for our app. This gets a specified number of chunks of a specific song and returns them to the client
    - current_track: the id of the song to play
    """

    # Get the current track
    current_track = get_value('current_track')
    current_chunk = get_value('current_chunk', 0)

    print(f'Recieved {current_track} at chunk {current_chunk}')

    if current_chunk < 0:
        return jsonify({'error': f'Invalid chunk: {current_chunk}'}), 404

    # Get the song
    song = db.session.query(AudioFile).filter_by(id=current_track).first()
    if not song:
        return jsonify({'error': f'Song not found: {current_track}'}), 404

    # Get the song file
    song_file = os.path.join(app.config['UPLOAD_FOLDER'], song.filename)
    if not os.path.exists(song_file):
        return jsonify({'error': 'Song file not found'}), 404

    # Return the song
    max_available_chunks = os.path.getsize(song_file) // CHUNK_SIZE
    if current_chunk >= max_available_chunks:
        return jsonify({'error': 'End of song'}), 404

    with open(song_file, 'rb') as f:
        f.seek(current_chunk * CHUNK_SIZE)
        data = f.read(CHUNK_SIZE)
    return Response(data, mimetype=AudioFile.ACCEPTED_FORMATS[song.format])

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
def upload_file():
    file = request.files['audio']
    url_id = request.form['url_id']
    format = request.form['format']
    secret = request.form['secret']

    if secret != app.secret_key:
        return jsonify({"error": "Invalid secret"}), 400

    if len(url_id) != 11:
        return jsonify({"error": "Invalid URL ID"}), 400

    if format not in AudioFile.ACCEPTED_FORMATS:
        return jsonify({"error": f"Invalid format: {format}"}), 400

    exist_url_id = AudioFile.query.filter_by(url_id=url_id).first()
    if exist_url_id:
        return jsonify({"error": f"URL ID {url_id} already exists"}), 400

    if file and file.filename is not None:
        file_ext = os.path.splitext(file.filename)[1]
        filename = secure_filename(f"{url_id}{file_ext}")
        print(f"Saving file: {file.filename} to {filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        audio_file = AudioFile(
            title=request.form['title'],
            filename=filename,
            url_id=url_id,
            format=format,
            active=True,
        )
        db.session.add(audio_file)
        db.session.commit()
        return jsonify({"message": "File uploaded successfully", "id": audio_file.id})

    return jsonify({"error": "Invalid file"}), 400

@app.route('/remove', methods=['DELETE'])
def remove_file():
    secret = request.form['secret']
    if secret != app.secret_key:
        return jsonify({"error": "Invalid secret"}), 400

    audio_id = request.form['id']
    audio = AudioFile.query.get(audio_id)
    if audio:
        # Remove file from disk
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], audio.filename))
        # Remove from db
        db.session.delete(audio)
        db.session.commit()
        return jsonify({"message": "File removed successfully"})
    return jsonify({"error": "File not found"}), 404

@app.route('/toggle', methods=['POST'])
def toggle_file():
    secret = request.form['secret']
    if secret != app.secret_key:
        return jsonify({"error": "Invalid secret"}), 400

    audio_id = request.form['id']
    target = request.form['target']
    audio = db.session.query(AudioFile).filter_by(id=audio_id).first()
    if audio:
        audio.active = target
        db.session.commit()
        return jsonify({"message": "File toggled successfully"})
    return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    app.run(debug=True, port=8123)
