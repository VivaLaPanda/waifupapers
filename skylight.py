
import time
from typing import List
import requests
import os
import dotenv
import os
from tzwhere import tzwhere
from astral import LocationInfo
from apscheduler.schedulers.blocking import BlockingScheduler
from generations import get_image, download_image, upscale

dotenv.load_dotenv()

# Get SKYLIGHT_API_TOKEN from environment variable
SKYLIGHT_API_TOKEN = os.environ.get("SKYLIGHT_API_TOKEN")
if not SKYLIGHT_API_TOKEN:
    print("No SKYLIGHT_API_TOKEN found in environment variables. Exiting.")
    exit(1)

# Get frames data from skylight API
# Returns a json object or error
# [{'id': '1369742', 'type': 'frame', 'attributes': {'name': 'penki', 'code': None, 'mine': True, 'open_to_public': False, 'message_viewability': 'viewable_to_all_senders', 'grace_period_ends': None, 'share_token': 'db446a628d52829629bf3f4282061e7f', 'notification_email': 'adrianrsmith93@gmail.com', 'apps': ['photos'], 'destroyed_at': None, 'brightness': 255, 'slideshow_speed': 10, 'slideshow_style': 0, 'sleeps_at': '21:00', 'wakes_at': '06:00', 'currently_sleeping': False, 'sleep_mode_on': False, 'timezone': 'America/Los_Angeles', 'start_sound': False, 'show_caption': True, 'show_heart': False, 'blur_effect': True, 'current_album_id': -1, 'plus': False, 'trialing': False, 'calendar_sync': False}, 'relationships': {'user': {'data': {'id': '5996783', 'type': 'user'}}, 'event_notification_setting': {'data': None}}}]
def get_frames() -> List[dict]:
    resp = requests.get("https://app.ourskylight.com/api/frames?", headers={
        "accept": "application/json, text/plain, */*",
        "authorization": "Basic " + SKYLIGHT_API_TOKEN,
    });

    if resp.status_code != 200:
        print("Error getting frames from skylight API. Exiting.")
        exit(1)
    
    return resp.json()["data"]

# Get messages for frame
# Returns a json object or error
# {"data":[{"id":"363683779","type":"message_asset","attributes":{"asset_type":"photo","asset_key":"61f0d9fef20bf07d79e163376924164a-0.jpg","thumbnail_key":null,"asset_bucket":"darkroom-production","created_at":"2023-02-08T01:20:30.890Z","frame_name":"penki","from_email":"adrianrsmith93@gmail.com","destroyed_at":null,"caption":"kissinger","comments_count":0,"asset_url":"https://darkroom-production.s3.amazonaws.com/61f0d9fef20bf07d79e163376924164a-0.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256\u0026X-Amz-Credential=AKIA52BMULLZAZME3BX6%2F20230208%2Fus-east-1%2Fs3%2Faws4_request\u0026X-Amz-Date=20230208T000000Z\u0026X-Amz-Expires=604800\u0026X-Amz-SignedHeaders=host\u0026X-Amz-Signature=4c6fab1efa2006f96adb0440545c2b7350c1842071c7854c740949561591ebe6","month_in_review_display_date":null,"frame_id":1369742,"frame_owner_id":5996783,"sender_id":5996783,"thumbnail_url":null}},{"id":"362857804","type":"message_asset","attributes":{"asset_type":"photo","asset_key":"0aqkt6l32mm-0.jpg","thumbnail_key":null,"asset_bucket":"darkroom-production","created_at":"2023-02-05T23:45:09.557Z","frame_name":"penki","from_email":"adrianrsmith93@gmail.com","destroyed_at":null,"caption":null,"comments_count":0,"asset_url":"https://darkroom-production.s3.amazonaws.com/0aqkt6l32mm-0.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256\u0026X-Amz-Credential=AKIA52BMULLZAZME3BX6%2F20230208%2Fus-east-1%2Fs3%2Faws4_request\u0026X-Amz-Date=20230208T000000Z\u0026X-Amz-Expires=604800\u0026X-Amz-SignedHeaders=host\u0026X-Amz-Signature=0d6b8e8014ecb575a47f2744b07e0096aa0c041e3d5f643ccf671e38869fa5b1","month_in_review_display_date":null,"frame_id":1369742,"frame_owner_id":5996783,"sender_id":5996783,"thumbnail_url":null}}],"meta":{"frame_owner":true,"trial_days_remaining":null,"current_page":1,"num_pages":1}}
def get_assets(frame_id: str) -> List[dict]:
    resp = requests.get(f"https://app.ourskylight.com/api/frames/{frame_id}/messages", headers={
        "accept": "application/json, text/plain, */*",
        "authorization": "Basic " + SKYLIGHT_API_TOKEN,
    });

    if resp.status_code != 200:
        print("Error getting assets from skylight API. Exiting.")
        exit(1)

    return resp.json()["data"]

# Delete messages on a frame
# Returns the IDs of the assets removed
def delete_assets(frame_id: str, asset_ids: List[str]) -> List[int]:
    resp = requests.delete(f"https://app.ourskylight.com/api/frames/{frame_id}/messages/destroy_multiple", headers={
        "accept": "application/json, text/plain, */*",
        "authorization": "Basic " + SKYLIGHT_API_TOKEN,
    }, json={
        "message_ids": asset_ids
    });

    if resp.status_code != 200:
        print("Error deleting assets from skylight API. Exiting.")
        exit(1)
    
    return resp.json()

# Upload an image to a frame
def upload_image(frame_id: str, image_path: str) -> None:
    # Determine the extension of the image
    ext = image_path.split(".")[-1]

    # Get the upload URL
    # curl 'https://app.ourskylight.com/api/upload_urls' \
    # -H 'accept: application/json, text/plain, */*' \
    # -H 'authorization: Basic NTk5Njc4MzpkMzUxNTkzZDA1YzM5YWE5N2M0NDQyZjU1MGM2ZDdhNw==' \
    # --data-raw '{"ext":"png","frame_ids":["1369742"]}' \
    resp = requests.post("https://app.ourskylight.com/api/upload_urls", headers={
        "accept": "application/json, text/plain, */*",
        "authorization": "Basic " + SKYLIGHT_API_TOKEN,
    }, json={
        "ext": ext,
        "frame_ids": [frame_id]
    });

    if resp.status_code != 200:
        print("Error getting upload URL from skylight API. Exiting.")
        exit(1)
    
    # Extract the s3 upload url
    upload_url = resp.json()["data"][0]["url"]

    # Upload the image to s3
    resp = requests.put(upload_url, data=open(image_path, "rb"))

    if resp.status_code != 200:
        print("Error uploading image to s3. Exiting.")
        exit(1)
    
    return


def set_skylight(image_path: str):
    # Get the frames for our account
    frames = get_frames()
    
    # Extract the frame IDs
    frame_ids = [frame["id"] for frame in frames]

    # Use the first one always for now
    frame_id = frame_ids[0]

    # Get the assets for the frame
    assets = get_assets(frame_id)

    # Upload the image
    upload_image(frame_id, image_path)

    # Wait 30 seconds for the image to upload
    time.sleep(15)

    # Delete all old assets if there are any
    if len(assets) > 0:
        asset_ids = [asset["id"] for asset in assets]
        delete_assets(frame_id, asset_ids)

def get_fixed_location(lat, long):
    # Find the timezone given the latlong
    tz = tzwhere.tzwhere()
    timezone_str = tz.tzNameAt(lat, long)

    l = LocationInfo()
    l.name = 'User Location'
    l.region = 'idk'
    l.timezone = timezone_str
    l.latitude = lat
    l.longitude = long
    return l

def update_skylight():
    # Get the location of the skylight
    skylight_location = get_fixed_location(37.804363, -122.271111) #oakland

    # Get the image
    img_url = get_image(skylight_location)
    img_path = download_image(img_url[0])
    upscale_url= upscale(img_path)
    upscale_path = download_image(upscale_url)

    # delete original image
    os.remove(img_path)

    set_skylight(upscale_path)

def main(): 
    update_skylight()

    scheduler = BlockingScheduler()
    scheduler.add_job(update_skylight, 'interval', hours=1, misfire_grace_time=60*30, coalesce=True)
    scheduler.start()

main()