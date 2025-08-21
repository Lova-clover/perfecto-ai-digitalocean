from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json
import os

def upload_to_youtube(video_path, title="AI 자동 생성 영상", description="AI로 생성된 숏폼입니다."):
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    token_json = os.getenv("YT_TOKEN_JSON", "")
    token_file = os.getenv("YT_TOKEN_FILE", "")
    if token_file and os.path.exists(token_file):
        with open(token_file, "r") as f:
            token_data = json.load(f)
    elif token_json:
        token_data = json.loads(token_json)
    else:
        raise RuntimeError("Missing YouTube creds: set YT_TOKEN_JSON or YT_TOKEN_FILE")

    # ✅ token dict로 자격 증명 생성
    credentials = Credentials.from_authorized_user_info(token_data, SCOPES)

    youtube = build("youtube", "v3", credentials=credentials)

    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["AI", "쇼츠", "자동화"],
            "categoryId": "22"
        },
        "status": {
            "privacyStatus": "public"
        }
    }

    media_file = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    upload_request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media_file
    )
    response = upload_request.execute()
    return f"https://youtube.com/watch?v={response['id']}"