from Pyjo.MCP.Server import Server
from Pyjo.MCP.Tool import Error
from Pyjoyment.Lite import *

from typing import Annotated, TypedDict


# A server of MCP as a gateway to the weather of Open-Meteo, which needs no key, for a client as Claude Code:
#
#   uv run python examples/weather.py daemon -l http://127.0.0.1:3000
#   claude mcp add --transport http weather http://127.0.0.1:3000/mcp
GEOCODING = 'https://geocoding-api.open-meteo.com/v1/search'
FORECAST = 'https://api.open-meteo.com/v1/forecast'

# The weather codes of the WMO, as Open-Meteo gives them
CONDITIONS = {
    0: 'Clear sky',
    1: 'Mainly clear',
    2: 'Partly cloudy',
    3: 'Overcast',
    45: 'Fog',
    48: 'Depositing rime fog',
    51: 'Light drizzle',
    53: 'Moderate drizzle',
    55: 'Dense drizzle',
    56: 'Light freezing drizzle',
    57: 'Dense freezing drizzle',
    61: 'Slight rain',
    63: 'Moderate rain',
    65: 'Heavy rain',
    66: 'Light freezing rain',
    67: 'Heavy freezing rain',
    71: 'Slight snow fall',
    73: 'Moderate snow fall',
    75: 'Heavy snow fall',
    77: 'Snow grains',
    80: 'Slight rain showers',
    81: 'Moderate rain showers',
    82: 'Violent rain showers',
    85: 'Slight snow showers',
    86: 'Heavy snow showers',
    95: 'Thunderstorm',
    96: 'Thunderstorm with slight hail',
    99: 'Thunderstorm with heavy hail',
}

server = Server(
    name='weather',
    version='1.0.0',
    instructions='The weather of Open-Meteo: find a place first when its name is ambiguous, then use its country code.',
)


class Place(TypedDict):
    """A place of the geocoding of Open-Meteo."""

    name: str
    country: str
    country_code: str
    region: str
    latitude: float
    longitude: float
    timezone: str


class Current(TypedDict):
    """The weather in a place now."""

    place: Place
    time: str
    conditions: str
    temperature: Annotated[float, 'Temperature in °C']
    apparent_temperature: Annotated[float, 'Apparent temperature in °C']
    humidity: Annotated[float, 'Relative humidity in %']
    wind_speed: Annotated[float, 'Wind speed in km/h']


class Day(TypedDict):
    """The weather in a place on a day."""

    date: str
    conditions: str
    temperature_max: Annotated[float, 'Maximum temperature in °C']
    temperature_min: Annotated[float, 'Minimum temperature in °C']
    precipitation: Annotated[float, 'Precipitation in mm']


class Forecast(TypedDict):
    """The weather in a place on the next days."""

    place: Place
    days: list[Day]


class Hour(TypedDict):
    """The weather in a place in an hour."""

    time: str
    conditions: str
    temperature: Annotated[float, 'Temperature in °C']
    apparent_temperature: Annotated[float, 'Apparent temperature in °C']
    precipitation_probability: Annotated[float, 'Probability of precipitation in %']
    precipitation: Annotated[float, 'Precipitation in mm']
    wind_speed: Annotated[float, 'Wind speed in km/h']


class HourlyForecast(TypedDict):
    """The weather in a place in the next hours."""

    place: Place
    hours: list[Hour]


async def get(url, **query):
    # A request of the API, non-blocking, with the user agent of the application
    tx = await app.ua.get_p(url, form=query)
    if (res := tx.result).is_error:
        raise Error.new(f'Open-Meteo answered {res.code}: {res.json("/reason") or res.message}')
    return res.json()


async def places(name, count=5, country=None, language='en'):
    # The most populous places first, as the search ranks a historic district of Ohio before the capital of Poland
    query = {'name': name, 'count': max(count, 10), 'language': language, 'format': 'json'}
    if country:
        query['countryCode'] = country
    found = (await get(GEOCODING, **query)).get('results') or []
    found = sorted(found, key=lambda place: place.get('population') or 0, reverse=True)[:count]
    if not found:
        raise Error.new(f'No place named {name}' + (f' in {country}' if country else ''))
    return [
        Place(
            name=place['name'],
            country=place.get('country', ''),
            country_code=place.get('country_code', ''),
            region=place.get('admin1', ''),
            latitude=place['latitude'],
            longitude=place['longitude'],
            timezone=place.get('timezone', ''),
        )
        for place in found
    ]


@server.tool(title='Find places', annotations={'readOnlyHint': True, 'openWorldHint': True})
async def find_places(
    name: str, count: Annotated[int, {'minimum': 1, 'maximum': 20}] = 5, language: str = 'en'
) -> list[Place]:
    """Find the places of a name, with their countries and regions, to tell apart the places of the same name.

    :param name: Name of a place, as a city, in the language of language.
    :param count: How many places at most.
    :param language: ISO 639-1 code of the language of the name and of the results, as pl.
    """
    return await places(name, count, language=language)


@server.tool(title='Current weather', annotations={'readOnlyHint': True, 'openWorldHint': True})
async def current_weather(place: str, country: str | None = None, language: str = 'en') -> Current:
    """The weather in a place now.

    :param place: Name of a place, as a city, in the language of language.
    :param country: ISO 3166-1 alpha-2 code of the country of the place, as PL.
    :param language: ISO 639-1 code of the language of the name, as pl.
    """
    found = (await places(place, 1, country, language))[0]
    fields = 'temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code'
    query = {'latitude': found['latitude'], 'longitude': found['longitude'], 'current': fields, 'timezone': 'auto'}
    now = (await get(FORECAST, **query))['current']
    return Current(
        place=found,
        time=now['time'],
        conditions=CONDITIONS.get(now['weather_code'], 'Unknown'),
        temperature=now['temperature_2m'],
        apparent_temperature=now['apparent_temperature'],
        humidity=now['relative_humidity_2m'],
        wind_speed=now['wind_speed_10m'],
    )


@server.tool(title='Weather forecast', annotations={'readOnlyHint': True, 'openWorldHint': True})
async def forecast(
    place: str,
    days: Annotated[int, {'minimum': 1, 'maximum': 16}] = 3,
    country: str | None = None,
    language: str = 'en',
) -> Forecast:
    """The weather in a place on the next days, from today.

    :param place: Name of a place, as a city, in the language of language.
    :param days: How many days.
    :param country: ISO 3166-1 alpha-2 code of the country of the place, as PL.
    :param language: ISO 639-1 code of the language of the name, as pl.
    """
    found = (await places(place, 1, country, language))[0]
    fields = 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum'
    query = {
        'latitude': found['latitude'],
        'longitude': found['longitude'],
        'daily': fields,
        'forecast_days': days,
        'timezone': 'auto',
    }
    daily = (await get(FORECAST, **query))['daily']
    return Forecast(
        place=found,
        days=[
            Day(
                date=date,
                conditions=CONDITIONS.get(code, 'Unknown'),
                temperature_max=high,
                temperature_min=low,
                precipitation=rain,
            )
            for date, code, high, low, rain in zip(
                daily['time'],
                daily['weather_code'],
                daily['temperature_2m_max'],
                daily['temperature_2m_min'],
                daily['precipitation_sum'],
                strict=True,
            )
        ],
    )


@server.tool(title='Hourly weather forecast', annotations={'readOnlyHint': True, 'openWorldHint': True})
async def hourly_forecast(
    place: str,
    hours: Annotated[int, {'minimum': 1, 'maximum': 384}] = 24,
    country: str | None = None,
    language: str = 'en',
) -> HourlyForecast:
    """The weather in a place in the next hours, from the current hour, in the local time of the place.

    :param place: Name of a place, as a city, in the language of language.
    :param hours: How many hours.
    :param country: ISO 3166-1 alpha-2 code of the country of the place, as PL.
    :param language: ISO 639-1 code of the language of the name, as pl.
    """
    found = (await places(place, 1, country, language))[0]
    fields = 'temperature_2m,apparent_temperature,precipitation_probability,precipitation,weather_code,wind_speed_10m'
    query = {
        'latitude': found['latitude'],
        'longitude': found['longitude'],
        'hourly': fields,
        'forecast_hours': hours,
        'timezone': 'auto',
    }
    hourly = (await get(FORECAST, **query))['hourly']
    return HourlyForecast(
        place=found,
        hours=[
            Hour(
                time=time,
                conditions=CONDITIONS.get(code, 'Unknown'),
                temperature=temperature,
                apparent_temperature=apparent,
                precipitation_probability=probability,
                precipitation=rain,
                wind_speed=wind,
            )
            for time, temperature, apparent, probability, rain, code, wind in zip(
                hourly['time'],
                hourly['temperature_2m'],
                hourly['apparent_temperature'],
                hourly['precipitation_probability'],
                hourly['precipitation'],
                hourly['weather_code'],
                hourly['wind_speed_10m'],
                strict=True,
            )
        ],
    )


# Host and Origin of localhost only, against DNS rebinding
plugin('AllowedHosts')

any('/mcp', server.to_action())

app.start()
