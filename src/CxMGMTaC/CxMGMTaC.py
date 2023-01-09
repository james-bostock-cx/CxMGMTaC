"""Manage projects, teams and users via config-as-code.

Note: currently, only management of teams and users is supported.
"""

__version__ = "1.0.0-SNAPSHOT"

import argparse
from collections import namedtuple
import copy
import logging
import logging.config
import os
import pathlib
import re
import sys
import yaml

from CheckmarxPythonSDK.CxRestAPISDK import AccessControlAPI

# Constants for dictionary access
ACTIVE = 'active'
ALLOWED_IP_LIST = 'allowed_ip_list'
AUTHENTICATION_PROVIDER_ID = 'authentication_provider_id'
AUTHENTICATION_PROVIDER_NAME = 'authentication_provider_name'
CELL_PHONE_NUMBER = 'cell_phone_number'
COUNTRY = 'country'
DEFAULT_ACTIVE = 'default_active'
DEFAULT_AUTHENTICATION_PROVIDER_NAME = 'default_authentication_provider_name'
DEFAULT_LOCALE_ID = 'default_locale_id'
DEFAULT_ROLES = 'default_roles'
EMAIL = 'email'
EXPIRATION_DATE = 'expiration_date'
FIRST_NAME = 'first_name'
JOB_TITLE = 'job_title'
FULL_NAME = 'full_name'
LAST_NAME = 'last_name'
LOCALE_ID = 'locale_id'
NAME = 'name'
OTHER = 'other'
PHONE_NUMBER = 'phone_number'
ROLE_IDS = 'role_ids'
ROLES = 'roles'
TEAM_IDS = 'team_ids'
USER_ID = 'user_id'
USERNAME = 'username'
USERS = 'users'

# Other constants
DEFAULT_LOG_FORMAT = '%(asctime)s | %(levelname)s | %(funcName)s: %(message)s'

Property = namedtuple('Property', 'name type mandatory')


class Team:
    """An Access Control team.

    Unlike teams in Access Control, the Team class includes an
    explicit list of user references (in the data model exposed by the
    Access Control API, a User has a property containing the
    identifiers of the teams to which it belongs).

    """

    attrs = [
        Property(NAME, str, True),
        Property(FULL_NAME, str, True)
    ]

    def __init__(self, name, full_name, users=None,
                 team_id=None):
        self.team_id = team_id
        self.name = name
        self.full_name = full_name
        if users:
            self.users = users
        else:
            self.users = list()

        if self.full_name.split('/')[-1] != self.name:
            raise ValueError(f'Last component of team full name ({self.full_name}) does not match team name ({self.name})')

    def add_user(self, user):
        """Adds the specified user to the team's list of users."""
        self.users.append(user)

    def to_dict(self):
        """Generate a dictionary representation of the team (which leads to
        prettier YAML output)."""

        d = {
            NAME: self.name,
            FULL_NAME: self.full_name,
            USERS: [user.to_dict() for user in self.users]
        }

        return d

    @staticmethod
    def from_dict(d):
        """Creates a Team from a dictionary."""
        logging.debug(f'd: {d}')
        type_check(d, Team.attrs)
        users = d[USERS]
        del d[USERS]
        team = Team(**d)
        for ud in users:
            team.add_user(UserReference.from_dict(ud))

        return team

    def save(self, dest_dir="."):
        """Saves the team to a file in the specified directory.

        The filename is the team's name, with a ".yml" suffix. The
        file is created in a directory whose path reflects the team's
        full name.

        """
        logging.debug(f'Team.save: full_name: {self.full_name}, dest_dir: {dest_dir}')

        full_name = re.sub('\\s+', '-', self.full_name)
        path = pathlib.Path(dest_dir) / pathlib.Path(f'./{full_name}.yml')
        logging.info(f'Saving team {self.name} to {path}')
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            print(yaml.dump(self.to_dict(), Dumper=yaml.CDumper),
                  file=f)

    @staticmethod
    def load(filename):
        """Loads a team from a YAML file."""
        logging.debug(f'Loading team from {filename}')
        with open(filename, 'r') as f:
            data = yaml.load(f, Loader=yaml.CLoader)
            return Team.from_dict(data)

    @staticmethod
    def load_dir(dirname):
        """Loads all the teams from the YAML files in the named directory and its subdirectories."""
        logging.debug(f'Loading teams from {dirname}')
        teams = []
        for dirpath, dirs, files in os.walk(dirname):
            for filename in files:
                path = pathlib.Path(dirpath) / pathlib.Path(filename)
                if path.suffix.lower() not in ['.yaml', '.yml']:
                    logging.debug(f'Skipping {path} as suffix ({path.suffix}) not recognised')
                    continue
                try:
                    teams.append(Team.load(path))
                except Exception as e:
                    logging.debug(f'Could not load team from {path}: {e}')
                    raise e

        return teams

    def __str__(self):
        """Returns a string representation of the team."""
        if self.team_id is not None:
            return f'Team[name={self.name},full_name={self.full_name},team_id={self.team_id}]'
        else:
            return f'Team[name={self.name},full_name={self.full_name}]'

    def __repr__(self):
        """Returns a string representation of the team."""
        return f'Team({self.name}, {self.full_name}, {self.users}, {self.team_id})'


class Users:
    """A collection of users.

    Having this as a distinct class allows us to specify default
    values for certain user properties, allowing the files on disk to
    be more concise.

    """

    # We omit the users property as it is handled specially
    attrs = [Property(DEFAULT_ACTIVE, bool, False),
             Property(DEFAULT_AUTHENTICATION_PROVIDER_NAME, str, False),
             Property(DEFAULT_LOCALE_ID, int, False),
             Property(DEFAULT_ROLES, list, False),
             ]

    def __init__(self, users, default_active=None,
                 default_authentication_provider_name=None,
                 default_locale_id=None, default_roles=None):

        self.users = users or []
        self.default_active = default_active
        self.default_authentication_provider_name = default_authentication_provider_name
        self.default_locale_id = default_locale_id
        if default_roles:
            self.default_roles = set(default_roles)
        else:
            self.default_roles = set()

    @staticmethod
    def load(filename):
        """Loads a collection of users from the specified file."""
        with open(filename, 'r') as f:
            data = yaml.load(f, Loader=yaml.CLoader)
            users = [Users.user_from_dict(d, data) for d in data[USERS]]
            del data[USERS]
            return Users(users, **data)

    @staticmethod
    def user_from_dict(d, data):
        """Creates a user from the specified dictionary.

        Any properties which are lacking from the dictionary, but for
        which there is a default value, are added.

        """
        for default, actual in [
                (DEFAULT_ACTIVE, ACTIVE),
                (DEFAULT_AUTHENTICATION_PROVIDER_NAME,
                 AUTHENTICATION_PROVIDER_NAME),
                (DEFAULT_LOCALE_ID, LOCALE_ID),
                (DEFAULT_ROLES, ROLES)]:
            if actual not in d and default in data:
                d[actual] = data[default]

        return User(**d)

    def to_dict(self):
        """Generates a dictionary representation of the Users object
        (which leads to prettier YAML output).

        """
        d = {
            USERS: [user.to_dict(default_active=self.default_active,
                                 default_authentication_provider_name=self.default_authentication_provider_name,
                                 default_locale_id=self.default_locale_id,
                                 default_roles=self.default_roles) for user in self.users]
        }

        for attr, f, mandatory in self.attrs:
            if getattr(self, attr) is not None:
                d[attr] = f(getattr(self, attr))
            elif mandatory:
                raise ValueError(f'{attr} attribute is mandatory')

        return d

    def save(self, dir_path):
        """Saves the user collection to the specified directory.

        The users collection is always saved to a file named users.yml.
        """
        users_path = dir_path / pathlib.Path('users.yml')
        with open(users_path, 'w') as f:
            print(yaml.dump(self.to_dict(), Dumper=yaml.CDumper),
                  file=f)
        pass

    def append(self, user):
        """Adds a user to the list of users."""
        self.users.append(user)

    def __len__(self):
        """Returns the number of users."""
        return len(self.users)

    def __contains__(self, user_ref):
        """Returns True if the user reference references a valid user."""
        for user in self.users:
            if user.authentication_provider_name == user_ref.authentication_provider_name and user.username == user_ref.username:
                return True

        return False


class User:
    """An Access Control user.

    For the convenience of people managing the YAML files containing
    user data, authentication provider and role names are used instead
    of their identifiers.

    """

    attrs = [Property(ACTIVE, bool, True),
             Property(ALLOWED_IP_LIST, list, False),
             Property(AUTHENTICATION_PROVIDER_NAME, str, True),
             Property(CELL_PHONE_NUMBER, str, False),
             Property(COUNTRY, str, False),
             Property(EMAIL, str, True),
             Property(EXPIRATION_DATE, str, False),
             Property(FIRST_NAME, str, True),
             Property(JOB_TITLE, str, False),
             Property(LAST_NAME, str, True),
             Property(LOCALE_ID, int, True),
             Property(OTHER, str, False),
             Property(PHONE_NUMBER, str, False),
             Property(ROLES, list, False),
             Property(USERNAME, str, True)
            ]
    
    def __init__(self, username, authentication_provider_name, email=None,
                 first_name=None, last_name=None, locale_id=None, roles=None,
                 active=None, allowed_ip_list=None, cell_phone_number=None,
                 country=None, expiration_date=None, job_title=None,
                 other=None, phone_number=None, user_id=None):

        self.user_id = user_id
        self.username = username
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.authentication_provider_name = authentication_provider_name
        self.locale_id = locale_id
        if roles:
            self.roles = set(roles)
        else:
            self.roles = set()
        self.active = active
        if allowed_ip_list:
            self.allowed_ip_list = allowed_ip_list
        else:
            self.allowed_ip_list = set()
        self.cell_phone_number = cell_phone_number
        self.country = country
        self.expiration_date = expiration_date
        self.job_title = job_title
        self.other = other
        self.phone_number = phone_number

    def to_dict(self, **kwargs):
        """Generates a dictionary representation of the user (which leads to
        prettier YAML output)."""

        logging.debug(f'User.to_dict: kwargs: {kwargs}')
        d = {}
        for attr, f, mandatory in self.attrs:
            value = getattr(self, attr)
            default_attr = f'default_{attr}'
            default_value = kwargs.get(default_attr)
            logging.debug(f'attr: {attr}, f: {f}, mandatory: {mandatory}, value: {value}, default_attr: {default_attr}, default_value: {default_value}')
            if value is not None:
                if value != default_value and (f is bool or value):
                    if f is list:
                        d[attr] = f(sorted(value))
                    else:
                        d[attr] = f(value)
            elif default_value is None and mandatory:
                raise ValueError(f'{attr} attribute is mandatory')

        return d

    @staticmethod
    def from_dict(d):
        """Creates a User from a dictionary."""
        logging.debug(f'd: {d}')
        return User(**d)

    def validate_roles(self, errors):
        """Validates the user's roles."""
        logging.debug(f'Validating roles of user {self.username}')
        for role in self.roles:
            if not role_manager.valid_name(role):
                logging.error(f'Role {role} for user {self.username} is not a valid role')
                errors.append(InvalidRole(self.username, role))

    def get_updates(self, other, old_team_ids, new_team_ids):
        """Creates an dictionary with field updates to make this User match the other User."""
        logging.debug(f'self : {self}')
        logging.debug(f'other: {other}')
        updates = {}
        if self.username != other.username:
            raise ValueError(f'Cannot generate updates for different users ({self.username} and {other.username})')
        if self.authentication_provider_name != other.authentication_provider_name:
            raise ValueError(f'Cannot change authentication provider name (from {self.authentication_provider_name} to {other.authentication_provider_name}))')

        found_updates = False
        for attr, f, mandatory in self.attrs:

            if attr in [AUTHENTICATION_PROVIDER_NAME, ROLES, USERNAME]:
                continue

            if hasattr(other, attr) and not attr_equal(getattr(self, attr), getattr(other, attr), f):
                updates[attr] = getattr(other, attr)
                logging.debug(f'User {self.username}: {attr} has changed from {getattr(self, attr)} to {getattr(other, attr)}')
                found_updates = True
            else:
                updates[attr] = getattr(self, attr)

        if old_team_ids != new_team_ids:
            updates[TEAM_IDS] = new_team_ids
            logging.debug(f'User {self.username}: team_ids has changed from {old_team_ids} to {new_team_ids}')
            found_updates = True
        else:
            updates[TEAM_IDS] = old_team_ids

        if self.roles != other.roles:
            updates[ROLE_IDS] = [role_manager.id_from_name(r) for r in other.roles]
            logging.debug(f'User {self.username}: roles has changed from {self.roles} to {other.roles}')
            found_updates = True
        else:
            updates[ROLE_IDS] = [role_manager.id_from_name(r) for r in self.roles]

        if found_updates:
            return updates
        else:
            return None

    def validate(self, errors):
        """Validates the user."""

        logging.debug(f'Validating {self}')
        for attr, f, mandatory in self.attrs:
            if mandatory and getattr(self, attr) is None:
                logging.error(f'No value found for {attr} property.')
                errors.append(MissingUserProperty(self.username, attr))

        if not authentication_provider_manager.valid_name(self.authentication_provider_name):
            errors.append(InvalidAuthenticationProviderName(self.username, self.authentication_provider_name))

        self.validate_roles(errors)

    def __str__(self):
        """Returns a string representation of the user."""
        return f'User[username={self.username},email={self.email},first_name={self.first_name},last_name={self.last_name},authentication_provider={self.authentication_provider_name},locale_id={self.locale_id},roles={self.roles},active={self.active},allowed_ip_list={self.allowed_ip_list},cell_phone_number={self.cell_phone_number},country={self.country},expiration_date={self.expiration_date},job_title={self.job_title},other={self.other},phone_number={self.phone_number},user_id={self.user_id})'

    def __repr__(self):
        """Returns a string representation of the user."""
        return f'User({self.username}, {self.email}, {self.first_name}, {self.last_name}, {self.authentication_provider_name}, {self.locale_id}, {self.roles}, {self.active}, {self.allowed_ip_list, self.cell_phone_number, self.country, self.expiration_date, self.job_title, self.other, self.phone_number, self.user_id})'


class UserReference:
    """A reference to a user.

    Users are uniquely identified by their username and their
    authentication provider.

    """

    def __init__(self, username, authentication_provider_name):

        self.username = username
        self.authentication_provider_name = authentication_provider_name

    def __eq__(self, other):
        """Returns True if this user reference and other are thesame."""
        if type(self) is type(other):
            return (self.username, self.authentication_provider_name) == \
                (other.username, other.authentication_provider_name)

    def __hash__(self):
        """Returns the hash of this user reference."""
        return hash((self.username, self.authentication_provider_name))

    def to_dict(self):
        """Generates a dictionary representation of the user (which leads to
        prettier YAML output)."""

        d = {
            USERNAME: self.username,
            AUTHENTICATION_PROVIDER_NAME: self.authentication_provider_name
        }

        return d

    @staticmethod
    def from_dict(d):
        """Creates a User from a dictionary."""
        logging.debug(f'd: {d}')
        return User(**d)

    def validate(self):
        """Validates this user reference."""
        logging.debug(f'Validating {self}')
        for attr in ['authentication_provider_name']:
            if getattr(self, attr) is None:
                raise ValueError(f'{self.username}: {attr} is None')

        # Make sure the authentication provider name is valid.
        _ = authentication_provider_manager.id_from_name(self.authentication_provider_name)

    def __str__(self):
        """Returns a string representation of this user reference."""
        return f'UserReference[username={self.username},authentication_provider={self.authentication_provider_name}]'

    def __repr__(self):
        """Returns a string representation of this user reference."""
        return f'UserReference({self.username}, {self.authentication_provider_name})'


class Model:
    """A model of Access Control teams and users.

    The model consists of a collection of users, a list of teams, and
    and three dictionaries:

    - team_map: a mapping from a team's full name to a corresponding Team
                instance.
    - user_map: a mapping from a user's username and authentication provider
                name to the corresponding User instance.
    - user_team_ids_map: a mapping from a user's username and authentication
                         provider name to a set of team identifiers. This
                         map is rebuilt when changes are made to the teams.
    """

    def __init__(self, teams, users, build_maps=False):

        self.teams = teams
        self.users = users
        self.team_map = {}
        self.user_team_ids_map = {}
        self.user_map = {}

        if build_maps:
            errors = []
            self.build_maps(errors)
            if errors:
                raise RuntimeError(f'Error(s) building maps: {errors}')

    def build_maps(self, errors):
        """Builds maps that help with processing."""

        for team in self.teams:
            if team.full_name in self.team_map:
                # TODO throw exception
                logging.error(f'Cannot have two teams with the same full name ({team.full_name})')
                errors.append(DuplicateTeam(team.full_name))
            self.team_map[team.full_name] = team
        for user in self.users.users:
            key = UserReference(user.username, user.authentication_provider_name)
            if key in self.user_map:
                logging.error(f'Cannot have two users with the same username and authentication provider ({key})')
                errors.append(DuplicateUser(key))
            self.user_map[key] = user
        self.update_user_team_ids_map()

    def update_user_team_ids_map(self):
        """Updates the mapping from users to sets of team identifiers."""
        logging.debug('Updating user team ids map')
        self.user_team_ids_map = {}
        for team in self.teams:
            for user in team.users:
                key = UserReference(user.username, user.authentication_provider_name)
                user_teams = self.user_team_ids_map.get(key, set())
                user_teams.add(team.team_id)
                self.user_team_ids_map[key] = user_teams

    def update_team_ids(self, other):
        """Updates the team identifiers from the other model instance.

        The assumption here is that one model will have been loaded
        from disk and so will not have team_id values; the other will
        have been retrieved from Access Control, and will have team_id
        values.

        """
        logging.debug('Updating team ids')
        for team in other.teams:
            if team.full_name in self.team_map:
                logging.debug(f'Setting team_id of {team.full_name} to {team.team_id}')
                self.team_map[team.full_name].team_id = team.team_id
            else:
                logging.debug(f'{team.full_name} not in team_map')
        self.update_user_team_ids_map()

    def validate(self, options):
        """Validates the model."""
        logging.debug('Validating model')

        errors = []
        self.build_maps(errors)
        self.validate_users(options, errors)
        self.validate_teams(options, errors)
        return errors

    def validate_users(self, options, errors):
        """Validates the model's users.

        Makes sure that each user belongs to at least one team.
        """
        logging.debug('Validating users')
        for user in self.users.users:
            user.validate(errors)
            key = UserReference(user.username, user.authentication_provider_name)
            if key not in self.user_team_ids_map:
                logging.error(f'{user.username} does not belong to any teams')
                errors.append(NoTeam(user.username, user.authentication_provider_name))

    def validate_teams(self, options, errors):
        """Validates this model's teams."""
        logging.debug('Validating teams')
        for team in self.teams:
            self.validate_team(team, options, errors)

    def validate_team(self, team, options, errors):
        """Validates the specified team.

        Makes sure that all the user references are valid.
        """
        logging.debug(f'Validating team {team.full_name}')
        for user_ref in team.users:
            if user_ref not in self.users:
                if options.retrieve_user_entries:
                    self.retrieve_user_entries(user_ref, options, errors)
                else:
                    logging.error(f'{user_ref} not in users file')
                    errors.append(MissingUser(user_ref))

    def retrieve_user_entries(self, user_ref, options, errors):
        """Retrieve user entries from an LDAP server."""
        logging.debug(f'Attempting to retrieve {user_ref.username} from {user_ref.authentication_provider_name}')
        ldap_server_id = authentication_provider_manager.get_ldap_server_id(user_ref.authentication_provider_name)
        user_entries = ac_api.get_user_entries_by_search_criteria(ldap_server_id, user_ref.username)
        for user_entry in user_entries:
            logging.debug(f'User_entry: {user_entry}')
            if user_entry.username == user_ref.username:
                logging.debug(f'Found user entry for {user_ref.username}')
                self.add_user_entry(user_ref, user_entry, options)
                return

        logging.error(f'Cannot find user with username {user_ref.username} in {user_ref.authentication_provider_name}')
        errors.append(MissingLDAPUser(user_ref))

    def add_user_entry(self, user_ref, user_entry, options):

        user = User(user_ref.username,
                    user_ref.authentication_provider_name,
                    user_entry.email,
                    user_entry.first_name,
                    user_entry.last_name)
        logging.debug(f'Adding {user} to self.users')
        self.users.append(user)
        self.save_users(options.data_dir)

    def apply_changes(self, new_model, dry_run):
        """Applies the changes needed to make this model match the new model.
        """
        logging.info('Applying changes')
        new_model.update_team_ids(self)
        self.add_teams(new_model, dry_run)
        self.add_users(new_model, dry_run)
        self.update_users(new_model, dry_run)
        self.delete_users(new_model, dry_run)
        self.delete_teams(new_model, dry_run)

    def add_teams(self, new_model, dry_run):
        """Adds teams that are in the new model but not the old."""
        logging.info("Adding teams")
        cur_team_names = set(self.team_map.keys())
        logging.debug(f'Current teams: {cur_team_names}')
        new_team_names = set(new_model.team_map.keys())
        logging.debug(f'New teams: {new_team_names}')
        teams_to_create = new_team_names - cur_team_names
        logging.debug(f'Teams to create: {teams_to_create}')

        team_map = copy.deepcopy(new_model.team_map)
        for team_full_name in sorted(teams_to_create):
            logging.debug(f'Creating {team_full_name}')
            team = new_model.team_map[team_full_name]
            parent_full_name = get_team_parent_name(team_full_name)
            parent_id = team_map[parent_full_name].team_id
            create_team(team.name, parent_id, dry_run)
            team_id = ac_api.get_team_id_by_full_name(team.full_name)
            team.team_id = team_id
            team_map[team.full_name] = team
        new_model.team_map = team_map
        new_model.update_user_team_ids_map()

    def delete_teams(self, new_model, dry_run):
        """Deletes any teams in that are in the old model but not the new."""
        logging.info("Deleting teams")
        cur_team_names = set(self.team_map.keys())
        logging.debug(f'Current teams: {cur_team_names}')
        new_team_names = set(new_model.team_map.keys())
        logging.debug(f'New teams: {new_team_names}')
        teams_to_delete = cur_team_names - new_team_names
        logging.debug(f'Teams to delete: {teams_to_delete}')

        for team_full_name in sorted(teams_to_delete, reverse=True):
            logging.debug(f'Deleting {team_full_name}')
            delete_team(self.team_map[team_full_name].team_id, dry_run)

    def add_users(self, new_model, dry_run):
        """Adds users that are in the new model but not the old."""
        logging.info('Adding users')

        cur_users = set(self.user_map.keys())
        logging.debug(f'Current users: {cur_users}')
        new_users = set(new_model.user_map.keys())
        logging.debug('New users')
        users_to_create = new_users - cur_users
        logging.debug(f'Users to create: {users_to_create}')

        for userkey in sorted(users_to_create):
            logging.debug(f'Creating {userkey.username}')
            create_user(new_model.get_user_by_userkey(userkey),
                        new_model.get_user_team_ids(userkey), dry_run)

    def delete_users(self, new_model, dry_run):
        """Deletes users that are in the old model but not in the new."""
        logging.info('Deleting users')

        cur_users = set(self.user_map.keys())
        logging.debug(f'Current users: {cur_users}')
        new_users = set(new_model.user_map.keys())
        logging.debug('New users')
        users_to_delete = cur_users - new_users
        logging.debug(f'Users to delete: {users_to_delete}')

        for userkey in sorted(users_to_delete):
            logging.debug(f'Deleting {userkey.username}')
            delete_user(self.get_user_by_userkey(userkey), dry_run)

    def update_users(self, new_model, dry_run):
        """Updates users whose properties (including teams) have changed."""
        logging.info('Updating users')

        cur_users = set(self.user_map.keys())
        logging.debug(f'Current users: {cur_users}')
        new_users = set(new_model.user_map.keys())
        logging.debug('New users')
        users_to_update = new_users & cur_users
        logging.debug(f'Users to check for updates: {users_to_update}')

        logging.debug('Updating users')
        for userkey in users_to_update:
            old_user = self.get_user_by_userkey(userkey)
            old_team_ids = self.get_user_team_ids(userkey)
            new_user = new_model.get_user_by_userkey(userkey)
            new_team_ids = new_model.get_user_team_ids(userkey)

            updates = old_user.get_updates(new_user, old_team_ids,
                                           new_team_ids)
            if updates:
                logging.debug(f'Setting updates[{USER_ID}] to {old_user.user_id}')
                updates[USER_ID] = old_user.user_id
                logging.debug(f'updates for {userkey.username}: {updates}')
                update_user(updates, dry_run)

    def get_user_by_userkey(self, userkey):
        """Returns the User instance corresponding to userkey."""
        return self.user_map[userkey]

    def get_user_team_ids(self, userkey):
        """Returns a set of team ids of which the specified user is a member.
        """
        return self.user_team_ids_map[userkey]

    @staticmethod
    def retrieve_from_access_control():
        """Retrieves model data from Access Control."""
        logging.info('Retrieving user and team data from Access Control')
        cx_teams = ac_api.get_all_teams()
        cx_users = ac_api.get_all_users()
        teams = []
        team_map = {}
        users = Users([])

        for cx_team in cx_teams:
            logging.debug(f'retrieve_from_access_control: cx_team: {cx_team}')
            team = Team(cx_team.name, cx_team.full_name, team_id=cx_team.id)
            teams.append(team)
            team_map[cx_team.id] = team

        for cx_user in cx_users:
            logging.debug(f'retrieve_from_access_control: cx_user: {cx_user}')
            roles = [role_manager.name_from_id(r) for r in cx_user.role_ids]
            authentication_provider_name = authentication_provider_manager.name_from_id(cx_user.authentication_provider_id)
            user = User(cx_user.username, authentication_provider_name,
                        cx_user.email, cx_user.first_name, cx_user.last_name,
                        cx_user.locale_id, roles, cx_user.active,
                        cx_user.allowed_ip_list,
                        cx_user.cell_phone_number, cx_user.country,
                        cx_user.expiration_date, cx_user.job_title,
                        cx_user.other, cx_user.phone_number,
                        cx_user.id)
            errors = []
            user.validate(errors)
            users.append(user)

            for team_id in cx_user.team_ids:
                team = team_map[team_id]
                user_ref = UserReference(cx_user.username, authentication_provider_name)
                team.users.append(user_ref)

        return Model(teams, users, build_maps=True)

    @staticmethod
    def load(dirname):
        """Loads a model from the specified directory."""
        dir_path = pathlib.Path(dirname)
        users_path = dir_path / pathlib.Path('users') / pathlib.Path('users.yml')
        users = Users.load(users_path)
        teams_dir_path = dir_path / pathlib.Path('teams')
        teams = Team.load_dir(teams_dir_path)
        return Model(teams, users)

    def save(self, dirname='.'):
        """Saves this model to the specified directory."""
        self.save_teams(dirname)
        self.save_users(dirname)

    def create_dest_dir(self, dirname='.'):
        """Creates the directory to which the model is to be saved."""
        dir_path = pathlib.Path(dirname)
        dir_path.mkdir(exist_ok=True)
        return dir_path

    def save_teams(self, dirname='.'):
        """Saves the model's teams to the specified directory.

        Note that the teams are saved to a 'teams' subdirectory.
        """
        dir_path = self.create_dest_dir(dirname)
        teams_dir_path = dir_path / pathlib.Path('teams')
        teams_dir_path.mkdir(exist_ok=True)
        for team in self.teams:
            team.save(teams_dir_path)

    def save_users(self, dirname='.'):
        """Saves the model's users to the specified directory.

        Note that the users are saved to a 'users' subdirectory.
        """
        dir_path = self.create_dest_dir(dirname)
        users_dir_path = dir_path / pathlib.Path('users')
        users_dir_path.mkdir(exist_ok=True)
        self.users.save(users_dir_path)


class RoleManager:
    """A manager of Access Control roles.

    "Manager" is maybe a bit overblown: this class retrieves the roles
    from Access Control and then translates between role names and
    role identifiers.
    """

    def __init__(self, ac_api):

        self.all_roles = ac_api.get_all_roles()
        logging.debug(f'all_roles: {[r.name for r in self.all_roles]}')

    def name_from_id(self, role_id):
        """Returns the role name that corresponds to role_id."""
        for role in self.all_roles:
            if role.id == role_id:
                return role.name

        raise ValueError(f'{role_id}: invalid role ID')

    def id_from_name(self, role_name):
        """Returns the role identifier that corresponds to role_name."""
        for role in self.all_roles:
            if role.name == role_name:
                return role.id

        raise ValueError(f'{role_name}: invalid role name')

    def valid_name(self, role_name):
        """Indicates with a role name is valid."""
        for role in self.all_roles:
            if role.name == role_name:
                return True

        return False


class AuthenticationProviderManager:
    """A manager of Access Control authentication providers.

    "Manager" is maybe a bit overblown: this class retrieves the
    authentication providers from Access Control and then translates
    between role names and role identifiers.
    """

    def __init__(self, ac_api):

        self.authentication_providers = ac_api.get_all_authentication_providers()
        self.ldap_servers = ac_api.get_all_ldap_servers()

    def name_from_id(self, provider_id):
        """Returns the authentication provider name that corresponds to
        provider_id.
        """
        for provider in self.authentication_providers:
            if provider.id == provider_id:
                return provider.name

        raise ValueError(f'{provider_id}: invalid authentication provider ID')

    def id_from_name(self, provider_name):
        """Returns the authentication provider identifier that corresponds
        to provider_name."""
        for provider in self.authentication_providers:
            if provider.name == provider_name:
                return provider.id

        raise ValueError(f'{provider_name}: invalid authentication provider name')

    def valid_name(self, provider_name):
        """Indicates with an authentication provider name is valid."""
        for provider in self.authentication_providers:
            if provider.name == provider_name:
                return True

        return False

    def get_ldap_server_id(self, ldap_server_name):

        for ldap_server in self.ldap_servers:
            if ldap_server.name == ldap_server_name:
                return ldap_server.id

        raise ValueError(f'{ldap_server_name}: invalid LDAP server name')


class DuplicateTeam:
    """More than one team have the same full name."""

    def __init__(self, team_full_name):

        self.team_full_name = team_full_name

    def __repr__(self):

        return f'DuplicateTeam({self.team_full_name})'


class DuplicateUser:
    """More than one user have the same username and authentication provider."""

    def __init__(self, user_reference):

        self.user_reference = user_reference

    def __repr__(self):

        return f'DuplicateUser({self.user_reference})'


class InvalidRole:
    """An invalid role error."""

    def __init__(self, username, role):

        self.username = username
        self.role = role

    def __repr__(self):

        return f'InvalidRole({self.username}, {self.role})'


class InvalidAuthenticationProviderName:
    """An invalid authentication provider name error."""

    def __init__(self, username, authentication_provider_name):

        self.username = username
        self.authentication_provider_name = authentication_provider_name

    def __repr__(self):

        return f'InvalidAuthenticationProviderName({self.username}, {self.authentication_provider_name})'


class NoTeam:
    """A no team error."""

    def __init__(self, username, authentication_provider_name):

        self.username = username
        self.authentication_provider_name = authentication_provider_name

    def __repr__(self):

        return f'NoTeam({self.username}, {self.authentication_provider_name})'


class MissingLDAPUser:
    """A missing LDAP user.

    I.e., the user referred to by the user reference cannot be found
    in the LDAP server associated with the reference.

    """

    def __init__(self, user_ref):

        self.user_ref = user_ref

    def __repr__(self):

        return f'MissingLDAPUser({self.user_ref})'


class MissingUser:
    """A missing user.

    I.e., a team file contains a reference to a non-existent user.
    """

    def __init__(self, user_ref):

        self.user_ref = user_ref

    def __repr__(self):

        return f'MissingUser({self.user_ref})'


class MissingUserProperty:
    """A missing user property error."""

    def __init__(self, username, property):

        self.username = username
        self.property = property

    def __repr__(self):

        return f'MissingUserProperty({self.username}, {self.property})'


class ModelValidationError(Exception):
    """A generic model validation error."""

    def __init__(self, errors):

        self.errors = errors

    def __str__(self):

        return f'ModelValidationError({self.errors})'


def attr_equal(attr1, attr2, attr_type):
    """Return True if two attributes are equal.

    If the attribute type is not bool, then we treat different Python
    False values as the same.

    For example, if the type is str, the empty string and None will be
    considered equal.
    """
    if attr_type is not bool and not attr1 and not attr2:
        return True

    return attr1 == attr2


def get_team_parent_name(full_name):
    """Returns the full name of the parent team to the specified team."""
    return '/'.join(full_name.split('/')[0:-1])


def extract(options):
    """Extracts a model from Access Control and saves it."""
    logging.info('extract')
    model = Model.retrieve_from_access_control()
    model.save(options.dest_dir)


def update(options):
    """Updates Access Control to match the """
    logging.info('update')
    cur_model = Model.retrieve_from_access_control()
    new_model = validate(options)
    logging.info('update: updating team ids of new model')
    new_model.update_team_ids(cur_model)
    cur_model.apply_changes(new_model, options.dry_run)


def validate(options):
    """Validates a model specified by YAML files."""
    logging.info(f'Validating files in {options.data_dir}')
    model = Model.load(options.data_dir)
    errors = model.validate(options)
    if errors:
        logging.error('Model failed validation')
        raise ModelValidationError(errors)

    logging.info('Model validated successfully')
    return model


def create_team(team_name, team_parent_id, dry_run):
    """Creates a team in Access Control."""
    logging.info(f'Creating team {team_name} under parent {team_parent_id}')
    if not dry_run:
        ac_api.create_new_team(team_name, team_parent_id)


def delete_team(team_id, dry_run):
    """Deletes a team from Access Control."""
    logging.info(f'Deleting team {team_id}')
    if not dry_run:
        ac_api.delete_a_team(team_id)


def create_user(user, team_ids, dry_run):
    """Creates a user in Access Control."""
    logging.info(f'Creating user {user.username}')
    if not dry_run:
        authentication_provider_id = authentication_provider_manager.id_from_name(user.authentication_provider_name)
        role_ids = [role_manager.id_from_name(r) for r in user.roles]
        ac_api.create_new_user(user.username, '', role_ids, list(team_ids),
                               authentication_provider_id, user.first_name,
                               user.last_name, user.email, user.phone_number,
                               user.cell_phone_number, user.job_title,
                               user.other, user.country, user.active,
                               user.expiration_date, list(user.allowed_ip_list),
                               user.locale_id)


def delete_user(user, dry_run):
    """Deletes a user from Access Control."""
    logging.info(f'Deleting user {user.username} ({user.user_id})')
    if not dry_run:
        ac_api.delete_a_user(user.user_id)


def update_user(updates, dry_run):
    """Updates a user in Access Control."""
    logging.info(f'Updating user with ID {updates[USER_ID]}')
    if USER_ID not in updates or not updates[USER_ID]:
        raise ValueError(f'{USER_ID} missing from updates dictionary')
    logging.debug(f'updates: {updates}')
    # Note that it is not permitted to change the authentication
    # provider so, for updates, we do not need to find the id that
    # corresponds to the provider name.
    #
    # JSON serialization doesn't cope with sets
    updates[ALLOWED_IP_LIST] = list(updates[ALLOWED_IP_LIST])
    updates[ROLE_IDS] = list(updates[ROLE_IDS])
    updates[TEAM_IDS] = list(updates[TEAM_IDS])
    if not dry_run:
        ac_api.update_a_user(**updates)


def type_check(d, properties):

    for property in properties:
        if property.name in d:
            if type(d[property.name]) != property.type:
                raise TypeError(f'Type of "{property.name}" property is {type(d[property.name])} (expected {property.type})')
        elif property.mandatory:
            raise ValueError(f'"{property.name}" property is mandatory')


def usage(args):
    """Prints a usage message."""
    print(f'''usage: py {sys.argv[0]} <extract|update|validate> [args]''')


# Global variables
ac_api = AccessControlAPI()
authentication_provider_manager = AuthenticationProviderManager(ac_api)
role_manager = RoleManager(ac_api)

if __name__ == '__main__':

    parser = argparse.ArgumentParser(prog='CxMGMTaC')
    parser.add_argument('--log-config', type=str,
                        help='The log configuration')
    parser.add_argument('--log-format', type=str,
                        default=DEFAULT_LOG_FORMAT,
                        help='The log format')
    parser.add_argument('-l', '--log-level', type=str, default='INFO',
                        help='The log level')
    parser.set_defaults(func=usage)
    subparsers = parser.add_subparsers(help='sub-command help')

    # Parser for the extract command
    extract_parser = subparsers.add_parser('extract')
    extract_parser.add_argument('-d', '--dest-dir', type=str, default='.',
                                help='Destination directory')
    extract_parser.set_defaults(func=extract)

    # Parser for the update command
    update_parser = subparsers.add_parser('update')
    update_parser.add_argument('-d', '--data-dir', type=str, default='.',
                               help='Data directory')
    update_parser.add_argument('--dry-run', action='store_true', default=False,
                               help='Display updates without performing them')
    update_parser.set_defaults(func=update)

    # Parser for the validate command
    validate_parser = subparsers.add_parser('validate')
    validate_parser.add_argument('-d', '--data-dir', type=str, default='.',
                                 help='Data directory')
    validate_parser.add_argument('-r', '--retrieve-user-entries',
                                 action='store_true', default=False,
                                 help='Retrieve user entries')
    validate_parser.set_defaults(func=validate)

    args = parser.parse_args([arg for arg in sys.argv[1:]
                              if not arg.startswith('--cxsast')])
    if args.log_config:
        logging.config.fileConfig(args.log_config)
    else:
        logging.basicConfig(level=args.log_level, format=args.log_format,
                            force=True)

    try:
        args.func(args)
    except Exception as e:
        logging.error(f'{args.func.__name__} failed: {e}', exc_info=True)
        sys.exit(1)

    sys.exit(0)
