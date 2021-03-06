import logging

import aiohttp
import re
from aiogram.utils.callback_data import CallbackData
from aiogram import types

from io import BytesIO
from PIL import Image

from config import HCTI_API_KEY, HCTI_API_USER_ID, HCTI_API_ENDPOINT


OWM_API_URL_FIND = "http://api.openweathermap.org/data/2.5/find"
OWM_API_URL_WEATHER = "https://api.openweathermap.org/data/2.5/weather"
OWM_API_ONECALL_URL_FORECAST = "https://api.openweathermap.org/data/2.5/onecall"

with open("staticfiles/weather_icons.css", "r") as file:
    CSS_WEATHER = file.read()

with open("templates/sunny.html", "r") as file:
    HTML_SUNNY = file.read()

with open("templates/partlycloudy.html", "r") as file:
    HTML_PARTLYCLOUDY = file.read()

with open("templates/mostlycloudy.html", "r") as file:
    HTML_MOSTLYCLOUDY = file.read()

with open("templates/cloudy.html", "r") as file:
    HTML_CLOUDY = file.read()

with open("templates/fogorhazy.html", "r") as file:
    HTML_FOGORHAZY = file.read()

with open("templates/chancerain.html", "r") as file:
    HTML_CHANCERAIN = file.read()

with open("templates/chancetstorms.html", "r") as file:
    HTML_TSTORMS = file.read()

with open("templates/sleet.html", "r") as file:
    HTML_SLEET = file.read()

with open("templates/flurries.html", "r") as file:
    HTML_FLURRIES = file.read()

with open("templates/snow.html", "r") as file:
    HTML_SNOW = file.read()

WEATHER_ICONS_HTML = [
    ("2..", HTML_TSTORMS),
    ("3..", HTML_CHANCERAIN),
    ("5..", HTML_CHANCERAIN),
    ("60.", HTML_SNOW),
    ("61.", HTML_SLEET),
    ("62.", HTML_SLEET),
    ("7.", HTML_FOGORHAZY),
    ("800", HTML_SUNNY),
    ("801", HTML_PARTLYCLOUDY),
    ("802", HTML_MOSTLYCLOUDY),
    ("803", HTML_MOSTLYCLOUDY),
    ("804", HTML_CLOUDY),
]

WEATHER_UNITS = {
    "celsius": ["metric", "\N{DEGREE SIGN}C"],
    "fahrenheit": ["imperial", "\N{DEGREE SIGN}F"],
}

metric_cb = CallbackData("change_metric", "city", "lat", "lon", "metric")
details_cb = CallbackData("weather_details", "city", "lat", "lon")


def lookup(s, lookups):
    for pattern, value in lookups:
        if re.search(pattern, s):
            return value
    return None


async def get_menu_buttons():
    menu_buttons = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu_buttons.add(
        types.KeyboardButton(text="Current weather"),
    )
    menu_buttons.add(
        types.KeyboardButton(text="Weather forecast"),
    )
    menu_buttons.add(
        types.KeyboardButton(text="Settings"),
    )
    return menu_buttons


async def get_img_weather_url(city: str, weather: str, weather_id: str, metric: str):
    weather_html = lookup(weather_id, WEATHER_ICONS_HTML)
    if weather_html:
        data = {
            "html": weather_html.replace("\n", "").format(
                city=city, weath=weather + " " + metric
            ),
            "css": CSS_WEATHER,
            "google_fonts": "Roboto",
        }
    else:
        logging.warning("Undefined weather code: ", weather_id)
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=HCTI_API_ENDPOINT,
                data=data,
                auth=aiohttp.BasicAuth(HCTI_API_USER_ID, HCTI_API_KEY),
            ) as response:
                return await response.json()
    except:
        return None


async def append_images(
    images, direction="horizontal", bg_color=(255, 255, 255), aligment="center"
):
    """
    Args:
        images: List of PIL images
        direction: direction of concatenation, 'horizontal' or 'vertical'
        bg_color: Background color (default: white)
        aligment: alignment mode if images need padding;
           'left', 'right', 'top', 'bottom', or 'center'
    """
    widths, heights = zip(*(i.size for i in images))

    if direction == "horizontal":
        new_width = sum(widths)
        new_height = max(heights)
        if (new_height * 2.5) < new_width:
            new_height = round(new_width / 2.5)
    else:
        new_width = max(widths)
        new_height = sum(heights)

    new_im = Image.new("RGB", (new_width, new_height), color=bg_color)

    offset = 0
    for im in images:
        if direction == "horizontal":
            y = 0
            if aligment == "center":
                y = int((new_height - im.size[1]) / 2)
            elif aligment == "bottom":
                y = new_height - im.size[1]
            new_im.paste(im, (offset, y))
            offset += im.size[0]
        else:
            x = 0
            if aligment == "center":
                x = int((new_width - im.size[0]) / 2)
            elif aligment == "right":
                x = new_width - im.size[0]
            new_im.paste(im, (x, offset))
            offset += im.size[1]

    return new_im


async def concat_imgs_by_urls(urls, bg_color):
    imgs = []
    for i in range(len(urls)):
        async with aiohttp.ClientSession() as session:
            async with session.get(url=urls[i]) as response:
                buffer = BytesIO(await response.read())
        img = Image.open(buffer)
        imgs.append(img)
    return await append_images(imgs, direction="horizontal", bg_color=bg_color)
