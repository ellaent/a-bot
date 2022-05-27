from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

import asyncio
import aiohttp
from db_utils import Database

import json
from io import BytesIO
import datetime

import logging

from config import TOKEN, OWM_TOKEN
from bot_utils import (
    OWM_API_URL_FIND,
    OWM_API_URL_WEATHER,
    OWM_API_ONECALL_URL_FORECAST,
    get_img_weather_url,
    WEATHER_UNITS,
    metric_cb,
    details_cb,
    concat_imgs_by_urls,
    get_menu_buttons,
)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


loop = asyncio.get_event_loop()
db = Database(loop)


class CityForm(StatesGroup):
    city = State()


class LocationForm(StatesGroup):
    location = State()


class CitySaveForm(StatesGroup):
    city = State()


class LocationSaveForm(StatesGroup):
    location = State()


class ForecastCityForm(StatesGroup):
    city = State()


class ForecastLocationForm(StatesGroup):
    location = State()


@dp.message_handler(commands=["start"])
async def process_start_command(message: types.Message):
    user = await db.current_user(message.chat.id)
    if user:
        pass
    else:
        await db.add_user(message.chat.id)

    menu_buttons = await get_menu_buttons()
    await message.answer(text="Hello!", reply_markup=menu_buttons)


@dp.message_handler(commands=["help"])
async def process_help_command(message: types.Message):
    await message.reply("Type smth to have another reply!")


@dp.message_handler(text=["Current weather"])
async def current_weather(message: types.Message):

    kb = types.InlineKeyboardMarkup()
    user_location = await db.get_user_location(message.chat.id)
    if user_location:
        location = json.loads(user_location)
        kb.add(
            types.InlineKeyboardButton(
                text="Current location",
                callback_data="current_weather_location_lon_"
                + location["lon"]
                + "_lat_"
                + location["lat"],
            )
        )
        kb.add(
            types.InlineKeyboardButton(
                text="Another city",
                callback_data="current_weather_city",
            )
        )
    else:
        kb.add(
            types.InlineKeyboardButton(
                text="Send location",
                callback_data="current_weather_location",
            )
        )
        kb.add(
            types.InlineKeyboardButton(
                text="Type city",
                callback_data="current_weather_city",
            )
        )
    await message.answer(
        "Choose option",
        reply_markup=kb,
    )


@dp.callback_query_handler(lambda query: query.data.startswith("current_weather_city"))
async def current_weather_city(callback_query: types.CallbackQuery):
    await CityForm.city.set()
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Type city",
    )
    return await bot.answer_callback_query(callback_query_id=callback_query.id)


@dp.message_handler(state="*", commands=["cancel"])
async def cancel_handler(message: types.Message, state: FSMContext):
    """
    Cancels any state
    """
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.finish()
    await message.reply("Cancelled.")


@dp.message_handler(state=CityForm.city)
async def process_city(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data["city"] = message.text
    await state.finish()

    s_city = data["city"]
    units = await db.get_user_metric(message.chat.id)
    params = {
        "q": s_city,
        "type": "like",
        "units": WEATHER_UNITS[units][0],
        "APPID": OWM_TOKEN,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url=OWM_API_URL_FIND, params=params) as response:
                r = await response.json()

        city = r["list"][0]
    except IndexError:
        return await bot.send_message(
            chat_id=message.chat.id, text="Sorry, no city found"
        )

    img = await get_img_weather_url(
        city["name"],
        str(round(city["main"]["temp"])),
        str(city["weather"][0]["id"]),
        WEATHER_UNITS[units][1],
    )
    caption = (
        "Current temp in {city} is {degrees:.0f} {metric} \n"
        "*{description}*\n"
        "Feels like {feels} {metric}\n".format(
            city=city["name"],
            degrees=city["main"]["temp"],
            metric=WEATHER_UNITS[units][1],
            description=city["weather"][0]["description"].capitalize(),
            feels=round(city["main"]["feels_like"]),
        )
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="Details",
            callback_data=details_cb.new(
                lat=city["coord"]["lat"], lon=city["coord"]["lon"], city=city["name"]
            ),
        )
    )

    await bot.send_photo(
        chat_id=message.chat.id,
        photo=img["url"],
        caption=caption,
        parse_mode="markdown",
        reply_markup=kb,
    )

    location = {
        "lat": str(city["coord"]["lat"]),
        "lon": str(city["coord"]["lon"]),
        "city": city["name"],
    }
    current_location = await db.get_user_location(message.chat.id)
    if current_location:
        pass
    else:
        await db.set_user_location(message.chat.id, location)


@dp.callback_query_handler(
    lambda query: query.data.startswith("current_weather_location")
)
async def current_weather_location(callback_query: types.CallbackQuery):
    query_data = callback_query.data.split("_")
    if len(query_data) > 3:
        lon = query_data[4]
        lat = query_data[6]
        units = await db.get_user_metric(callback_query.message.chat.id)
        params = {
            "lat": lat,
            "lon": lon,
            "units": WEATHER_UNITS[units][0],
            "APPID": OWM_TOKEN,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url=OWM_API_URL_WEATHER, params=params) as response:
                r = await response.json()
        img = await get_img_weather_url(
            r["name"],
            str(round(r["main"]["temp"])),
            str(r["weather"][0]["id"]),
            WEATHER_UNITS[units][1],
        )
        caption = (
            "Current temp in {city} is {degrees:.0f} {metric} \n"
            "*{description}*\n"
            "Feels like {feels} {metric}".format(
                city=r["name"],
                degrees=r["main"]["temp"],
                metric=WEATHER_UNITS[units][1],
                description=r["weather"][0]["description"].capitalize(),
                feels=round(r["main"]["feels_like"]),
            )
        )

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(
                text="Details",
                callback_data=details_cb.new(
                    lat=r["coord"]["lat"], lon=r["coord"]["lon"], city=r["name"]
                ),
            )
        )

        await bot.send_photo(
            chat_id=callback_query.message.chat.id,
            photo=img["url"],
            caption=caption,
            parse_mode="markdown",
            reply_markup=kb,
        )
    else:
        await LocationForm.location.set()
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Send location",
        )
    return await bot.answer_callback_query(callback_query_id=callback_query.id)


@dp.message_handler(state=LocationForm.location, content_types=["location"])
async def process_geo(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data["location"] = message.location
    await state.finish()

    lat = message.location.latitude
    lon = message.location.longitude
    units = await db.get_user_metric(message.chat.id)
    params = {
        "lat": lat,
        "lon": lon,
        "units": WEATHER_UNITS[units][0],
        "APPID": OWM_TOKEN,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url=OWM_API_URL_WEATHER, params=params) as response:
            r = await response.json()

    img = await get_img_weather_url(
        r["name"],
        str(round(r["main"]["temp"])),
        str(r["weather"][0]["id"]),
        WEATHER_UNITS[units][1],
    )
    caption = (
        "Current temp in {city} is {degrees:.0f} {metric} \n"
        "*{description}*\n"
        "Feels like {feels} {metric}".format(
            city=r["name"],
            degrees=r["main"]["temp"],
            metric=WEATHER_UNITS[units][1],
            description=r["weather"][0]["description"].capitalize(),
            feels=round(r["main"]["feels_like"]),
        )
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="Details",
            callback_data=details_cb.new(
                lat=r["coord"]["lat"], lon=r["coord"]["lon"], city=r["name"]
            ),
        )
    )

    await bot.send_photo(
        chat_id=message.chat.id,
        photo=img["url"],
        caption=caption,
        parse_mode="markdown",
        reply_markup=kb,
    )

    location = {"lat": str(lat), "lon": str(lon), "city": r["name"]}
    await db.set_user_location(message.chat.id, location)


@dp.callback_query_handler(details_cb.filter())
async def weather_details(callback_query: types.CallbackQuery, callback_data: dict):
    lat = callback_data["lat"]
    lon = callback_data["lon"]
    city = callback_data["city"]

    units = await db.get_user_metric(callback_query.message.chat.id)
    params = {
        "lat": lat,
        "lon": lon,
        "units": WEATHER_UNITS[units][0],
        "exclude": "minutly,hourly",
        "appid": OWM_TOKEN,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url=OWM_API_ONECALL_URL_FORECAST, params=params
        ) as response:
            r = await response.json()

    if r["current"]["uvi"] > 2:
        uvi_description = "*UV index is heightended*"
    else:
        uvi_description = ""

    if r["current"]["wind_speed"] <= 5:
        wind_speed_description = "(Gentle breeze)"
    elif r["current"]["wind_speed"] <= 8:
        wind_speed_description = "(Moderate breeze)"
    elif r["current"]["wind_speed"] <= 11:
        wind_speed_description = "(Fresh breeze)"
    else:
        wind_speed_description = "*Strong breeze*"

    brief = (
        "Current temp in {city} is {degrees:.0f} {metric} \n"
        "*{description}*\n"
        "Feels like {feels} {metric}".format(
            city=city,
            degrees=r["current"]["temp"],
            metric=WEATHER_UNITS[units][1],
            description=r["current"]["weather"][0]["description"].capitalize(),
            feels=r["current"]["feels_like"],
        )
    )
    details = (
        "\nPressure: {pressure} hPa\n"
        "Humidity: {humidity}%\n"
        "UV index: {uvi} {uvi_description}\n"
        "Wind speed: {wind_speed}m/s {wind_speed_description}".format(
            pressure=r["current"]["pressure"],
            humidity=r["current"]["humidity"],
            uvi=r["current"]["uvi"],
            uvi_description=uvi_description,
            wind_speed=r["current"]["wind_speed"],
            wind_speed_description=wind_speed_description,
        )
    )

    new_caption = brief + details
    await bot.edit_message_caption(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        caption=new_caption,
        parse_mode="markdown",
    )
    return await bot.answer_callback_query(callback_query_id=callback_query.id)


@dp.message_handler(text=["Settings"])
async def settings(message: types.Message):
    kb = types.InlineKeyboardMarkup()
    user_location = await db.get_user_location(message.chat.id)
    metric = await db.get_user_metric(message.chat.id)
    if user_location:
        location = json.loads(user_location)
        location_text = "Your saved location: {city}({lat}, {lon})\n".format(
            city=location["city"], lat=location["lat"], lon=location["lon"]
        )
        kb.add(
            types.InlineKeyboardButton(
                text="Change location",
                callback_data="change_location",
            )
        )
    else:
        location_text = "You don't have any saved location.\n"
        kb.add(
            types.InlineKeyboardButton(
                text="Add saved location",
                callback_data="add_location",
            )
        )
    metric_text = "Your current weather units: {metric} ({sign})\n".format(
        metric=WEATHER_UNITS[metric][0], sign=WEATHER_UNITS[metric][1]
    )
    msg_text = location_text + metric_text
    if user_location:
        kb.add(
            types.InlineKeyboardButton(
                text="Change metric ({sign})".format(sign=WEATHER_UNITS[metric][1]),
                callback_data=metric_cb.new(
                    city=location["city"],
                    lat=location["lat"],
                    lon=location["lon"],
                    metric=metric,
                ),
            )
        )
    else:
        kb.add(
            types.InlineKeyboardButton(
                text="Change metric ({sign})".format(sign=WEATHER_UNITS[metric][1]),
                callback_data=metric_cb.new(
                    metric=metric, city="None", lon="None", lat="None"
                ),
            )
        )
    return await message.answer(
        text=msg_text,
        reply_markup=kb,
    )


@dp.callback_query_handler(
    lambda query: query.data.startswith("change_location")
    or query.data.startswith("add_location")
)
async def change_location(callback_query: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="Send location",
            callback_data="change_weather_location",
        )
    )
    kb.add(
        types.InlineKeyboardButton(
            text="Type city",
            callback_data="change_weather_city",
        )
    )
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Choose option to set new location",
        reply_markup=kb,
    )
    return await bot.answer_callback_query(callback_query_id=callback_query.id)


@dp.callback_query_handler(lambda query: query.data.startswith("change_weather_city"))
async def change_weather_city(callback_query: types.CallbackQuery):
    await CitySaveForm.city.set()
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Type city",
    )
    return await bot.answer_callback_query(callback_query_id=callback_query.id)


@dp.message_handler(state=CitySaveForm.city)
async def process_change_city(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data["city"] = message.text
    await state.finish()

    s_city = data["city"]
    params = {"q": s_city, "type": "like", "APPID": OWM_TOKEN}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url=OWM_API_URL_FIND, params=params) as response:
                r = await response.json()

        city = r["list"][0]
    except IndexError:
        return await bot.send_message(
            chat_id=message.chat.id, text="Sorry, no city found"
        )

    location = {
        "lat": str(city["coord"]["lat"]),
        "lon": str(city["coord"]["lon"]),
        "city": city["name"],
    }
    await db.set_user_location(message.chat.id, location)
    await message.reply(
        text="Your location was successfully saved. You can check all your settings with Settings button in menu.",
    )


@dp.callback_query_handler(
    lambda query: query.data.startswith("change_weather_location")
)
async def change_weather_location(callback_query: types.CallbackQuery):
    await LocationSaveForm.location.set()
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Send location",
    )
    return await bot.answer_callback_query(callback_query_id=callback_query.id)


@dp.message_handler(state=LocationSaveForm.location, content_types=["location"])
async def change_geo(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data["location"] = message.location
    await state.finish()

    lat = message.location.latitude
    lon = message.location.longitude
    params = {"lat": lat, "lon": lon, "APPID": OWM_TOKEN}

    async with aiohttp.ClientSession() as session:
        async with session.get(url=OWM_API_URL_WEATHER, params=params) as response:
            r = await response.json()

    location = {"lat": str(lat), "lon": str(lon), "city": r["name"]}
    await db.set_user_location(message.chat.id, location)
    await message.reply(
        text="Your location was successfully saved. You can check all your settings with Settings button in menu.",
    )


@dp.callback_query_handler(metric_cb.filter())
async def change_metric(callback_query: types.CallbackQuery, callback_data: dict):
    await db.change_user_metric(callback_query.message.chat.id)
    if callback_data["metric"] == "celsius":
        metric = "fahrenheit"
    else:
        metric = "celsius"
    kb = types.InlineKeyboardMarkup()

    if callback_data["city"] == "None":
        location_text = "You don't have any saved location.\n"
        kb.add(
            types.InlineKeyboardButton(
                text="Add saved location",
                callback_data="add_location",
            )
        )
    else:
        location_text = "Your saved location: {city}({lat}, {lon})\n".format(
            city=callback_data["city"],
            lat=callback_data["lat"],
            lon=callback_data["lon"],
        )
        kb.add(
            types.InlineKeyboardButton(
                text="Change location",
                callback_data="change_location",
            )
        )
    metric_text = "Your current weather units: {metric} ({sign})\n".format(
        metric=WEATHER_UNITS[metric][0], sign=WEATHER_UNITS[metric][1]
    )
    msg_text = location_text + metric_text
    if callback_data["city"] == "None":
        kb.add(
            types.InlineKeyboardButton(
                text="Change metric ({sign})".format(sign=WEATHER_UNITS[metric][1]),
                callback_data=metric_cb.new(
                    city="None", lat="None", lon="None", metric=metric
                ),
            )
        )
    else:
        kb.add(
            types.InlineKeyboardButton(
                text="Change metric ({sign})".format(sign=WEATHER_UNITS[metric][1]),
                callback_data=metric_cb.new(
                    city=callback_data["city"],
                    lat=callback_data["lat"],
                    lon=callback_data["lon"],
                    metric=metric,
                ),
            )
        )
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=msg_text,
        reply_markup=kb,
    )
    return await bot.answer_callback_query(callback_query_id=callback_query.id)


@dp.message_handler(text=["Weather forecast"])
async def weather_forecast(message: types.Message):

    kb = types.InlineKeyboardMarkup()
    user_location = await db.get_user_location(message.chat.id)
    if user_location:
        location = json.loads(user_location)
        kb.add(
            types.InlineKeyboardButton(
                text="Current location",
                callback_data="forecast_location_lon_"
                + location["lon"]
                + "_lat_"
                + location["lat"],
            )
        )
        kb.add(
            types.InlineKeyboardButton(
                text="Another city",
                callback_data="forecast_city",
            )
        )
    else:
        kb.add(
            types.InlineKeyboardButton(
                text="Send location",
                callback_data="forecast_location",
            )
        )
        kb.add(
            types.InlineKeyboardButton(
                text="Type city",
                callback_data="forecast_city",
            )
        )
    await message.answer(
        "Choose option",
        reply_markup=kb,
    )


@dp.callback_query_handler(lambda query: query.data.startswith("forecast_location"))
async def forecast_location(callback_query: types.CallbackQuery):
    query_data = callback_query.data.split("_")
    if len(query_data) > 2:

        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Preparing your weather forecast...",
        )
        await bot.answer_callback_query(callback_query_id=callback_query.id)

        lon = query_data[3]
        lat = query_data[5]
        units = await db.get_user_metric(callback_query.message.chat.id)
        params = {
            "lat": lat,
            "lon": lon,
            "units": WEATHER_UNITS[units][0],
            "exclude": "minutly,hourly",
            "appid": OWM_TOKEN,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url=OWM_API_ONECALL_URL_FORECAST, params=params
            ) as response:
                r = await response.json()

        forecast_imgs = []
        for index, day in enumerate(r["daily"]):
            if index == 7:
                break
            time = datetime.datetime.fromtimestamp(int(day["dt"]))
            img = await get_img_weather_url(
                weather=str(round(day["temp"]["day"])),
                city=f"{time:%Y-%m-%d}",
                weather_id=str(day["weather"][0]["id"]),
                metric=WEATHER_UNITS[units][1],
            )
            forecast_imgs.append(img["url"])

        img = await concat_imgs_by_urls(forecast_imgs, bg_color=(134, 185, 224))

        bio = BytesIO()
        bio.name = str(callback_query.message.chat.id) + ".png"
        img.save(bio, "PNG")
        bio.seek(0)

        alerts = ""
        if "alerts" in r:
            caption = "*National alerts*:\n"
            for alert in r["alerts"]:
                start = datetime.datetime.fromtimestamp(int(alert["start"]))
                end = datetime.datetime.fromtimestamp(int(alert["end"]))
                alerts = alerts + "{start} - {end}:\n {description}\n".format(
                    start=f"{start:%m-%d %H:%M:%S}",
                    end=f"{end:%m-%d %H:%M:%S}",
                    description=alert["description"].replace("*", "\\*"),
                )
            alerts = caption + alerts
        await bot.send_photo(
            chat_id=callback_query.message.chat.id,
            photo=bio,
            caption=alerts,
            parse_mode="markdown",
        )
        bio.close()
        await bot.delete_message(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
        )
    else:
        await ForecastLocationForm.location.set()
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Send location",
        )


@dp.message_handler(state=ForecastLocationForm.location, content_types=["location"])
async def forecast_location_new(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data["location"] = message.location
    await state.finish()

    lat = message.location.latitude
    lon = message.location.longitude

    await bot.send_message(
        text="Preparing your weather forecast...", chat_id=message.chat.id
    )

    units = await db.get_user_metric(message.chat.id)
    params = {
        "lat": lat,
        "lon": lon,
        "units": WEATHER_UNITS[units][0],
        "exclude": "minutly,hourly",
        "appid": OWM_TOKEN,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url=OWM_API_ONECALL_URL_FORECAST, params=params
        ) as response:
            r = await response.json()

    forecast_imgs = []
    for index, day in enumerate(r["daily"]):
        if index == 7:
            break
        time = datetime.datetime.fromtimestamp(int(day["dt"]))
        img = await get_img_weather_url(
            weather=str(round(day["temp"]["day"])),
            city=f"{time:%Y-%m-%d}",
            weather_id=str(day["weather"][0]["id"]),
            metric=WEATHER_UNITS[units][1],
        )
        forecast_imgs.append(img["url"])

    img = await concat_imgs_by_urls(forecast_imgs, bg_color=(134, 185, 224))

    bio = BytesIO()
    bio.name = str(message.chat.id) + ".png"
    img.save(bio, "PNG")
    bio.seek(0)

    alerts = ""
    if "alerts" in r:
        caption = "*National alerts*:\n"
        for alert in r["alerts"]:
            start = datetime.datetime.fromtimestamp(int(alert["start"]))
            end = datetime.datetime.fromtimestamp(int(alert["end"]))
            alerts = alerts + "{start} - {end}:\n {description}\n".format(
                start=f"{start:%m-%d %H:%M:%S}",
                end=f"{end:%m-%d %H:%M:%S}",
                description=alert["description"].replace("*", "\\*"),
            )
        alerts = caption + alerts
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=bio,
        caption=alerts,
        parse_mode="markdown",
    )
    bio.close()
    await bot.delete_message(
        chat_id=message.chat.id,
        message_id=message.message_id + 1,
    )

    location = {"lat": str(lat), "lon": str(lon), "city": r["timezone"]}
    await db.set_user_location(message.chat.id, location)


@dp.callback_query_handler(lambda query: query.data.startswith("forecast_city"))
async def forecast_city(callback_query: types.CallbackQuery):
    await ForecastCityForm.city.set()
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Type city",
    )
    return await bot.answer_callback_query(callback_query_id=callback_query.id)


@dp.message_handler(state=ForecastCityForm.city)
async def forecast_city_process(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data["city"] = message.text
    await state.finish()

    await bot.send_message(
        text="Preparing your weather forecast...", chat_id=message.chat.id
    )

    units = await db.get_user_metric(message.chat.id)
    params = {
        "q": data["city"],
        "type": "like",
        "units": WEATHER_UNITS[units][0],
        "APPID": OWM_TOKEN,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url=OWM_API_URL_FIND, params=params) as response:
                r = await response.json()

        city = r["list"][0]
    except IndexError:
        await bot.delete_message(
            chat_id=message.chat.id,
            message_id=message.message_id + 1,
        )
        return await bot.send_message(
            chat_id=message.chat.id, text="Sorry, no city found"
        )

    params = {
        "lat": city["coord"]["lat"],
        "lon": city["coord"]["lon"],
        "units": WEATHER_UNITS[units][0],
        "exclude": "minutly,hourly",
        "appid": OWM_TOKEN,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url=OWM_API_ONECALL_URL_FORECAST, params=params
        ) as response:
            r = await response.json()

    forecast_imgs = []
    for index, day in enumerate(r["daily"]):
        if index == 7:
            break
        time = datetime.datetime.fromtimestamp(int(day["dt"]))
        img = await get_img_weather_url(
            weather=str(round(day["temp"]["day"])),
            city=f"{time:%Y-%m-%d}",
            weather_id=str(day["weather"][0]["id"]),
            metric=WEATHER_UNITS[units][1],
        )
        forecast_imgs.append(img["url"])

    img = await concat_imgs_by_urls(forecast_imgs, bg_color=(134, 185, 224))

    bio = BytesIO()
    bio.name = str(message.chat.id) + ".png"
    img.save(bio, "PNG")
    bio.seek(0)

    alerts = ""
    if "alerts" in r:
        caption = "*National alerts*:\n"
        for alert in r["alerts"]:
            start = datetime.datetime.fromtimestamp(int(alert["start"]))
            end = datetime.datetime.fromtimestamp(int(alert["end"]))
            alerts = alerts + "{start} - {end}:\n {description}\n".format(
                start=f"{start:%m-%d %H:%M:%S}",
                end=f"{end:%m-%d %H:%M:%S}",
                description=alert["description"].replace("*", "\\*"),
            )
        alerts = caption + alerts
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=bio,
        caption=alerts,
        parse_mode="markdown",
    )
    bio.close()
    await bot.delete_message(
        chat_id=message.chat.id,
        message_id=message.message_id + 1,
    )

    location = {
        "lat": str(city["coord"]["lat"]),
        "lon": str(city["coord"]["lat"]),
        "city": city["name"],
    }
    await db.set_user_location(message.chat.id, location)


if __name__ == "__main__":
    executor.start_polling(dp)
