import datetime
import json
import logging
from pathlib import Path
import sys
import unittest
from unittest import mock

cwd = Path().absolute()
sys.path.insert(1, str(cwd.parents[0] / Path('src') / Path('CxMGMTaC')))

# see https://stackoverflow.com/questions/15753390/how-can-i-mock-requests-and-the-response


from CheckmarxPythonSDK.CxRestAPISDK.config import config
config['base_url'] = 'http://localhost'
config['username'] = 'unittest'
config['password'] = '********'

logging.basicConfig(level=logging.DEBUG,
                    format='%(levelname)s | %(funcName)s: %(message)s')

CREATION_DATE = 'creationDate'
DATA = 'data'
FULL_NAME = 'fullName'
ID = 'id'
METHOD = 'method'
NAME = 'name'
PARENT_ID = 'parentId'
URL = 'url'


class MockCxSAST:

    responses_dir = Path('data') / Path('mock_responses')

    def __init__(self):

        self.init()

    def init(self):

        with open(self.responses_dir / Path('authentication_providers.json'),
                  'r') as f:
            self.authentication_providers = json.load(f)

        with open(self.responses_dir / Path('roles.json'), 'r') as f:
            self.roles = json.load(f)

        with open(self.responses_dir / Path('teams.json'), 'r') as f:
            self.teams = json.load(f)

        with open(self.responses_dir / Path('token.json'), 'r') as f:
            self.token = json.load(f)

        with open(self.responses_dir / Path('users.json'), 'r') as f:
            self.users = json.load(f)

        self.requests = []

    def handle_request(self, request):

        self.requests.append(request)
        if request[METHOD] == 'DELETE':
            return self.handle_DELETE(request)
        elif request[METHOD] == 'GET':
            return self.handle_GET(request)
        elif request[METHOD] == 'POST':
            return self.handle_POST(request)
        elif request[METHOD] == 'PUT':
            return self.handle_PUT(request)
        else:
            raise RuntimeError(f'{request[METHOD]}: unsupported method')

    def handle_DELETE(self, request):

        if request[URL].startswith('http://localhost/cxrestapi/auth/Teams/'):
            team_id = self.get_id_from_url(request[URL])
            count = len(self.teams)
            self.teams = [team for team in self.teams if team[ID] != team_id]
            if len(self.teams) != count:
                return (200, None)
            else:
                return (404, None)
        elif request[URL].startswith('http://localhost/cxrestapi/auth/Users'):
            user_id = self.get_id_from_url(request[URL])
            count = len(self.users)
            self.users = [user for user in self.users if user[ID] != user_id]
            if len(self.users) != count:
                return (200, None)
            else:
                return (404, None)
        else:
            return (404, None)

    def handle_GET(self, request):

        if request[URL] == 'http://localhost/cxrestapi/auth/AuthenticationProviders':
            return (200, self.authentication_providers)
        elif request[URL] == 'http://localhost/cxrestapi/auth/Users':
            return (200, self.users)
        elif request[URL] == 'http://localhost/cxrestapi/auth/Roles':
            return (200, self.roles)
        elif request[URL] == 'http://localhost/cxrestapi/auth/Teams':
            return (200, self.teams)
        elif request[URL].startswith('http://localhost/cxrestapi/auth/Users/'):
            user_id = self.get_id_from_url(request[URL])
            for user in self.users:
                if user[ID] == user_id:
                    return (200, user)
            return (404, None)
        else:
            return (404, None)

    def handle_POST(self, request):

        if request[URL] == 'http://localhost/cxrestapi/auth/identity/connect/token':
            return (200, self.token)
        elif request[URL] == 'http://localhost/cxrestapi/auth/Teams':
            team = json.loads(request[DATA])
            team[ID] = self.get_next_id(self.teams)
            team[CREATION_DATE] = f'{datetime.datetime.now()}Z'
            team[FULL_NAME] = self.generate_team_full_name(team)
            self.teams.append(team)
            return (201, None)
        elif request[URL] == 'http://localhost/cxrestapi/auth/Users':
            user = json.loads(request[DATA])
            user[ID] = self.get_next_id(self.users)
            self.users.append(user)
            return (201, None)
            return (201, None)
        else:
            return (404, None)

    def handle_PUT(self, request):

        if request[URL].startswith('http://localhost/cxrestapi/auth/Users/'):
            user_id = self.get_id_from_url(request[URL])
            for user in self.users:
                if user[ID] == user_id:
                    new_user = json.loads(request[DATA])
                    for key in new_user:
                        user[key] = new_user[key]
                return (200, None)
        else:
            return (404, None)

    def get_id_from_url(self, url):

        bits = url.split('/')
        return int(bits[-1])

    def get_next_id(self, items):

        next_id = max(item[ID] for item in items) + 1
        print(f'next_id: {next_id}')
        return next_id

    def generate_team_full_name(self, team):

        for parent in self.teams:
            if parent[ID] == team[PARENT_ID]:
                return f'{parent[FULL_NAME]}/{team[NAME]}'

        raise RuntimeError(f'Cannot find parent team of {team}')


mockCxSAST = MockCxSAST()

def mocked_requests_request(*args, **kwargs):

    global request_list

    mock_responses_dir = Path('data') / Path('mock_responses')

    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    print(f'kwargs: {kwargs}')
    response_code, data = mockCxSAST.handle_request(kwargs)
    print(f'response_code: {response_code}, data: {data}')
    return MockResponse(data, response_code)


with mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request):
    import CxMGMTaC


class TestCxMGMTaC(unittest.TestCase):

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_retrieve_from_ac(self, mock_get):

        model = CxMGMTaC.Model.retrieve_from_access_control()
        self.assertEqual(8, len(model.teams))
        self.assertEqual(11, len(model.users))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_invalid_role(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("invalid_role"))
        errors = model.validate()
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.InvalidRole))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_invalid_authentication_provider_name(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("invalid_authentication_provider_name"))
        errors = model.validate()
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0],
                                   CxMGMTaC.InvalidAuthenticationProviderName))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_active(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_active"))
        errors = model.validate()
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUserProperty))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_email(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_email"))
        errors = model.validate()
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUserProperty))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_first_name(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_first_name"))
        errors = model.validate()
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUserProperty))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_last_name(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_last_name"))
        errors = model.validate()
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUserProperty))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_locale_id(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_locale_id"))
        errors = model.validate()
        print(f'errors: {errors}')
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUserProperty))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_no_team(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("no_team"))
        errors = model.validate()
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.NoTeam))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_default_authentication_provider_name(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("default_authentication_provider_name"))
        errors = model.validate()
        self.assertEqual(0, len(errors))
        self.assertEqual('Application', model.users.users[0].authentication_provider_name)

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_add_team(self, mock_get):

        self.update_common(Path("data") / Path("add_team"))
        self.assertEqual(4, len(mockCxSAST.requests),
                         'Expected exactly three requests')
        request = mockCxSAST.requests[2]
        self.assertEqual('POST', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Teams',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_add_team_with_user(self, mock_get):

        self.update_common(Path("data") / Path("add_team_with_user"))
        for req in mockCxSAST.requests:
            print(f'*** request: {req}')
        self.assertEqual(5, len(mockCxSAST.requests),
                         'Expected exactly four requests')
        request = mockCxSAST.requests[2]
        self.assertEqual('POST', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Teams',
                         request['url'])
        request = mockCxSAST.requests[4]
        self.assertEqual('PUT', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users/11019',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_add_user(self, mock_get):

        self.update_common(Path("data") / Path("add_user"))
        self.assertEqual(3, len(mockCxSAST.requests),
                         'Expected exactly three requests')
        request = mockCxSAST.requests[2]
        self.assertEqual('POST', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_delete_user(self, mock_get):

        self.update_common(Path("data") / Path("delete_user"))
        self.assertEqual(3, len(mockCxSAST.requests),
                         'Expected exactly three requests')
        request = mockCxSAST.requests[2]
        self.assertEqual('DELETE', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users/11019',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_update_user(self, mock_get):

        self.update_common(Path("data") / Path("update_user"))
        self.assertEqual(3, len(mockCxSAST.requests),
                         'Expected exactly three requests')
        request = mockCxSAST.requests[2]
        self.assertEqual('PUT', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users/11019',
                         request['url'])

    def update_common(self, path):

        old_model = CxMGMTaC.Model.retrieve_from_access_control()
        new_model = CxMGMTaC.Model.load(path)
        errors = new_model.validate()
        self.assertEqual(0, len(errors))
        old_model.apply_changes(new_model, False)

    def setUp(self):

        mockCxSAST.init()

if __name__ == '__main__':
    unittest.main()
