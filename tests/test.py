"""

Copyright 2022-2023 Checkmarx

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from collections import namedtuple
import datetime
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock
import yaml

cwd = Path().absolute()
sys.path.insert(1, str(cwd.parents[0] / Path('src') / Path('CxMGMTaC')))

# see https://stackoverflow.com/questions/15753390/how-can-i-mock-requests-and-the-response

Options = namedtuple('Options', ['data_dir', 'retrieve_user_entries', 'use_cxaudit_permission'])

from CheckmarxPythonSDK.CxRestAPISDK.config import config
config['base_url'] = 'http://localhost'
config['username'] = 'unittest'
config['password'] = '********'

# Set logging level
try:
    level_str = os.environ['LOG_LEVEL']
except KeyError:
    level_str = 'WARNING'
logging.basicConfig(level=logging.getLevelName(level_str),
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

        with open(self.responses_dir / Path('ldap_servers.json'), 'r') as f:
            self.ldap_servers = json.load(f)

        self.ldap_user_entries = {}
        for file in (self.responses_dir / Path('ldap_user_entries')).glob('*.json'):
            with open(file, 'r') as f:
                self.ldap_user_entries[file.stem] = json.load(f)

        with open(self.responses_dir / Path('roles.json'), 'r') as f:
            self.roles = json.load(f)

        with open(self.responses_dir / Path('server_license_data.json'), 'r') as f:
            self.server_license_data = json.load(f)

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
                return (204, None)
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
        elif request[URL].startswith('http://localhost/cxrestapi/auth/LDAPServers'):
            bits = request[URL].split('/')
            if len(bits) == 6:
                return (200, self.ldap_servers)
            elif len(bits) == 8 and bits[7].startswith('UserEntries'):
                ldap_server_id = int(bits[6])
                username_contains_pattern = bits[7]
                username = username_contains_pattern.split('=')[1]
                if ldap_server_id == 3 and username in self.ldap_user_entries:
                    return (200, self.ldap_user_entries[username])
                else:
                    return (200, [])
            else:
                return (404, None)
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
        elif request[URL] == 'http://localhost/cxrestapi/serverLicenseData':
            return (200, self.server_license_data)
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
                return (204, None)
        else:
            return (404, None)

    def get_id_from_url(self, url):

        bits = url.split('/')
        return int(bits[-1])

    def get_next_id(self, items):

        next_id = max(item[ID] for item in items) + 1
        logging.debug(f'next_id: {next_id}')
        return next_id

    def generate_team_full_name(self, team):

        for parent in self.teams:
            if parent[ID] == team[PARENT_ID]:
                return f'{parent[FULL_NAME]}/{team[NAME]}'

        raise RuntimeError(f'Cannot find parent team of {team}')


mockCxSAST = MockCxSAST()


def mocked_requests_request(*args, **kwargs):

    global request_list

    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    logging.debug(f'kwargs: {kwargs}')
    response_code, data = mockCxSAST.handle_request(kwargs)
    logging.debug(f'response_code: {response_code}, data: {data}')
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
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.InvalidRole))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_invalid_authentication_provider_name(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("invalid_authentication_provider_name"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0],
                                   CxMGMTaC.InvalidAuthenticationProviderName))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_active(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_active"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUserProperty))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_email(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_email"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUserProperty))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_first_name(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_first_name"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUserProperty))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_last_name(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_last_name"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUserProperty))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_locale_id(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_locale_id"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUserProperty))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_missing_user(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("missing_user"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.MissingUser))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_no_team(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("no_team"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.NoTeam))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_default_authentication_provider_name(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("default_authentication_provider_name"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(0, len(errors))
        self.assertEqual('Application', model.users.users[0].authentication_provider_name)

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_duplicate_team_full_name(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("duplicate_team_full_name"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_duplicate_user(self, mock_get):

        model = CxMGMTaC.Model.load(Path("data") / Path("duplicate_user"))
        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        errors = model.validate(options)
        self.assertEqual(1, len(errors))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_add_team(self, mock_get):

        self.update_common(Path("data") / Path("add_team"))
        self.assertEqual(5, len(mockCxSAST.requests),
                         'Expected exactly five requests')
        request = mockCxSAST.requests[3]
        self.assertEqual('POST', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Teams',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_add_team_with_user(self, mock_get):

        self.update_common(Path("data") / Path("add_team_with_user"))
        self.assertEqual(6, len(mockCxSAST.requests),
                         'Expected exactly six requests')
        request = mockCxSAST.requests[3]
        self.assertEqual('POST', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Teams',
                         request['url'])
        request = mockCxSAST.requests[5]
        self.assertEqual('PUT', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users/11019',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_delete_team_with_user(self, mock_get):

        self.update_common(Path("data") / Path("delete_team_with_user"))
        self.assertEqual(5, len(mockCxSAST.requests),
                         'Expected exactly five requests')
        request = mockCxSAST.requests[3]
        self.assertEqual('PUT', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users/5010',
                         request['url'])
        request = mockCxSAST.requests[4]
        self.assertEqual('DELETE', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Teams/2002',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_add_user(self, mock_get):

        self.update_common(Path("data") / Path("add_user"))
        self.assertEqual(4, len(mockCxSAST.requests),
                         'Expected exactly four requests')
        request = mockCxSAST.requests[3]
        self.assertEqual('POST', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_add_users(self, mock_get):

        self.update_common(Path("data") / Path("add_users"))
        self.assertEqual(5, len(mockCxSAST.requests),
                         'Expected exactly five requests')
        request = mockCxSAST.requests[3]
        self.assertEqual('POST', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users',
                         request['url'])
        request = mockCxSAST.requests[4]
        self.assertEqual('POST', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_delete_user(self, mock_get):

        self.update_common(Path("data") / Path("delete_user"))
        self.assertEqual(4, len(mockCxSAST.requests),
                         'Expected exactly four requests')
        request = mockCxSAST.requests[3]
        self.assertEqual('DELETE', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users/11019',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_delete_users(self, mock_get):

        self.update_common(Path("data") / Path("delete_users"))
        self.assertEqual(5, len(mockCxSAST.requests),
                         'Expected exactly five requests')
        request = mockCxSAST.requests[3]
        self.assertEqual('DELETE', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users/11019',
                         request['url'])
        request = mockCxSAST.requests[4]
        self.assertEqual('DELETE', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users/11015',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_update_user(self, mock_get):

        self.update_common(Path("data") / Path("update_user"))
        self.assertEqual(4, len(mockCxSAST.requests),
                         'Expected exactly four requests')
        request = mockCxSAST.requests[3]
        self.assertEqual('PUT', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/Users/11019',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_retrieve_user_entries(self, mock_get):
        '''Test the retrieval of user data from the LDAP server.'''

        options = Options('.', True, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        model = CxMGMTaC.Model.load(Path("data") / Path("retrieve_user_entries"))
        errors = model.validate(options)
        self.assertEqual(0, len(errors))
        with open(Path('users') / Path('users.yml'), 'r') as f:
            users = yaml.load(f, Loader=yaml.CLoader)
            found = False
            for user in users['users']:
                if (user['username'] == 'testuser'
                    and user['email'] == 'testuser@cxmgmtac.com'
                    and user['first_name'] == 'test'
                    and user['last_name'] == 'user'):
                    found = True
                    # The following have default values specified at
                    # the top-level of the users.yml file.
                    self.assertNotIn('active', user)
                    self.assertNotIn('locale_id', user)
                    break
        self.assertTrue(found, 'Could not find user in users.yml')
        shutil.rmtree('users')
        self.assertEqual(2, len(mockCxSAST.requests),
                         'Expected exactly two requests')
        request = mockCxSAST.requests[1]
        self.assertEqual('GET', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/LDAPServers/3/UserEntries?userNameContainsPattern=testuser',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_retrieve_user_entries_no_email(self, mock_get):
        '''Test the retrieval of user data from the LDAP server where
        the user does not have an email address.'''

        options = Options('.', True, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        model = CxMGMTaC.Model.load(Path("data") / Path("retrieve_user_entries_no_email"))
        errors = model.validate(options)
        self.assertEqual(0, len(errors))
        with open(Path('users') / Path('users.yml'), 'r') as f:
            users = yaml.load(f, Loader=yaml.CLoader)
            found = False
            for user in users['users']:
                if (user['username'] == 'noemail'
                    and user['email'] == 'noemail@CxMGMTaC'
                    and user['first_name'] == 'test'
                    and user['last_name'] == 'user'):
                    found = True
                    # The following have default values specified at
                    # the top-level of the users.yml file.
                    self.assertNotIn('active', user)
                    self.assertNotIn('locale_id', user)
                    break
        self.assertTrue(found, 'Could not find user in users.yml')
        shutil.rmtree('users')
        self.assertEqual(2, len(mockCxSAST.requests),
                         'Expected exactly two requests')
        request = mockCxSAST.requests[1]
        self.assertEqual('GET', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/LDAPServers/3/UserEntries?userNameContainsPattern=noemail',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_retrieve_user_entries_no_first_name(self, mock_get):
        '''Test the retrieval of user data from the LDAP server where
        the user does not have a first name.'''

        options = Options('.', True, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        model = CxMGMTaC.Model.load(Path("data") / Path("retrieve_user_entries_no_first_name"))
        errors = model.validate(options)
        self.assertEqual(0, len(errors))
        with open(Path('users') / Path('users.yml'), 'r') as f:
            users = yaml.load(f, Loader=yaml.CLoader)
            found = False
            for user in users['users']:
                if (user['username'] == 'nofirstname'
                    and user['email'] == 'nofirstname@cxmgmtac.com'
                    and user['first_name'] == 'nofirstname'
                    and user['last_name'] == 'user'):
                    found = True
                    # The following have default values specified at
                    # the top-level of the users.yml file.
                    self.assertNotIn('active', user)
                    self.assertNotIn('locale_id', user)
                    break
        self.assertTrue(found, 'Could not find user in users.yml')
        shutil.rmtree('users')
        self.assertEqual(2, len(mockCxSAST.requests),
                         'Expected exactly two requests')
        request = mockCxSAST.requests[1]
        self.assertEqual('GET', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/LDAPServers/3/UserEntries?userNameContainsPattern=nofirstname',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_retrieve_user_entries_no_last_name(self, mock_get):
        '''Test the retrieval of user data from the LDAP server where
        the user does not have a last name.'''

        options = Options('.', True, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        model = CxMGMTaC.Model.load(Path("data") / Path("retrieve_user_entries_no_last_name"))
        errors = model.validate(options)
        self.assertEqual(0, len(errors))
        with open(Path('users') / Path('users.yml'), 'r') as f:
            users = yaml.load(f, Loader=yaml.CLoader)
            found = False
            for user in users['users']:
                if (user['username'] == 'nolastname'
                    and user['email'] == 'nolastname@cxmgmtac.com'
                    and user['first_name'] == 'test'
                    and user['last_name'] == 'nolastname'):
                    found = True
                    # The following have default values specified at
                    # the top-level of the users.yml file.
                    self.assertNotIn('active', user)
                    self.assertNotIn('locale_id', user)
                    break
        self.assertTrue(found, 'Could not find user in users.yml')
        shutil.rmtree('users')
        self.assertEqual(2, len(mockCxSAST.requests),
                         'Expected exactly two requests')
        request = mockCxSAST.requests[1]
        self.assertEqual('GET', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/LDAPServers/3/UserEntries?userNameContainsPattern=nolastname',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_retrieve_missing_user_entries(self, mock_get):
        '''Test the retrieval of user data from the LDAP server where
        the user cannot be found.'''

        options = Options('.', True, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        model = CxMGMTaC.Model.load(Path("data") / Path("retrieve_missing_user_entries"))
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertEqual(2, len(mockCxSAST.requests),
                         'Expected exactly two requests')
        request = mockCxSAST.requests[1]
        self.assertEqual('GET', request['method'])
        self.assertEqual('http://localhost/cxrestapi/auth/LDAPServers/3/UserEntries?userNameContainsPattern=nosuchuser',
                         request['url'])

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_exceed_user_limit(self, mock_get):

        options = Options('.', False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        model = CxMGMTaC.Model.load(Path("data") / Path("exceed_user_limit"))
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.ExceedUserLimit))

    @mock.patch('CheckmarxPythonSDK.utilities.httpRequests.requests.request',
                side_effect=mocked_requests_request)
    def test_exceed_audit_user_limit(self, mock_get):

        options = Options('.', False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        model = CxMGMTaC.Model.load(Path("data") / Path("exceed_audit_user_limit"))
        errors = model.validate(options)
        self.assertEqual(1, len(errors))
        self.assertTrue(isinstance(errors[0], CxMGMTaC.ExceedAuditUserLimit))

    def test_user_to_dict(self):

        user = CxMGMTaC.User('testuser', 'Application',
                             email='testuser@local.domain',
                             first_name='test',
                             last_name='user',
                             locale_id=1,
                             roles=['SAST Reviewer'],
                             active=True)
        d = user.to_dict()
        self.assertEqual(d[CxMGMTaC.ACTIVE], True)
        self.assertEqual(d[CxMGMTaC.AUTHENTICATION_PROVIDER_NAME],
                         'Application')
        self.assertNotIn(CxMGMTaC.CELL_PHONE_NUMBER, d)
        self.assertNotIn(CxMGMTaC.COUNTRY, d)
        self.assertEqual(d[CxMGMTaC.EMAIL], 'testuser@local.domain')
        self.assertNotIn(CxMGMTaC.EXPIRATION_DATE, d)
        self.assertEqual(d[CxMGMTaC.FIRST_NAME], 'test')
        self.assertNotIn(CxMGMTaC.JOB_TITLE, d)
        self.assertEqual(d[CxMGMTaC.LOCALE_ID], 1)
        self.assertEqual(d[CxMGMTaC.LAST_NAME], 'user')
        self.assertNotIn(CxMGMTaC.OTHER, d)
        self.assertNotIn(CxMGMTaC.PHONE_NUMBER, d)
        self.assertEqual(d[CxMGMTaC.ROLES], ['SAST Reviewer'])
        self.assertEqual(d[CxMGMTaC.USERNAME], 'testuser')

    def test_user_to_dict_false_values(self):

        user = CxMGMTaC.User('testuser', 'Application',
                             email='testuser@local.domain',
                             first_name='test',
                             last_name='user',
                             locale_id=1,
                             roles=['SAST Reviewer'],
                             active=True,
                             allowed_ip_list=[],
                             cell_phone_number='',
                             country='',
                             expiration_date='',
                             job_title='',
                             other='',
                             phone_number='')
        d = user.to_dict()
        self.assertEqual(d[CxMGMTaC.ACTIVE], True)
        self.assertEqual(d[CxMGMTaC.AUTHENTICATION_PROVIDER_NAME],
                         'Application')
        self.assertNotIn(CxMGMTaC.CELL_PHONE_NUMBER, d)
        self.assertNotIn(CxMGMTaC.COUNTRY, d)
        self.assertEqual(d[CxMGMTaC.EMAIL], 'testuser@local.domain')
        self.assertNotIn(CxMGMTaC.EXPIRATION_DATE, d)
        self.assertEqual(d[CxMGMTaC.FIRST_NAME], 'test')
        self.assertNotIn(CxMGMTaC.JOB_TITLE, d)
        self.assertEqual(d[CxMGMTaC.LOCALE_ID], 1)
        self.assertEqual(d[CxMGMTaC.LAST_NAME], 'user')
        self.assertNotIn(CxMGMTaC.OTHER, d)
        self.assertNotIn(CxMGMTaC.PHONE_NUMBER, d)
        self.assertEqual(d[CxMGMTaC.ROLES], ['SAST Reviewer'])
        self.assertEqual(d[CxMGMTaC.USERNAME], 'testuser')

    def test_user_to_dict_default_active(self):

        user = CxMGMTaC.User('testuser', 'Application',
                             email='testuser@local.domain',
                             first_name='test',
                             last_name='user',
                             locale_id=1,
                             roles=['SAST Reviewer'])
        d = user.to_dict(default_active=True)
        self.assertNotIn(CxMGMTaC.ACTIVE, d)
        self.assertEqual(d[CxMGMTaC.AUTHENTICATION_PROVIDER_NAME], 'Application')
        self.assertEqual(d[CxMGMTaC.EMAIL], 'testuser@local.domain')
        self.assertEqual(d[CxMGMTaC.FIRST_NAME], 'test')
        self.assertEqual(d[CxMGMTaC.LOCALE_ID], 1)
        self.assertEqual(d[CxMGMTaC.LAST_NAME], 'user')
        self.assertEqual(d[CxMGMTaC.ROLES], ['SAST Reviewer'])

    def test_user_to_dict_default_locale_id(self):

        user = CxMGMTaC.User('testuser', 'Application',
                             email='testuser@local.domain',
                             first_name='test',
                             last_name='user',
                             roles=['SAST Reviewer'],
                             active=True)
        d = user.to_dict(default_locale_id=1)
        self.assertEqual(d[CxMGMTaC.ACTIVE], True)
        self.assertEqual(d[CxMGMTaC.AUTHENTICATION_PROVIDER_NAME],
                         'Application')
        self.assertEqual(d[CxMGMTaC.EMAIL], 'testuser@local.domain')
        self.assertEqual(d[CxMGMTaC.FIRST_NAME], 'test')
        self.assertNotIn(CxMGMTaC.LOCALE_ID, d)
        self.assertEqual(d[CxMGMTaC.LAST_NAME], 'user')
        self.assertEqual(d[CxMGMTaC.ROLES], ['SAST Reviewer'])

    def test_user_to_dict_default_roles(self):

        user = CxMGMTaC.User('testuser', 'Application',
                             email='testuser@local.domain',
                             first_name='test',
                             last_name='user',
                             locale_id=1,
                             active=True,
                             roles={'SAST Reviewer'})
        d = user.to_dict(default_roles={'SAST Reviewer'})
        self.assertEqual(d[CxMGMTaC.ACTIVE], True)
        self.assertEqual(d[CxMGMTaC.AUTHENTICATION_PROVIDER_NAME],
                         'Application')
        self.assertEqual(d[CxMGMTaC.EMAIL], 'testuser@local.domain')
        self.assertEqual(d[CxMGMTaC.FIRST_NAME], 'test')
        self.assertEqual(d[CxMGMTaC.LOCALE_ID], 1)
        self.assertEqual(d[CxMGMTaC.LAST_NAME], 'user')
        self.assertNotIn(CxMGMTaC.ROLES, d)

    def update_common(self, path):

        options = Options(None, False, CxMGMTaC.DEFAULT_USE_CXAUDIT_PERMISSION)
        old_model = CxMGMTaC.Model.retrieve_from_access_control()
        new_model = CxMGMTaC.Model.load(path)
        errors = new_model.validate(options)
        self.assertEqual(0, len(errors))
        old_model.apply_changes(new_model, False)

    def setUp(self):

        mockCxSAST.init()


if __name__ == '__main__':
    unittest.main()
