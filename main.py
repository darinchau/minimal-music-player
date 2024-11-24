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

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())  # Generate a unique user_id
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['audio']
    url_id = request.form['url_id']
    format = request.form['format']
    if len(url_id) != 11:
        return jsonify({"error": "Invalid URL ID"}), 400

    if format not in AudioFile.ACCEPTED_FORMATS:
        return jsonify({"error": f"Invalid format: {format}"}), 400

    secret = request.form['secret']
    if secret != os.getenv('ADMIN_SECRET'):
        return jsonify({"error": "Invalid secret"}), 401

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
    audio_id = request.form['id']
    secret = request.form['secret']
    if secret != os.getenv('ADMIN_SECRET'):
        return jsonify({"error": "Invalid secret"}), 401
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
    audio_id = request.form['id']
    secret = request.form['secret']
    mode = request.form['mode']
    if secret != os.getenv('ADMIN_SECRET'):
        return jsonify({"error": "Invalid secret"}), 401
    audio = AudioFile.query.get(audio_id)
    if audio:
        if mode == 'activate':
            audio.active = True
        elif mode == 'deactivate':
            audio.active = False
        else:
            return jsonify({"error": f"Invalid mode: {mode}"}), 400
        db.session.commit()
        return jsonify({"message": f"File {mode}d successfully"})
    return jsonify({"error": "File not found"}), 404


@app.route('/play', methods=['GET'])
def play_random():
    format = "ogg"
    user_id = request.cookies.get('user_id')

    def stream(paths):
        check_skip = 100
        while True:
            path, id = random.choice(paths)
            r.set(f"audio_{user_id}", id)
            print(f"User: {user_id} is playing {id}")
            try:
                with open(os.path.join(app.config['UPLOAD_FOLDER'], path), "rb") as fwav:
                    data = fwav.read(CHUNK)
                    while data:
                        yield data
                        data = fwav.read(CHUNK)
                        check_skip -= 1
                        if check_skip <= 0:
                            check_skip = 100
                            if r.get(f"audio_{user_id}") is None:
                                print(f"User: {user_id} stopped playing {id}")
                                break
            except Exception as e:
                print(e)
                print(traceback.format_exc())
                time.sleep(1)
                continue

    audios = AudioFile.query.filter_by(active=True, format=format).all()
    if not audios:
        return jsonify({"error": "File not found"}), 404
    paths = [(audio.filename, audio.id) for audio in audios]
    return Response(stream(paths), mimetype=AudioFile.ACCEPTED_FORMATS[format])

@app.route('/metadata')
def get_metadata():
    user_id = request.cookies.get('user_id')
    audio_id = r.get(f"audio_{user_id}")
    if audio_id is None:
        return jsonify({"error": "No audio currently playing"}), 404

    audio = AudioFile.query.get(audio_id)
    if audio:
        return jsonify({"title": audio.title, "url": f"https://www.youtube.com/watch?v={audio.url_id}"})
    else:
        return jsonify({"error": "Audio metadata not found"}), 404

@app.route('/skip', methods=['POST'])
def skip():
    user_id = request.cookies.get('user_id')
    audio_id = r.get(f"audio_{user_id}")
    if audio_id is None:
        return jsonify({"error": "No audio currently playing"}), 404

    audio = AudioFile.query.get(audio_id)
    if audio:
        r.delete(f"audio_{user_id}")
        return jsonify({"message": "Audio skipped"})
    else:
        return jsonify({"error": "Audio not found"}), 404

if __name__ == '__main__':
    app.run(debug=True, port=8123)
