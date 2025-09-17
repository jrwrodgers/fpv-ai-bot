import json
import re
from googleapiclient.discovery import build

# --- Prompt user for input ---
YOUTUBE_API_KEY = "AIzaSyAhLyD2Uesduc1OhYKEE-19S0b4Qs5cso8"
channel_input = input("Enter the YouTube Channel URL, handle, or Channel ID: ").strip()
RESOURCES_PATH = "resources_youtube.json"


# --- YouTube API setup ---
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# --- Resolve Channel ID ---
def resolve_channel_id(user_input: str) -> str:
    """
    Resolves a YouTube channel input into the canonical channel ID.
    Accepts:
      - Raw channel ID (starts with 'UC')
      - /c/ or /user/ URLs
      - @handles (e.g., https://www.youtube.com/@JoshuaBardwell)
    """
    user_input = user_input.strip()

    # Already a channel ID
    if user_input.startswith("UC"):
        return user_input

    # Handle @handle URLs
    handle_match = re.search(r"@([\w\-]+)", user_input)
    if handle_match:
        handle = handle_match.group(1)
        request = youtube.search().list(
            part="snippet",
            q=handle,
            type="channel",
            maxResults=1
        )
        response = request.execute()
        items = response.get("items", [])
        if items:
            return items[0]["snippet"]["channelId"]

    # Handle /c/ or /user/ URLs
    match = re.search(r"(?:/c/|/user/)([\w\-]+)", user_input)
    if match:
        identifier = match.group(1)
        request = youtube.channels().list(
            part="id",
            forUsername=identifier
        )
        response = request.execute()
        items = response.get("items", [])
        if items:
            return items[0]["id"]

    raise ValueError("Could not resolve channel ID. Please enter a valid YouTube channel URL, handle, or ID.")

# Resolve
try:
    CHANNEL_ID = resolve_channel_id(channel_input)
    print(f"Resolved channel ID: {CHANNEL_ID}")
except Exception as e:
    print(f"Error resolving channel: {e}")
    exit(1)

# --- Load existing resources ---
try:
    with open(RESOURCES_PATH, "r") as f:
        resources = json.load(f)
except FileNotFoundError:
    resources = {}

resources.setdefault("youtube_videos", [])

# --- Get uploads playlist ID ---
channel_response = youtube.channels().list(
    part="contentDetails",
    id=CHANNEL_ID
).execute()

uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']

# --- Fetch all videos from uploads playlist ---
next_page_token = None
while True:
    playlist_request = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads_playlist_id,
        maxResults=50,
        pageToken=next_page_token
    )
    playlist_response = playlist_request.execute()

    for item in playlist_response.get('items', []):
        video_data = {
            "title": item['snippet']['title'],
            "url": f"https://www.youtube.com/watch?v={item['snippet']['resourceId']['videoId']}",
            "description": item['snippet']['description']
        }
        if video_data not in resources["youtube_videos"]:
            resources["youtube_videos"].append(video_data)

    next_page_token = playlist_response.get("nextPageToken")
    if not next_page_token:
        break

# --- Save back to JSON ---
with open(RESOURCES_PATH, "w") as f:
    json.dump(resources, f, indent=2)

print(f"✅ Added {len(resources['youtube_videos'])} videos to {RESOURCES_PATH}")

