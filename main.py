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
import redis
import random
import time
import uuid
import traceback
import threading

import dotenv
dotenv.load_dotenv()

# Chunk size for audio processing
CHUNK = 1024

CHECK_SKIP_INTERVAL = 100

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

redis_host = os.getenv('REDISHOST', 'localhost')
redis_port = int(os.getenv('REDIS_PORT', 6379))
redis_password = os.getenv('REDIS_PASSWORD', None)

r = redis.Redis(host=redis_host, port=redis_port, password=redis_password, decode_responses=True)

def get_metadata_content(title, url_id):
    return f"Now Playing: <a href=\"https://www.youtube.com/watch?v={url_id}\" target=\"_blank\">{title}</a>"

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())  # Generate a unique user_id
    return render_template('index.html')

@app.route('/play', methods=['GET'])
def play_random():
    format = "ogg"
    user_id = session['user_id']

    def stream(paths):
        check_skip = CHECK_SKIP_INTERVAL
        while True:
            path, id, title = random.choice(paths)
            r.set(f"audio_{user_id}", get_metadata_content(title, id))
            print(f"User: {user_id} is playing {id}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], path)
            try:
                with open(file_path, "rb") as fwav:
                    data = fwav.read(CHUNK)
                    while data:
                        yield data
                        data = fwav.read(CHUNK)
                        check_skip -= 1
                        if check_skip <= 0:
                            check_skip = CHECK_SKIP_INTERVAL
                            if r.get(f"audio_{user_id}") is None:
                                print(f"User: {user_id} skipped playing {id}")
                                break
            except Exception as e:
                print(e)
                print(traceback.format_exc())
                time.sleep(1)
                continue # Loops back to the beginning of the while loop to play another song

            print(f"User: {user_id} finished getting data for {id}")
            while True:
                metadata = r.get(f"audio_{user_id}")
                # Play another audio if metadata is None or metadata is changed (the latter should not happen but just in case)
                if metadata is None or metadata != get_metadata_content(title, id):
                    print(f"User: {user_id} stopped playing {id}")
                    break
                time.sleep(0.5)

    audios = AudioFile.query.filter_by(active=True, format=format).all()
    if not audios:
        return jsonify({"error": "File not found"}), 404
    paths = [(audio.filename, audio.id, audio.title) for audio in audios]
    return Response(stream(paths), mimetype=AudioFile.ACCEPTED_FORMATS[format])

@app.route('/metadata')
def get_metadata():
    user_id = session['user_id']
    audio_id = r.get(f"audio_{user_id}")
    if audio_id is None:
        return jsonify({"error": "No audio currently playing"}), 404

    return jsonify({"html": audio_id})

@app.route('/skip', methods=['POST'])
def skip():
    user_id = session['user_id']
    audio_id = r.get(f"audio_{user_id}")
    if audio_id is None:
        return jsonify({"error": "No audio currently playing"}), 404
    print(f"User: {user_id} skipped audio")
    r.delete(f"audio_{user_id}")
    return jsonify({"message": "Audio skipped"})

if __name__ == '__main__':
    app.run(debug=True, port=8123)
