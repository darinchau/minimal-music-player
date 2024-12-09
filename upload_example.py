import os
import requests
import dotenv
import tempfile
from pydub import AudioSegment
from tqdm.auto import tqdm
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

def upload_file(url: str, file_path: str, url_id: str, title: str, *, progress_bar: bool = True):
    """ Upload a file to a specified URL using POST with multipart/form-data.
    - url (str): the URL to upload the file to
    - file_path (str): the path to the file to upload
    - url_id (str): the URL ID of the file
    - title (str): the title of the file
    """
    audio = AudioSegment.from_mp3(file_path)
    chunks = make_chunks(audio, CHUNK_SIZE_SECONDS * 1000)
    chunks = list(chunks)

    r = requests.post(url, data={
        'url_id': url_id,
        'title': title,
        'secret': os.getenv("SECRET_KEY"),
        "chunks": len(chunks)
    })

    if not r.ok:
        raise Exception(f"Failed to upload metadata ({r.status_code}): {r.text}")

    with tempfile.TemporaryDirectory() as temp_dir:
        for i, chunk in tqdm(enumerate(chunks), desc=f"Uploading {title}...", disable=not progress_bar):
            chunk_name = os.path.join(temp_dir, f"chunk{i}.mp3")
            chunk.export(chunk_name, format="mp3")

            with open(chunk_name, 'rb') as f:
                r = requests.post(url, data={
                    'url_id': url_id,
                    'title': title,
                    'secret': os.getenv("SECRET_KEY"),
                    "chunks": len(chunks)
                }, files={
                    'file': f
                })

            if not r.ok:
                raise Exception(f"Failed to upload chunk {i} of {title} ({r.status_code}): {r.text}")

    print("Uploaded ", title)
