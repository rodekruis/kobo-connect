import requests
import urllib

class EspoAPIError(Exception):
    """An exception class for the client"""

def http_build_query(data):
    parents = list()
    pairs = dict()

    def renderKey(parents):
        depth, outStr = 0, ''
        for x in parents:
            s = "[%s]" if depth > 0 or isinstance(x, int) else "%s"
            outStr += s % str(x)
            depth += 1
        return outStr

    def r_urlencode(data):
        if isinstance(data, list) or isinstance(data, tuple):
            for i in range(len(data)):
                parents.append(i)
                r_urlencode(data[i])
                parents.pop()
        elif isinstance(data, dict):
            for key, value in data.items():
                parents.append(key)
                r_urlencode(value)
                parents.pop()
        else:
            pairs[renderKey(parents)] = str(data)

        return pairs
    return urllib.parse.urlencode(r_urlencode(data))

class EspoAPI:

    url_path = '/api/v1/'

    def __init__(self, url, api_key):
        self.url = url
        self.api_key = api_key
        self.status_code = None

    def request(self, method, action, params=None):
        if params is None:
            params = {}

        headers = {
        }

        headers['X-Api-Key'] = self.api_key

        kwargs = {
            'url': self.normalize_url(action),
            'headers': headers,
        }

        if method in ['POST', 'PATCH', 'PUT']:
            kwargs['json'] = params
        else:
            kwargs['url'] = kwargs['url'] + '?' + http_build_query(params)

        # print(kwargs['url'])
        print(kwargs)
        response = requests.request(method, **kwargs)

        self.status_code = response.status_code

        if self.status_code != 200:
            reason = self.parse_reason(response.headers)
            raise EspoAPIError(f'Wrong request, status code is {response.status_code}, reason is {reason}')

        data = response.content
        if not data:
            raise EspoAPIError('Wrong request, content response is empty')

        return response.json()

    def normalize_url(self, action):
        return self.url + self.url_path + action

    @staticmethod
    def parse_reason(headers):
        if 'X-Status-Reason' not in headers:
            return 'Unknown Error'

        return headers['X-Status-Reason']