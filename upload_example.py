import os
import requests
import dotenv
import tempfile
from pydub import AudioSegment
from contextlib import contextmanager

dotenv.load_dotenv()

url = "http://localhost:8123"

CHUNK_SIZE_SECONDS = 2

def make_chunks(audio_segment, chunk_length_ms):
    for i in range(0, len(audio_segment), chunk_length_ms):
        yield audio_segment[i:i + chunk_length_ms]

@contextmanager
def multiopen(paths: list[str]):
    files = [open(path, 'rb') for path in paths]
    try:
        yield files
    finally:
        for file in files:
            file.close()

def upload_file(url: str, file_path: str, url_id: str, title: str):
    """ Upload a file to a specified URL using POST with multipart/form-data.
    - url (str): the URL to upload the file to
    - file_path (str): the path to the file to upload
    - url_id (str): the URL ID of the file
    - title (str): the title of the file
    """
    audio = AudioSegment.from_mp3(file_path)
    chunks = make_chunks(audio, CHUNK_SIZE_SECONDS * 1000)

    with tempfile.TemporaryDirectory() as temp_dir:
        filepaths = []
        for i, chunk in enumerate(chunks):
            chunk_name = os.path.join(temp_dir, f"chunk{i}.mp3")
            chunk.export(chunk_name, format="mp3")
            filepaths.append(chunk_name)

        with multiopen(filepaths) as files:
            data = {
                'url_id': url_id,
                'title': title,
                "secret": os.getenv('SECRET_KEY'),
                'chunks': len(filepaths)
            }
            audio_files = {
                f"chunk_{i}": file for i, file in enumerate(files)
            }
            response = requests.post(url, data=data, files=audio_files)
    return response
