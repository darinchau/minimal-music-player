from __future__ import annotations
import os
import sys
from flask import Flask, Response, stream_with_context, render_template
from flask_cors import CORS
from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
import os
from werkzeug.utils import secure_filename
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey, Float, Boolean
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
import redis
import random
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

app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///database.db"
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.secret_key = os.getenv('SECRET_KEY')

db.init_app(app)
with app.app_context() as ctx:
    db.create_all()

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Routes
@app.route('/')
def index():
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

    if file and file.filename is not None:
        filename = secure_filename(file.filename)
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

@app.route('/<format>/<url_id>', methods=['GET'])
def play_sound(format, url_id):
    def stream(path):
        try:
            with open(path, "rb") as fwav:
                data = fwav.read(CHUNK)
                while data:
                    yield data
                    data = fwav.read(CHUNK)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    audio = AudioFile.query.filter_by(url_id=url_id).filter_by(active=True).filter_by(format=format).first()
    if not audio:
        return jsonify({"error": "File not found"}), 404

    path = audio.filename
    return Response(stream(path), mimetype=AudioFile.ACCEPTED_FORMATS[format])

@app.route('/play', methods=['GET'])
def play_random():
    format = "ogg"
    session['current_audio'] = None  # Reset current audio for this session

    def stream(paths):
        print(paths)

        while True:
            path, id = random.choice(paths)
            session['current_audio'] = id  # Store the current audio ID in the session
            try:
                with open(path, "rb") as fwav:
                    data = fwav.read(CHUNK)
                    while data:
                        yield data
                        data = fwav.read(CHUNK)
            except Exception as e:
                return jsonify({"error": str(e)}), 500

    audios = AudioFile.query.filter_by(active=True, format=format).all()
    if not audios:
        return jsonify({"error": "File not found"}), 404
    paths = [(audio.filename, audio.id) for audio in audios]
    return Response(stream(paths), mimetype=AudioFile.ACCEPTED_FORMATS[format])

@app.route('/metadata', methods=['GET'])
def get_metadata():
    audio_id = session.get('current_audio')
    if audio_id is None:
        return jsonify({"error": "No audio currently playing"}), 404

    audio = AudioFile.query.get(audio_id)
    if audio:
        return jsonify({"title": audio.title, "url": f"https://www.youtube.com/watch?v={audio.url_id}"})
    else:
        return jsonify({"error": "Audio metadata not found"}), 404

if __name__ == '__main__':
    app.run(debug=True, port=8123)
