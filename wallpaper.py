from appscript import mactypes, app
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from generations import get_image, download_image, upscale, get_user_location

def update_wallpaper():
    # Get the users's location
    user_location = get_user_location()

    # Get the image
    img_url = get_image(user_location)
    img_path = download_image(img_url[0])
    upscale_url= upscale(img_path)
    upscale_path = download_image(upscale_url)

    # delete original image
    os.remove(img_path)

    set_wallpaper(upscale_path)

def set_wallpaper(img_path):
    # Set the wallpaper using appscript
    app('Finder').desktop_picture.set(mactypes.File(img_path))

def main(): 
    update_wallpaper()

    scheduler = BlockingScheduler()
    scheduler.add_job(update_wallpaper, 'interval', hours=1, misfire_grace_time=60*30, coalesce=True)
    scheduler.start()

if __name__ == "__main__":
    main()