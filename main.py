from __future__ import annotations
import os
import sys
from flask import Flask, Response, stream_with_context, render_template
from flask_cors import CORS
from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey, Float, Boolean
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.sql.expression import func

import dotenv
dotenv.load_dotenv()

CHUNK_SIZE = 4096

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
app.config['UPLOAD_FOLDER'] = '/uploads/'
app.secret_key = os.getenv('SECRET_KEY')

db.init_app(app)
with app.app_context() as ctx:
    db.create_all()

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def get_metadata_content(title, url_id):
    return f"Now Playing: <a href=\"https://www.youtube.com/watch?v={url_id}\" target=\"_blank\">{title}</a>"

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get', methods=['GET'])
def get():
    """
    Get a random song from the database
    """
    song = db.session.query(AudioFile).filter_by(active=True).order_by(func.random()).first()

    if not song:
        return jsonify({'error': 'No songs found'}), 404

    return jsonify({'current_track': song.id})

@app.route('/play?current_track=<int:current_track>&current_chunk=<int:current_chunk>', methods=['GET'])
def play(current_track, current_chunk):
    """
    Main endpoint for our app. This gets a specified number of chunks of a specific song and returns them to the client
    - current_track: the id of the song to play
    - current_chunk: the current chunk of the song to play
    """

    if current_chunk < 0:
        return jsonify({'error': f'Invalid chunk: {current_chunk}'}), 400

    # Get the song
    song = db.session.query(AudioFile).filter_by(id=current_track).first()
    if not song:
        return jsonify({'error': f'Song not found: {current_track}'}), 404

    # Get the song file
    song_file = os.path.join(app.config['UPLOAD_FOLDER'], song.filename)
    if not os.path.exists(song_file):
        return jsonify({'error': 'Song file not found'}), 404

    # Get the song format
    format = song.format

    max_available_chunks = os.path.getsize(song_file) // CHUNK_SIZE
    if current_chunk >= max_available_chunks:
        return jsonify({'error': 'End of song'}), 404


    # Return the song
    with open(song_file, 'rb') as f:
        f.seek(current_chunk * CHUNK_SIZE)
        chunk = f.read(CHUNK_SIZE)
    return Response(chunk, mimetype=AudioFile.ACCEPTED_FORMATS[format])

if __name__ == '__main__':
    app.run(debug=True, port=8123)
