import Pyjo.MCP.Test

from Pyjo.File import curfile
from Pyjo.Test import *


# The application of examples/weather.py, which the test loads without starting a server, and whose requests of
# Open-Meteo a mock of its routes answers, as the tests do not use the network
t = Pyjo.MCP.Test.new(curfile().dirname().dirname().sibling('examples', 'weather.py'))
t.app.log.level = 'fatal'


PLACES = {
    ('Warszawa', 'pl'): [
        {
            'name': 'Warszawa',
            'latitude': 48.84,
            'longitude': 37.61,
            'country': 'Ukraina',
            'country_code': 'UA',
            'admin1': 'obwód doniecki',
            'timezone': 'Europe/Kyiv',
            'population': 11162,
        },
        {
            'name': 'Warszawa',
            'latitude': 52.23,
            'longitude': 21.01,
            'country': 'Polska',
            'country_code': 'PL',
            'admin1': 'Województwo mazowieckie',
            'timezone': 'Europe/Warsaw',
            'population': 1702139,
        },
    ],
    ('Warsaw', 'en'): [
        {
            'name': 'Warsaw',
            'latitude': 52.23,
            'longitude': 21.01,
            'country': 'Poland',
            'country_code': 'PL',
            'admin1': 'Mazovia',
            'timezone': 'Europe/Warsaw',
            'population': 1702139,
        },
        {
            'name': 'Warsaw',
            'latitude': 41.24,
            'longitude': -85.85,
            'country': 'United States',
            'country_code': 'US',
            'admin1': 'Indiana',
            'timezone': 'America/Indiana/Indianapolis',
            'population': 14472,
        },
        {'name': 'Warsaw Historic District', 'latitude': 40.36, 'longitude': -91.43},
    ],
}
WARSAW = {
    'name': 'Warsaw',
    'country': 'Poland',
    'country_code': 'PL',
    'region': 'Mazovia',
    'latitude': 52.23,
    'longitude': 21.01,
    'timezone': 'Europe/Warsaw',
}
queries = []


@t.app.routes.get('/v1/search')
def search(c):
    queries.append(c.req.query_params.to_dict())
    found = PLACES.get((c.param('name'), c.param('language')), [])
    if c.param('countryCode'):
        found = [place for place in found if place.get('country_code') == c.param('countryCode')]
    c.render(json={'results': found[: int(c.param('count'))]} if found else {'generationtime_ms': 0.1})


@t.app.routes.get('/v1/forecast')
def forecast(c):
    queries.append(c.req.query_params.to_dict())
    if c.param('latitude') == '0':
        return c.render(json={'error': True, 'reason': 'Latitude must be in range of -90 to 90°.'}, status=400)
    if c.param('current'):
        current = {
            'time': '2026-10-24T20:30',
            'temperature_2m': 9.6,
            'relative_humidity_2m': 87,
            'apparent_temperature': 7.9,
            'wind_speed_10m': 7.2,
            'weather_code': 3,
        }
        return c.render(json={'current': current})
    if c.param('hourly'):
        hours = int(c.param('forecast_hours'))
        hourly = {
            'time': ['2026-10-24T20:00', '2026-10-24T21:00', '2026-10-24T22:00'][:hours],
            'temperature_2m': [10.0, 9.8, 9.4][:hours],
            'apparent_temperature': [8.2, 7.9, 7.4][:hours],
            'precipitation_probability': [0, 20, 65][:hours],
            'precipitation': [0.0, 0.0, 0.4][:hours],
            'weather_code': [3, 2, 61][:hours],
            'wind_speed_10m': [8.3, 9.0, 9.7][:hours],
        }
        return c.render(json={'hourly': hourly})
    days = int(c.param('forecast_days'))
    daily = {
        'time': ['2026-10-24', '2026-10-25', '2026-10-26'][:days],
        'weather_code': [51, 63, 999][:days],
        'temperature_2m_max': [10.3, 12.6, 11.0][:days],
        'temperature_2m_min': [7.0, 6.9, 5.5][:days],
        'precipitation_sum': [0.1, 1.7, 0.0][:days],
    }
    c.render(json={'daily': daily})


# The requests of Open-Meteo go to the routes of the mock, on the server of the user agent of the application
t.app.ua.server.app = t.app


@t.app.ua.on('start')
def start(ua, tx):
    url, base = tx.req.url, ua.server.nb_url()
    if url.host in ('geocoding-api.open-meteo.com', 'api.open-meteo.com'):
        url.scheme, url.host, url.port = base.scheme, base.host, base.port


def call(tool, /, **arguments):
    # A call of a tool, with the queries of the mock of its own
    queries.clear()
    return t.call_ok(tool, **arguments)


with subtest('Tools'):
    t.list_tools_ok().status_is(200)
    names = [tool['name'] for tool in t.response['result']['tools']]
    is_deeply_ok(names, ['find_places', 'current_weather', 'forecast', 'hourly_forecast'], 'tools')
    t.result_is('/tools/2/title', 'Weather forecast')
    t.result_is('/tools/2/annotations', {'readOnlyHint': True, 'openWorldHint': True})
    t.result_is(
        '/tools/2/inputSchema/properties/days',
        {'type': 'integer', 'minimum': 1, 'maximum': 16, 'default': 3, 'description': 'How many days.'},
    )
    t.result_is('/tools/2/inputSchema/required', ['place'])
    t.result_is(
        '/tools/2/outputSchema/properties/days/items/properties/precipitation',
        {'type': 'number', 'description': 'Precipitation in mm'},
    )

with subtest('Places'):
    call('find_places', name='Warsaw').status_is(200).is_error_is(False)
    t.structured_content_is('/0', WARSAW)
    t.structured_content_is('/1/region', 'Indiana')
    t.result_is(
        '/structuredContent/2',
        {
            'name': 'Warsaw Historic District',
            'country': '',
            'country_code': '',
            'region': '',
            'latitude': 40.36,
            'longitude': -91.43,
            'timezone': '',
        },
    )
    is_deeply_ok(queries, [{'name': 'Warsaw', 'count': '10', 'language': 'en', 'format': 'json'}], 'query')
    call('find_places', name='Warszawa', count=1, language='pl').status_is(200)
    t.structured_content_is('/0/country', 'Polska', 'most populous first')
    t.json_hasnt('/result/structuredContent/1')
    call('find_places', name='Nowhere').status_is(200).is_error_is(True)
    t.text_content_is('No place named Nowhere')
    call('find_places', name='Warsaw', count=21).status_is(200).is_error_is(True)

with subtest('Current weather'):
    call('current_weather', place='Warsaw').status_is(200).is_error_is(False)
    t.result_is(
        '/structuredContent',
        {
            'place': WARSAW,
            'time': '2026-10-24T20:30',
            'conditions': 'Overcast',
            'temperature': 9.6,
            'apparent_temperature': 7.9,
            'humidity': 87,
            'wind_speed': 7.2,
        },
    )
    current = 'temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code'
    is_deeply_ok(
        queries[1],
        {'latitude': '52.23', 'longitude': '21.01', 'current': current, 'timezone': 'auto'},
        'query of the forecast',
    )
    call('current_weather', place='Warsaw', country='US').status_is(200)
    t.structured_content_is('/place/region', 'Indiana')
    is_ok(queries[0]['countryCode'], 'US', 'country')
    call('current_weather', place='Warsaw', country='DE').status_is(200).is_error_is(True)
    t.text_content_is('No place named Warsaw in DE')

with subtest('Forecast'):
    call('forecast', place='Warszawa', language='pl').status_is(200).is_error_is(False)
    t.structured_content_is('/place/name', 'Warszawa')
    t.result_is(
        '/structuredContent/days',
        [
            {
                'date': '2026-10-24',
                'conditions': 'Light drizzle',
                'temperature_max': 10.3,
                'temperature_min': 7.0,
                'precipitation': 0.1,
            },
            {
                'date': '2026-10-25',
                'conditions': 'Moderate rain',
                'temperature_max': 12.6,
                'temperature_min': 6.9,
                'precipitation': 1.7,
            },
            {
                'date': '2026-10-26',
                'conditions': 'Unknown',
                'temperature_max': 11.0,
                'temperature_min': 5.5,
                'precipitation': 0.0,
            },
        ],
    )
    is_ok(queries[1]['forecast_days'], '3', 'three days by default')
    call('forecast', place='Warsaw', days=1).status_is(200).structured_content_is('/days/0/date', '2026-10-24')
    t.json_hasnt('/result/structuredContent/days/1')
    call('forecast', place='Warsaw', days=17).status_is(200).is_error_is(True)
    t.text_content_is('Invalid arguments:\n/days: Greater than the maximum 16.')

with subtest('Hourly forecast'):
    call('hourly_forecast', place='Warsaw', hours=3).status_is(200).is_error_is(False)
    t.structured_content_is('/place', WARSAW)
    t.result_is(
        '/structuredContent/hours/2',
        {
            'time': '2026-10-24T22:00',
            'conditions': 'Slight rain',
            'temperature': 9.4,
            'apparent_temperature': 7.4,
            'precipitation_probability': 65,
            'precipitation': 0.4,
            'wind_speed': 9.7,
        },
    )
    fields = 'temperature_2m,apparent_temperature,precipitation_probability,precipitation,weather_code,wind_speed_10m'
    is_deeply_ok(
        queries[1],
        {'latitude': '52.23', 'longitude': '21.01', 'hourly': fields, 'forecast_hours': '3', 'timezone': 'auto'},
        'query of the forecast',
    )
    call('hourly_forecast', place='Warsaw').status_is(200)
    is_ok(queries[1]['forecast_hours'], '24', 'a day by default')
    call('hourly_forecast', place='Warsaw', hours=385).status_is(200).is_error_is(True)
    t.text_content_is('Invalid arguments:\n/hours: Greater than the maximum 384.')

with subtest('Errors of Open-Meteo'):
    PLACES[('Null Island', 'en')] = [{'name': 'Null Island', 'latitude': 0, 'longitude': 0}]
    call('forecast', place='Null Island').status_is(200).is_error_is(True)
    t.text_content_is('Open-Meteo answered 400: Latitude must be in range of -90 to 90°.')

t.ua.close()

done_testing()
