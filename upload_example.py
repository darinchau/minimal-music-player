import os
import requests
import dotenv
import tempfile
from pydub import AudioSegment
from tqdm.auto import tqdm
from contextlib import contextmanager
import time

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
    # Check if song exists
    r = requests.get(url, data = {
        'url_id': url_id,
        'secret': os.getenv("SECRET_KEY"),
    })
    if r.ok:
        print(f"Song {title} already exists")
        return

    audio = AudioSegment.from_mp3(file_path)
    chunks = make_chunks(audio, CHUNK_SIZE_SECONDS * 1000)
    chunks = list(chunks)

    print(f"Processed mp3. Uploading {title} ({len(chunks)} chunks)...")

    r = requests.post(url, data={
        'url_id': url_id,
        'title': title,
        'secret': os.getenv("SECRET_KEY"),
        "chunks": len(chunks)
    })

    if not r.ok:
        raise Exception(f"Failed to upload metadata ({r.status_code}): {r.text}")

    track_id = r.json()['id']

    with tempfile.TemporaryDirectory() as temp_dir:
        for i, chunk in tqdm(enumerate(chunks), desc=f"Uploading {title}...", disable=not progress_bar, total=len(chunks)):
            chunk_name = os.path.join(temp_dir, f"chunk{i}.mp3")
            chunk.export(chunk_name, format="mp3")

            tries = 0
            while True:
                with open(chunk_name, 'rb') as f:
                    r = requests.post(url, data={
                        'current_track': track_id,
                        "current_chunk": i,
                        'secret': os.getenv("SECRET_KEY"),
                    }, files={
                        'file': f
                    })

                if r.ok:
                    break

                tries += 1
                if tries >= 5:
                    print(f"Failed to upload chunk {i} of {title} ({r.status_code}): {r.text}")
                    break

                time.sleep(1)
    print("Uploaded ", title)
