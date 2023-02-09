
import time
import json
from typing import List
import requests
import os
import dotenv
import os
from tzwhere import tzwhere
from astral import LocationInfo
from apscheduler.schedulers.blocking import BlockingScheduler
from generations import get_image, download_image, upscale, override_wd_model

dotenv.load_dotenv()

# Get SKYLIGHT_API_TOKEN from environment variable
SKYLIGHT_API_TOKEN = os.environ.get("SKYLIGHT_API_TOKEN")
if not SKYLIGHT_API_TOKEN:
    print("No SKYLIGHT_API_TOKEN found in environment variables. Exiting.")
    exit(1)

# Get frames data from skylight API
# Returns a json object or error
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
    # -H 'accept: application/json, text/plain, */*' \\
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


def set_skylight(image_path: str, frame_id: str):
    # Get the assets for the frame
    assets = get_assets(frame_id)

    # Upload the image
    print(f"Uploading image {image_path} to frame {frame_id}...")
    upload_image(frame_id, image_path)

    # Wait 15 seconds for the image to upload
    time.sleep(45)

    # Delete all old assets if there are any
    print(f"Deleting {len(assets)} old assets from frame {frame_id}...")
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

def update_skylight(frame_id: str, gen_config: dict = {}):
    # Get the location of the skylight
    skylight_location = get_fixed_location(37.804363, -122.271111) #oakland

    # Get the image
    img_url = get_image(skylight_location, gen_config)
    img_path = download_image(img_url[0])
    upscale_url= upscale(img_path)
    upscale_path = download_image(upscale_url)

    print(f"Upscaled image to {upscale_path} from {img_path}...")

    # delete original image
    os.remove(img_path)

    print(f"Deleted original image {img_path}...")

    set_skylight(upscale_path, frame_id)

def main():
    # Get the frames from the ./gen-configs/frames.json file
    print("Reading frames.json")
    framefile = open("./gen-configs/frames.json", "r")
    frames = json.load(framefile) # type: dict[str, str]
    framefile.close()
    print(f"Found {len(frames)} frames to update...")

    for frame, config in frames.items():
        print(f"Updating frame {frame} with config {config}...")
        # Read in the generation config
        gen_config_file = open(f"./gen-configs/{config}.json", "r")
        gen_config = json.load(gen_config_file)
        update_skylight(frame, gen_config)

main()
