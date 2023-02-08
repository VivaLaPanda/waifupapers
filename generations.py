from typing import List, Tuple
import replicate
import datetime
import os
import pytz
import random
from tzwhere import tzwhere
import geocoder
import requests
import dotenv
from astral.sun import sun
from astral.moon import moonrise, moonset
from astral import LocationInfo, moon

dotenv.load_dotenv()

wd_model = replicate.models.get("tstramer/waifu-diffusion")
upscale_model = replicate.models.get("nightmareai/real-esrgan")
# Get OWM_API_KEY from environment variable
OWM_API_KEY = os.environ.get("OWM_API_KEY")

def get_base_prompt(gen_config: dict) -> Tuple[List[str], List[str]]:
    return gen_config["base"]["prompt"], gen_config["base"]["negative_prompt"]

def get_character_prompts(seed, gen_config: dict) -> List[str]:
    # if the gen config for character is length 0, return empty list
    if len(gen_config["characters"]) == 0:
        return []
    
    # loop over the characters in the gen config list
    # and add them to a list of prompts
    chacter_prompts = []
    for character in gen_config["characters"]:
        # Seed the random number generator
        # And then pick some combination of the above
        random.seed(seed)
        prompts =  random.sample(character["hair_len"], 1) + random.sample(character["hair_color"], 1) + random.sample(character["position"], 1) + random.sample(character["accessory"], 1)
        chacter_prompts += prompts
    
    return chacter_prompts

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

def get_season_prompts(dt) -> List[str]:
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

# TODO: maybe affect weather
def get_night_prompts(city, dt, weather) -> List[str]:
    rise = moonrise(city.observer, dt, tzinfo=city.tzinfo) # timestamp
    set = moonset(city.observer, dt, tzinfo=city.tzinfo) # timestamp
    phase = moon.phase(dt)

    # The moon phase method returns an number describing the phase, where the value is between 0 and 27.99. The following lists the mapping of various values to the description of the phase of the moon.
    # 0 .. 6.99	New moon
    # 7 .. 13.99	First quarter
    # 14 .. 20.99	Full moon
    # 21 .. 27.99	Last quarter

    # if the moon is up, use it
    night_tags = ["night", "darkness"]
    if dt > rise or dt < set:
        if phase < 14 and phase >= 7:
            night_tags.append("((crescent moon))")
        elif phase < 21:
            night_tags.append("((full moon))")
        else:
            night_tags.append("((crescent moon))")
    
    # TODO: update once I have weather logic
    if weather == "clear":
        night_tags.append("(starry sky)")

    return night_tags

def get_time_prompts(city, dt, weather) -> List[str]:
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

# Get the positive and negative tags for the weather
def get_weather_prompts(weather, temperature, time_tags) -> Tuple[List[str], List[str]]:
    baseWeatherTags = {
        "clear sky": (["clear sky"], ["cloudy sky", "cloud"]),
        "few clouds": (["cloudy sky"], []),
        "scattered clouds": (["cloudy sky"], []), 
        "broken clouds": (["cloudy sky"], []),    
        "shower rain": (["rain"], []),
        "rain": (["rain"], ["clear sky"]),
        "thunderstorm": (["lightning", "storm", "storm cloud"], ["clear sky"]),
        "snow": (["snow"], ["clear sky"]),
        "mist": (["fog"], ["clear sky"]),
        "fog": (["fog"], ["clear sky"]),
        "haze": (["fog", "haze", "smoke"], ["clear sky"]),
    }
    
    positive_tags, negative_tags = baseWeatherTags[weather]
    if weather == "broken clouds":
        if "day" in time_tags:
            positive_tags.append("dappled sunlight")
            positive_tags.append("sunbeam")
        elif "full moon" in time_tags:
            positive_tags.append("dappled moonlight")

    # if it's not snowy, always negative snow
    if weather != "snow":
        negative_tags.append("snow")
    
    # Temperature is in kelvin, so convert to celsius
    temperature = temperature - 273.15
    if temperature < 15:
        positive_tags.append("winter clothes")
        positive_tags.append("cold")
    
    if temperature < 5:
        positive_tags.append("scarf")
        positive_tags.append("jacket")
    
    if temperature > 100:
        positive_tags.append("swimsuit")
    elif temperature > 85 and weather == "clear sky":
        positive_tags.append("sun_hat")

    return positive_tags, negative_tags

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

def get_user_location() -> LocationInfo:
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

def default_gen(seed, user_location: LocationInfo, gen_config: dict) -> Tuple[List[str], List[str]]:
    # Get the current datetime localized to the current timezone
    now = datetime.datetime.now(pytz.timezone(user_location.timezone))

    # For testing, add hours to the time
    #now = now + datetime.timedelta(hours=10)

    return gen_prompt(user_location, now, seed, gen_config)

def gen_prompt(location, dt, seed, gen_config: dict) -> Tuple[List[str], List[str]]:
    prompt, neg_prompt = get_base_prompt(gen_config)
    prompt.extend(get_character_prompts(seed, gen_config))

    # Get the current city
    city = location

    # Get the current weather
    weather = get_weather(city)

    # Get the current time prompts
    prompt.extend(get_time_prompts(city, dt, weather["weather"]))
    
    # Get the current weather prompts
    weather_pos_tags, weather_neg_tags = get_weather_prompts(weather["weather"], weather["temp"], prompt)
    prompt.extend(weather_pos_tags)
    neg_prompt.extend(weather_neg_tags)

    # Get the current season prompts
    prompt.extend(get_season_prompts(dt))

    # Get the current addons
    prompt.extend(random_addons(seed))

    return prompt, neg_prompt

# Generates the starting image for a location
def get_image(location: LocationInfo, gen_config: dict):
    # Get the current day to use as a seed
    now = datetime.datetime.now()
    seed = now.day

    prompt, neg_prompt = default_gen(seed, location, gen_config)
    # join prompt with ", "
    prompt = ", ".join(prompt)
    neg_prompt = ", ".join(neg_prompt)

    return wd_model.predict(prompt=prompt, negative_prompt=neg_prompt, width=1024, height=640, num_inference_steps=50, seed=seed, scheduler="K_EULER_ANCESTRAL")

def upscale(path):
    # Do upscale
    in_img = open(path, "rb")
    return upscale_model.predict(image=in_img)

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