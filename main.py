import replicate
import datetime
from appscript import mactypes, app
import os
import pytz
import random
from tzwhere import tzwhere
import geocoder
import requests
from astral.sun import sun
from astral.moon import moonrise, moonset
from astral import LocationInfo, moon
from astral.geocoder import database, lookup
from apscheduler.schedulers.blocking import BlockingScheduler

wd_model = replicate.models.get("cjwbw/waifu-diffusion")
# Get OWM_API_KEY from environment variable
OWM_API_KEY = os.environ.get("OWM_API_KEY")

def get_base_prompt():
    # from behind, outdoors, scenery, 4k, wallpaper
    return [
        "outdoors",
        "scenery",
        "4k",
        "wallpaper",
        "from behind",
        "1girl",
        "wide_shot",
    ]

def get_character_prompts():
    return [
        "very long hair",
    ]

def get_season(dt):
    Y = 2000 # dummy leap year to allow input X-02-29 (leap day)
    seasons = [('winter', (datetime.date(Y,  1,  1),  datetime.date(Y,  3, 20))),
            ('spring', (datetime.date(Y,  3, 21),  datetime.date(Y,  6, 20))),
            ('summer', (datetime.date(Y,  6, 21),  datetime.date(Y,  9, 22))),
            ('autumn', (datetime.date(Y,  9, 23),  datetime.date(Y, 12, 20))),
            ('winter', (datetime.date(Y, 12, 21),  datetime.date(Y, 12, 31)))]
    
    # Shift all the seasons a bit, since the "feel" of a season is usually before it actually starts
    seasons = [(season, (start + datetime.timedelta(days=15), end + datetime.timedelta(days=15))) for season, (start, end) in seasons]

    if isinstance(dt, datetime.datetime):
        dt = dt.date()
    dt = dt.replace(year=Y)
    return next(season for season, (start, end) in seasons
                if start <= dt <= end)

def get_season_prompts(dt):
    # Determine the season from the datetime
    season = get_season(dt)

    # Map to danbooru tags
    tagMap = {
        "winter": ["winter"],
        "spring": ["spring"],
        "summer": ["summer"],
        "autumn": ["autumn"],
    }

    return tagMap[season]

def get_city():
    return LocationInfo("London", "England", "Europe/London", 51.5, -0.116)

# TODO: maybe affect weather
def get_night_prompts(city, dt, weather):
    rise = moonrise(city.observer, dt, tzinfo=city.tzinfo) # timestamp
    set = moonset(city.observer, dt, tzinfo=city.tzinfo) # timestamp
    phase = moon.phase(dt)

    # The moon phase method returns an number describing the phase, where the value is between 0 and 27.99. The following lists the mapping of various values to the description of the phase of the moon.
    # 0 .. 6.99	New moon
    # 7 .. 13.99	First quarter
    # 14 .. 20.99	Full moon
    # 21 .. 27.99	Last quarter

    # if the moon is up, use it
    night_tags = ["night"]
    if dt > rise or dt < set:
        if phase < 14 and phase >= 7:
            night_tags.append("crescent moon")
        elif phase < 21:
            night_tags.append("full moon")
        else:
            night_tags.append("crescent moon")
    
    # TODO: update once I have weather logic
    if weather == "clear":
        night_tags.append("starry sky")

    return night_tags

def get_time_prompts(city, dt, weather):
    # Determine if it's night, dawn, sunrise, noon, sunset, or dusk using astral
    # https://astral.readthedocs.io/en/latest/
    s = sun(city.observer, dt, tzinfo=city.tzinfo)

    if dt < s["dawn"]:
        return get_night_prompts(city, dt, weather)
    elif dt < s["sunrise"]:
        return ["dawn"]
    elif dt < s["noon"]:
        return ["sunrise"]
    elif dt < s["sunset"]:
        return ["day"]
    elif dt < s["dusk"]:
        return ["sunset"]
    else:
        return get_night_prompts(city, dt, weather)

def get_weather(city):
    BASE_URL = "https://api.openweathermap.org/data/2.5/weather?"

    url = f"{BASE_URL}lat={city.latitude}&lon={city.longitude}&appid={OWM_API_KEY}"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        main = data['main']
        temperature = main['temp']
        weather = data['weather']
        weather_description = weather[0]['description']
        return {"weather": weather_description, "temp": temperature}
    else:
        print(response)
        print(response.content)

def get_weather_prompts(weather, temperature, time_tags):
    baseWeatherTags = {
        "clear sky": ["clear sky"],
        "few clouds": ["cloudy_sky"],
        "scattered clouds": ["cloudy_sky"], 
        "broken clouds": ["cloudy_sky"],    
        "shower rain": ["rain"],
        "rain": ["rain"],
        "thunderstorm": ["lightning", "storm", "storm_cloud"],
        "snow": ["snow"],
        "mist": ["fog"],
    }
    
    tags = baseWeatherTags[weather]
    if weather == "broken clouds":
        if "day" in time_tags:
            tags.append("dappled_sunlight")
            tags.append("sunbeam")
        elif "full moon" in time_tags:
            tags.append("dappled_moonlight")
    
    # Temperature is in kelvin, so convert to celsius
    temperature = temperature - 273.15
    if temperature < 15:
        tags.append("winter_clothes")
    
    if temperature < 5:
        tags.append("scarf")
        tags.append("jacket")
    
    if temperature > 100:
        tags.append("swimsuit")
    elif temperature > 85 and weather == "clear sky":
        tags.append("sun_hat")

    return tags

def random_addons(seed):
    addons = [
        "ocean",
        "mountain",
        "lake",
        "forest",
        "river",
        "temple",
        "cliff",
        "waterfall",
        "hill",
        "village",
    ]
    
    # Seed the random number generator
    # And then pick any two of the above
    random.seed(seed)
    return random.sample(addons, 2)

def get_user_location():
    g = geocoder.ip('me')

    # Find the timezone given the latlong
    tz = tzwhere.tzwhere()
    timezone_str = tz.tzNameAt(g.latlng[0], g.latlng[1])

    l = LocationInfo()
    l.name = 'User Location'
    l.region = 'idk'
    l.timezone = timezone_str
    l.latitude = g.latlng[0]
    l.longitude = g.latlng[1]
    return l

def default_gen(seed):
    # Get the users's location
    user_location = get_user_location()

    # Get the current datetime localized to the current timezone
    now = datetime.datetime.now(pytz.timezone(user_location.timezone))

    # For testing, add hours to the time
    #now = now + datetime.timedelta(hours=10)

    return gen_prompt(user_location, now, seed)

def gen_prompt(location, dt, seed):
    prompt = get_base_prompt()
    prompt.extend(get_character_prompts())

    # Get the current city
    city = location

    # Get the current time prompts
    prompt.extend(get_time_prompts(city, dt, "clear"))

    # Get the current weather
    weather = get_weather(city)
    
    prompt.extend(get_weather_prompts(weather["weather"], weather["temp"], prompt))

    # Get the current season prompts
    prompt.extend(get_season_prompts(dt))

    # Get the current addons
    prompt.extend(random_addons(seed))

    return prompt

def get_image():
    # Get the current day to use as a seed
    now = datetime.datetime.now()
    seed = now.day

    prompt = default_gen(seed)
    # join prompt with ", "
    prompt = ", ".join(prompt)

    return wd_model.predict(prompt=prompt, width=1024, height=512, num_inference_steps=60, seed=seed)

def download_image(url):
    # Download the image as [timestamp].png
    r = requests.get(url, allow_redirects=True)

    path = f"{datetime.datetime.now().timestamp()}.png"
    # Make a /images/ dir if one doesn't exist
    if not os.path.exists("images"):
        os.makedirs("images")
    path = f"images/{path}"

    open(path, 'wb').write(r.content)

    return path

def set_wallpaper(img_path):
    # Set the wallpaper using appscript
    app('Finder').desktop_picture.set(mactypes.File(img_path))

def update_wallpaper():
    img_url = get_image()
    img_path = download_image(img_url[0])

    set_wallpaper(img_path)

def main(): 
    update_wallpaper()

    scheduler = BlockingScheduler()
    scheduler.add_job(update_wallpaper, 'interval', hours=1)
    scheduler.start()

if __name__ == "__main__":
    main()