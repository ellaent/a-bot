from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.callback_data import CallbackData

import psycopg2
import asyncio
import aiohttp
from db_utils import Database

import requests
import json
from io import BytesIO
import datetime

from config import TOKEN, OWM_TOKEN, HCTI_API_KEY, HCTI_API_USER_ID, HCTI_API_ENDPOINT
from bot_utils import OWM_API_URL_FIND, OWM_API_URL_WEATHER, OWM_API_ONECALL_URL_FORECAST, get_img_weather_url, WEATHER_UNITS, metric_cb

from test_concat_images import test_concat


bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
# conn = psycopg2.connect(dbname=DB_NAME, user=DB_USERNAME, password=DB_PASSWORD, host=DB_HOST)


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


@dp.message_handler(commands=['start'])
async def process_start_command(message: types.Message):
    user = await db.current_user(message.chat.id)
    if user:
        pass
    else:
        await db.add_user(message.chat.id)

    menu_buttons = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu_buttons.add(
        types.KeyboardButton(
            text="Current weather"
        ),
    )
    menu_buttons.add(
        types.KeyboardButton(
            text="Weather forecast"
        ),
    )
    menu_buttons.add(
        types.KeyboardButton(
            text="Settings"
        ),
    )
    await message.answer(
        text="Hello!",
        reply_markup=menu_buttons
    )


@dp.message_handler(commands=['help'])
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
                callback_data="current_weather_location_lon_" + location["lon"] + "_lat_" + location["lat"],
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


# cancels state handler: need to be done for all text messages with states
@dp.message_handler(state='*', commands=['cancel'])
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.finish()
    await message.reply('Cancelled.')


@dp.message_handler(state=CityForm.city)
async def process_city(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data['city'] = message.text
    await state.finish()

    s_city = data['city']
    units = await db.get_user_metric(message.chat.id)
    params={'q': s_city,
            'type': 'like',
            'units': WEATHER_UNITS[units][0],
            'APPID': OWM_TOKEN
            }

    async with aiohttp.ClientSession() as session:
        async with session.get(url=OWM_API_URL_FIND, params=params) as response:
            r = await response.json()

    city = r['list'][0]

    img = await get_img_weather_url(city['name'], str(round(city['main']['temp'])), str(city['weather'][0]['id']), WEATHER_UNITS[units][1])
    caption = "Current temp in {city} is {degrees:.0f} {metric} \n" \
              "*{description}*\n" \
              "Feels like {feels} {metric}".format(city=city['name'], degrees=city['main']['temp'],
                                                          metric = WEATHER_UNITS[units][1],
                                                          description = city['weather'][0]['description'].capitalize(),
                                                          feels=round(city['main']['feels_like']))

    await bot.send_photo(
        chat_id=message.chat.id,
        photo=img['url'],
        caption=caption,
        parse_mode="markdown"
    )

    location = {
        'lat': str(city['coord']['lat']),
        'lon': str(city['coord']['lon']),
        'city': city['name']
    }
    current_location = await db.get_user_location(message.chat.id)
    if current_location:
        pass
    else:
        await db.set_user_location(message.chat.id, location)


@dp.callback_query_handler(lambda query: query.data.startswith("current_weather_location"))
async def current_weather_location(callback_query: types.CallbackQuery):
    query_data = callback_query.data.split("_")
    if len(query_data) > 3:
        lon = query_data[4]
        lat = query_data[6]
        units = await db.get_user_metric(callback_query.message.chat.id)
        params = {
            'lat': lat,
            'lon': lon,
            'units': WEATHER_UNITS[units][0],
            'APPID': OWM_TOKEN
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url=OWM_API_URL_WEATHER, params=params) as response:
                r = await response.json()
        img = await get_img_weather_url(r['name'], str(round(r['main']['temp'])), str(r['weather'][0]['id']), WEATHER_UNITS[units][1])
        caption = "Current temp in {city} is {degrees:.0f} {metric} \n" \
                  "*{description}*\n" \
                  "Feels like {feels} {metric}".format(city=r['name'], degrees=r['main']['temp'],
                                                              metric = WEATHER_UNITS[units][1],
                                                              description=r['weather'][0][
                                                                  'description'].capitalize(),
                                                              feels=round(r['main']['feels_like']))

        await bot.send_photo(
            chat_id = callback_query.message.chat.id,
            photo = img['url'],
            caption = caption,
            parse_mode="markdown"
        )
    else:
        await LocationForm.location.set()
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Send location",
        )


@dp.message_handler(state=LocationForm.location, content_types=['location'])
async def process_geo(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data['location'] = message.location
    await state.finish()

    lat = message.location.latitude
    lon = message.location.longitude
    units = await db.get_user_metric(message.chat.id)
    params = {
        'lat': lat,
        'lon': lon,
        'units': WEATHER_UNITS[units][0],
        'APPID': OWM_TOKEN
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url=OWM_API_URL_WEATHER, params=params) as response:
            r = await response.json()

    img = await get_img_weather_url(r['name'], str(round(r['main']['temp'])), str(r['weather'][0]['id']), WEATHER_UNITS[units][1])
    caption = "Current temp in {city} is {degrees:.0f} {metric} \n" \
              "*{description}*\n" \
              "Feels like {feels} {metric}".format(city=r['name'], degrees=r['main']['temp'],
                                                   metric=WEATHER_UNITS[units][1],
                                                   description=r['weather'][0][
                                                       'description'].capitalize(),
                                                   feels=round(r['main']['feels_like']))

    await bot.send_photo(
        chat_id=message.chat.id,
        photo=img['url'],
        caption=caption,
        parse_mode="markdown"
    )

    location = {
        'lat': str(lat),
        'lon': str(lon),
        'city': r['name']
    }
    await db.set_user_location(message.chat.id, location)
    # await message.reply(f"Current temp in {r['name']}: " + str(r['main']['temp']) + u'\N{DEGREE SIGN}')


@dp.message_handler(text=["Settings"])
async def settings(message: types.Message):
    kb = types.InlineKeyboardMarkup()
    user_location = await db.get_user_location(message.chat.id)
    metric = await db.get_user_metric(message.chat.id)
    if user_location:
        location = json.loads(user_location)
        location_text = "Your saved location: {city}({lat}, {lon})\n".format(city = location['city'],
                                                                           lat = location['lat'],
                                                                           lon = location['lon'])
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
    metric_text = "Your current weather units: {metric} ({sign})\n".format(metric = WEATHER_UNITS[metric][0],
                                                                         sign = WEATHER_UNITS[metric][1])
    msg_text = location_text + metric_text
    if user_location:
        kb.add(
            types.InlineKeyboardButton(
                text="Change metric ({sign})".format(sign = WEATHER_UNITS[metric][1]),
                callback_data=metric_cb.new(
                    city=location['city'],
                    lat=location['lat'],
                    lon=location['lon'],
                    metric=metric
                ),
            )
        )
    else:
        kb.add(
            types.InlineKeyboardButton(
                text="Change metric ({sign})".format(sign=WEATHER_UNITS[metric][1]),
                callback_data=metric_cb.new(
                    metric=metric,
                    city='None',
                    lon='None',
                    lat='None'
                ),
            )
        )
    return await message.answer(
        text=msg_text,
        reply_markup=kb,
    )


@dp.callback_query_handler(lambda query: query.data.startswith("change_location"))
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
        reply_markup=kb
    )


@dp.callback_query_handler(lambda query: query.data.startswith("change_weather_city"))
async def change_weather_city(callback_query: types.CallbackQuery):
    await CitySaveForm.city.set()
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Type city",
    )


@dp.message_handler(state=CitySaveForm.city)
async def process_change_city(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data['city'] = message.text
    await state.finish()

    s_city = data['city']
    params = {'q': s_city,
              'type': 'like',
              'APPID': OWM_TOKEN
              }

    async with aiohttp.ClientSession() as session:
        async with session.get(url=OWM_API_URL_FIND, params=params) as response:
            r = await response.json()

    city = r['list'][0]
    location = {
        'lat': str(city['coord']['lat']),
        'lon': str(city['coord']['lon']),
        'city': city['name']
    }
    await db.set_user_location(message.chat.id, location)
    await message.reply(
        text="Your location was successfully saved. You can check all your settings with Settings button in menu.",
    )


@dp.callback_query_handler(lambda query: query.data.startswith("change_weather_location"))
async def change_weather_location(callback_query: types.CallbackQuery):
    await LocationSaveForm.location.set()
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Send location",
    )


@dp.message_handler(state=LocationSaveForm.location, content_types=['location'])
async def change_geo(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data['location'] = message.location
    await state.finish()

    lat = message.location.latitude
    lon = message.location.longitude
    params = {
        'lat': lat,
        'lon': lon,
        'APPID': OWM_TOKEN
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url=OWM_API_URL_WEATHER, params=params) as response:
            r = await response.json()

    location = {
        'lat': str(lat),
        'lon': str(lon),
        'city': r['name']
    }
    await db.set_user_location(message.chat.id, location)
    await message.reply(
        text="Your location was successfully saved. You can check all your settings with Settings button in menu.",
    )


@dp.callback_query_handler(metric_cb.filter())
async def change_metric(callback_query: types.CallbackQuery, callback_data: dict):
    await db.change_user_metric(callback_query.message.chat.id)
    if callback_data['metric'] == 'celsius':
        metric = 'fahrenheit'
    else:
        metric = 'celsius'
    kb = types.InlineKeyboardMarkup()

    if callback_data['city'] == 'None':
        location_text = "You don't have any saved location.\n"
        kb.add(
            types.InlineKeyboardButton(
                text="Add saved location",
                callback_data="add_location",
            )
        )
    else:
        location_text = "Your saved location: {city}({lat}, {lon})\n".format(city = callback_data['city'],
                                                                           lat = callback_data['lat'],
                                                                           lon = callback_data['lon'])
        kb.add(
            types.InlineKeyboardButton(
                text="Change location",
                callback_data="change_location",
            )
        )
    metric_text = "Your current weather units: {metric} ({sign})\n".format(metric = WEATHER_UNITS[metric][0],
                                                                         sign = WEATHER_UNITS[metric][1])
    msg_text = location_text + metric_text
    if callback_data['city'] == 'None':
        kb.add(
            types.InlineKeyboardButton(
                text="Change metric ({sign})".format(sign=WEATHER_UNITS[metric][1]),
                callback_data=metric_cb.new(
                    city='None',
                    lat='None',
                    lon='None',
                    metric=metric
                ),
            )
        )
    else:
        kb.add(
            types.InlineKeyboardButton(
                text="Change metric ({sign})".format(sign = WEATHER_UNITS[metric][1]),
                callback_data=metric_cb.new(
                    city=callback_data['city'],
                    lat=callback_data['lat'],
                    lon=callback_data['lon'],
                    metric=metric
                ),
            )
        )
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text = msg_text,
        reply_markup=kb
    )


@dp.message_handler(state='*', commands=['test'])
async def test_handler(message: types.Message, state: FSMContext):
    img = await test_concat("https://home.openweathermap.org/assets/logo_white-011958e697955be95bdc4af6a4d1913dbf9df990cb9101a67c439879293f5947.png")
    bio = BytesIO()
    bio.name = str(message.chat.id) + '.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    # bot.send_photo(chat_id, photo=bio)
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=bio,
        parse_mode="markdown"
    )
    bio.close()


@dp.message_handler(text=["Weather forecast"])
async def weather_forecast(message: types.Message):

    kb = types.InlineKeyboardMarkup()
    user_location = await db.get_user_location(message.chat.id)
    if user_location:
        location = json.loads(user_location)
        kb.add(
            types.InlineKeyboardButton(
                text="Current location",
                callback_data="forecast_location_lon_" + location["lon"] + "_lat_" + location["lat"],
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
            text="Preparing your weather forecast..."
        )

        lon = query_data[3]
        lat = query_data[5]
        units = await db.get_user_metric(callback_query.message.chat.id)
        params = {
            'lat': lat,
            'lon': lon,
            'units': WEATHER_UNITS[units][0],
            'exclude': 'minutly,hourly',
            'appid': OWM_TOKEN
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url=OWM_API_ONECALL_URL_FORECAST, params=params) as response:
                r = await response.json()
        print('one call done')

        city = r['timezone']
        forecast_imgs = []
        for index, day in enumerate(r['daily']):
            if index == 7:
                break
            time = datetime.datetime.fromtimestamp(int(day['dt']))
            img = await get_img_weather_url(weather=str(day['temp']['day']),
                                          city=f"{time:%Y-%m-%d}",
                                          weather_id=str(day['weather'][0]['id']),
                                          metric=WEATHER_UNITS[units][1]
                                          )
            forecast_imgs.append(img['url'])

        img = await test_concat(forecast_imgs)

        bio = BytesIO()
        bio.name = str(callback_query.message.chat.id) + '.png'
        img.save(bio, 'PNG')
        bio.seek(0)

        print(r)
        alerts = ""
        if 'alerts' in r:
            caption = "*National alerts*:\n"
            for alert in r['alerts']:
                start = datetime.datetime.fromtimestamp(int(alert['start']))
                end = datetime.datetime.fromtimestamp(int(alert['end']))
                alerts = alerts + "{start} - {end}:\n {description}\n".format(start = f"{start:%m-%d %H:%M:%S}",
                                                                          end = f"{end:%m-%d %H:%M:%S}",
                                                                          description = alert['description'].replace("*", "\\*")
                                                                          )
            alerts = caption + alerts
        await bot.send_photo(
            chat_id=callback_query.message.chat.id,
            photo=bio,
            caption=alerts,
            parse_mode="markdown"
        )
        bio.close()
        await bot.delete_message(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id
        )
    else:
        await ForecastLocationForm.location.set()
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Send location",
        )


if __name__ == '__main__':
    executor.start_polling(dp)