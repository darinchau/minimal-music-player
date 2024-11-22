import requests

# Upload "test.wav"

def upload_file(url, file_path, url_id, format, title):
    """ Upload a file to a specified URL using POST with multipart/form-data. """
    with open(file_path, 'rb') as file:
        files = {'audio': (file_path, file, 'audio/wav')}
        data = {
            'url_id': url_id,
            'format': format,
            'title': title
        }
        response = requests.post(url, files=files, data=data)
        return response

if __name__ == '__main__':
    # URL of the Flask endpoint
    flask_url = 'http://localhost:8123/upload'

    # Path to the file to upload
    file_to_upload = 'rick.wav'

    # Example form data
    url_id = 'dQw4w9WgXcQ'
    format = 'wav'
    title = 'Never Gonna Give You Up'

    # Call the function to upload the file
    response = upload_file(flask_url, file_to_upload, url_id, format, title)

    # Print the server's response
    print(response.text)
