import os
import sys
from flask import Flask, Response, stream_with_context, render_template
from flask_cors import CORS
import pyaudio
import wave
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://username:password@localhost/audiodb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads/'
db = SQLAlchemy(app)

CHUNK = 1024

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

class AudioFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    filename = db.Column(db.String(100), nullable=False)
    url_id = db.Column(db.String(11), nullable=False)
    active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<AudioFile {self.title}>'

with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['audio']
    url_id = request.form['url_id']
    if len(url_id) != 11:
        return jsonify({"error": "Invalid URL ID"}), 400

    if file and file.filename.endswith('.wav'):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        audio_file = AudioFile(
            title=request.form['title'],
            filename=filename,
            url_id=url_id
        )
        db.session.add(audio_file)
        db.session.commit()
        return jsonify({"message": "File uploaded successfully", "id": audio_file.id})

    return jsonify({"error": "Invalid file"}), 400

@app.route('/play', methods=['GET'])
def play_audio():
    def sound(path: str):
        wf = wave.open(path, 'rb')

        p = pyaudio.PyAudio()

        stream = p.open(format =
                        p.get_format_from_width(wf.getsampwidth()),
                        channels = wf.getnchannels(),
                        rate = wf.getframerate(),
                        output = True)

        data = wf.readframes(CHUNK)

        while data:
            stream.write(data)
            data = wf.readframes(CHUNK)

        # cleanup stuff.
        wf.close()
        stream.close()
        p.terminate()

    path = None
    if 'id' in request.args:
        audio_file = AudioFile.query.get(request.args['id'])
        if audio_file:
            path = os.path.join(app.config['UPLOAD_FOLDER'], audio_file.filename)
    elif 'url_id' in request.args:
        audio_file = AudioFile.query.filter_by(url_id=request.args['url_id']).first()
        if audio_file:
            path = os.path.join(app.config['UPLOAD_FOLDER'], audio_file.filename)
    elif 'title' in request.args:
        audio_file = AudioFile.query.filter_by(title=request.args['title']).first()
        if audio_file:
            path = os.path.join(app.config['UPLOAD_FOLDER'], audio_file.filename)

    if not path:
        return jsonify({"error": "File not found"}), 404

    return Response(sound(), mimetype="audio/wav")

if __name__ == '__main__':
    app.run(debug=True, port=8123)
