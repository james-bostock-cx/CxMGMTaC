"""Manage projects, teams and users via config-as-code."""

__version__ = "0.2.0"

import argparse
from collections import namedtuple
import copy
import logging
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
DEFAULT_ALLOWED_IP_LIST = 'default_allowed_ip_list'
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

# Global variables
authentication_provider_manager = None
role_manager = None

Property = namedtuple('Property', 'name type mandatory')


class Team:

    def __init__(self, name, full_name, default_active=None,
                 default_allowed_ip_list=None,
                 default_authentication_provider_name=None,
                 default_locale_id=None, default_roles=None, users=None,
                 team_id=None):
        self.team_id = team_id
        self.name = name
        self.full_name = full_name
        self.default_active = default_active
        if default_allowed_ip_list:
            self.default_allowed_ip_list = set(default_allowed_ip_list)
        else:
            self.default_allowed_ip_list = set()
        self.default_authentication_provider_name = default_authentication_provider_name
        self.default_locale_id = default_locale_id
        if default_roles:
            self.default_roles = set(default_roles)
        else:
            self.default_roles = set()
        if users:
            self.users = users
        else:
            self.users = list()

        if self.full_name.split('/')[-1] != self.name:
            raise ValueError(f'Last component of team full name ({self.full_name}) does not match team name ({self.name})')

    def add_user(self, user):

        self.users.append(user)

    def normalize(self):
        """For certain attributes, if all users have the same value,
        replace them with a team-level default."""

        logging.debug(f'Normalising {self.full_name}')
        for attr in [ACTIVE, ALLOWED_IP_LIST,
                     AUTHENTICATION_PROVIDER_NAME, LOCALE_ID, ROLES]:
            default = None
            set_default = True
            for user in self.users:
                if default is not None and default != getattr(user, attr):
                    set_default = False
                    break
                else:
                    default = getattr(user, attr)
            if set_default:
                logging.debug(f'Setting default_{attr} to {default}')
                setattr(self, f'default_{attr}', default)
                for user in self.users:
                    setattr(user, attr, None)

    def denormalize(self):
        """For each team-level default attribute, set the
        corresponding attribute for all users that do not already have
        a value for it."""

        for user in self.users:
            logging.debug(f'Setting default attributes for user {user.username} in team {self.full_name}')
            for attr, attr_type in [(ACTIVE, bool), (ALLOWED_IP_LIST, list),
                                    (AUTHENTICATION_PROVIDER_NAME, str),
                                    (LOCALE_ID, int), (ROLES, list)]:
                attr_value = getattr(user, attr)
                logging.debug(f'attr: {attr}: attr_value: {attr_value}')
                if (attr_type == list and not attr_value) or attr_value is None:
                    logging.debug(f'{attr} for {user.username} is None')
                    default_value = getattr(self, f'default_{attr}')
                    if default_value is None:
                        errors = [
                            MissingDefaultAttribute(user.username, self.full_name, attr)
                            ]
                        raise ModelValidationError(errors)
                    else:
                        logging.debug(f'Setting {attr} for user {user.username} to {default_value}')
                        setattr(user, attr, default_value)
                else:
                    logging.debug(f'{attr} for {user.username} is {getattr(user, attr)}')

            user.validate()

    def to_dict(self):

        """Generate a dictionary representation of the team (which leads to
        prettier YAML output)."""

        self.normalize()

        d = {
            NAME: self.name,
            FULL_NAME: self.full_name,
            USERS: [user.to_dict() for user in self.users]
        }

        for attr, f in [(DEFAULT_ACTIVE, bool),
                        (DEFAULT_ALLOWED_IP_LIST, list),
                        (DEFAULT_AUTHENTICATION_PROVIDER_NAME, str),
                        (DEFAULT_LOCALE_ID, int),
                        (DEFAULT_ROLES, list)]:
            if getattr(self, attr) or f is bool:
                d[attr] = f(getattr(self, attr))

        return d

    @staticmethod
    def from_dict(d):
        """Creates a Team from a dictionary."""
        logging.debug(f'd: {d}')
        type_check(d, [
            Property(NAME, str, True),
            Property(FULL_NAME, str, True),
            Property(DEFAULT_ACTIVE, bool, False),
            Property(DEFAULT_ALLOWED_IP_LIST, list, False),
            Property(DEFAULT_AUTHENTICATION_PROVIDER_NAME, str, False),
            Property(DEFAULT_ROLES, list, False),
            ])
        users = d[USERS]
        del d[USERS]
        team = Team(**d)
        for ud in users:
            team.add_user(User.from_dict(ud))

        team.denormalize()

        return team

    def save(self, dest_dir="."):
        """Save the team to a file in the specified directory.

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
        """Loads a team from a YAM file."""
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

    def validate_default_roles(self, errors):
        """Validates the team's default roles."""
        logging.debug(f'Validating default roles for {self.full_name}')
        for role in self.default_roles:
            if not role_manager.valid_role_by_name(role):
                logging.error(f'default role {role} for team {self.full_name} is not a valid role')
                errors.append(InvalidDefaultRole(self.full_name, role))

    def __str__(self):
        return f'Team[name={self.name},full_name={self.full_name}'

    def __repr__(self):

        return 'Team({}, {}, {}, {}, {}, {}, {}, {}, {})'.format(self.name,
                                                                 self.full_name,
                                                                 self.default_active,
                                                                 self.default_allowed_ip_list,
                                                                 self.default_authentication_provider_name,
                                                                 self.default_locale_id,
                                                                 self.default_roles,
                                                                 self.users.
                                                                 self.team_id)


class User:

    def __init__(self, username, email, first_name, last_name,
                 authentication_provider_name=None, locale_id=None, roles=None,
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

    def to_dict(self):
        """Generate a dictionary representation of the user (which leads to
        prettier YAML output)."""

        d = {
            USERNAME: self.username,
            EMAIL: self.email,
            FIRST_NAME: self.first_name,
            LAST_NAME: self.last_name,
        }

        for attr, f in [(ACTIVE, bool),
                        (ALLOWED_IP_LIST, list),
                        (AUTHENTICATION_PROVIDER_NAME, str),
                        (CELL_PHONE_NUMBER, str),
                        (COUNTRY, str),
                        (EXPIRATION_DATE, str),
                        (JOB_TITLE, str),
                        (OTHER, str),
                        (PHONE_NUMBER, str),
                        (ROLES, list)]:
            if getattr(self, attr) is not None:
                d[attr] = f(getattr(self, attr))

        return d

    @staticmethod
    def from_dict(d):
        """Creates a User from a dictionary."""
        logging.debug(f'd: {d}')
        return User(**d)

    def validate_roles(self, errors, team_full_name):
        """Validates the user's roles."""
        logging.debug(f'Validating roles of user {self.username}')
        for role in self.roles:
            if not role_manager.valid_role_by_name(role):
                logging.error(f'Role {role} for user {self.username} in team {team_full_name} is not a valid role')
                errors.append(InvalidRole(team_full_name, self.username, role))

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
        for attr in [ACTIVE, ALLOWED_IP_LIST, CELL_PHONE_NUMBER,
                      COUNTRY, EMAIL, EXPIRATION_DATE, FIRST_NAME,
                      JOB_TITLE, LAST_NAME, LOCALE_ID, OTHER,
                      PHONE_NUMBER]:

            if hasattr(other, attr) and (getattr(self, attr) != getattr(other, attr)):
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

    def validate(self):

        logging.debug(f'Validating {self}')
        for attr in ['active', 'authentication_provider_name', 'locale_id']:
            if getattr(self, attr) is None:
                raise ValueError(f'{self.username}: {attr} is None')

        # Make sure the authentication provider name is valid.
        _ = authentication_provider_manager.id_from_name(self.authentication_provider_name)

    def __str__(self):

        return f'User[username={self.username},email={self.email},first_name={self.first_name},last_name={self.last_name},authentication_provider={self.authentication_provider_name},locale_id={self.locale_id},roles={self.roles},active={self.active},allowed_ip_list={self.allowed_ip_list},cell_phone_number={self.cell_phone_number},country={self.country},expiration_date={self.expiration_date},job_title={self.job_title},other={self.other},phone_number={self.phone_number},user_id={self.user_id})'

    def __repr__(self):

        return f'User({self.username}, {self.email}, {self.first_name}, {self.last_name}, {self.authentication_provider_name}, {self.locale_id}, {self.roles}, {self.active}, {self.allowed_ip_list, self.cell_phone_number, self.country, self.expiration_date, self.job_title, self.other, self.phone_number, self.user_id})'


class Model:
    """A model of teams an users.

    The model consists of two dictionaries:

    - team_map: a mapping from a team's full name to a corresponding Team instance.
    - user_map: a mapping from a user's username to a mapping of team full names to
                User instances.
    """

    def __init__(self, teams):

        self.teams = teams
        self.team_map = {}
        self.user_map = {}
        for team in teams:
            if team.full_name in self.team_map:
                logging.error(f'Cannot have two teams with the same full name {team.full_name}')
            self.team_map[team.full_name] = team
            for user in team.users:
                team_user_map = self.user_map.get(user.username, {})
                team_user_map[team.full_name] = user
                self.user_map[user.username] = team_user_map

    def validate(self):
        """Validates the model."""
        logging.debug('Validating model')

        errors = []
        self.validate_default_roles(errors)
        self.validate_users(errors)
        return errors

    def validate_default_roles(self, errors):
        """Validates each team's default roles."""
        logging.debug('Validating default roles')
        for team in self.teams:
            team.validate_default_roles(errors)

    def validate_users(self, errors):
        """Makes sure that user definitions are consistent across teams."""
        for username in self.user_map:
            self.validate_user(errors, username, self.user_map[username])

    def validate_user(self, errors, username, team_user_map):
        """Validates the specified user."""
        logging.debug(f'Validating user {username}')

        if len(team_user_map) == 1:
            logging.debug(f'User {username} belongs to multiple teams')

        first_team = None
        first_user = None
        for team_full_name, user in team_user_map.items():
            user.validate_roles(errors, team_full_name)
            if not first_user:
                first_team = self.team_map[team_full_name]
                first_user = user
                first_roles = user.roles
            else:
                # By definition, the username values are the same
                if user.email != first_user.email:
                    logging.debug(f'{first_user.email} != {user.email}')
                    errors.append(InconsistentUser('email',
                                                   first_user.username,
                                                   first_team.full_name,
                                                   team_full_name,
                                                   first_user.email,
                                                   user.email))
                team = self.team_map[team_full_name]
                roles = user.roles
                if first_roles != roles:
                    logging.debug(f'{first_roles} != {roles}')
                    errors.append(InconsistentUser('roles',
                                                   first_user.username,
                                                   first_team.full_name,
                                                   team_full_name,
                                                   first_roles,
                                                   roles))

    def apply_changes(self, ac_api, new_model, dry_run):
        """Applies the changes needed to make this model match the new model."""
        logging.info('Applying changes')
        self.apply_team_changes(ac_api, new_model, dry_run)
        self.apply_user_changes(ac_api, new_model, dry_run)

    def apply_team_changes(self, ac_api, new_model, dry_run):
        """Applies team changes to make this model match the new model."""
        logging.info('Applying team changes')
        cur_team_names = set(self.team_map.keys())
        new_team_names = set(new_model.team_map.keys())
        teams_to_create = new_team_names - cur_team_names
        teams_to_delete = cur_team_names - new_team_names

        # Update ids of teams in new_model
        for team_full_name in new_model.team_map:
            if team_full_name in self.team_map:
                new_model.team_map[team_full_name].team_id = self.team_map[team_full_name].team_id

        logging.debug('Creating new teams')
        team_map = copy.deepcopy(new_model.team_map)
        for team_full_name in sorted(teams_to_create):
            team = new_model.team_map[team_full_name]
            parent_full_name = get_team_parent_name(team_full_name)
            parent_id = team_map[parent_full_name].team_id
            create_team(ac_api, team.name, parent_id, dry_run)
            team_id = ac_api.get_team_id_by_full_name(team.full_name)
            logging.debug(f'Team ID for {team.name} is {team_id}')
            team.team_id = team_id
            team_map[team.full_name] = team
        new_model.team_map = team_map

        logging.debug('Deleting teams')
        for team_full_name in sorted(teams_to_delete, reverse=True):
            delete_team(ac_api, self.team_map[team_full_name].team_id, dry_run)

        # Update team_id values of existing teams in the new model
        for team_name in cur_team_names:
            if team_name in new_team_names:
                old_team = self.team_map[team_name]
                new_team = new_model.team_map[team_name]
                new_team.team_id = old_team.team_id

    def apply_user_changes(self, ac_api, new_model, dry_run):
        """Applies user changes to make this model match the new model."""
        logging.info('Applying user changes')

        cur_users = set(self.user_map.keys())
        new_users = set(new_model.user_map.keys())
        users_to_create = new_users - cur_users
        users_to_delete = cur_users - new_users

        logging.debug('Creating new users')
        for username in sorted(users_to_create):
            # TODO! role_ids and team_ids
            create_user(ac_api, new_model.get_user_by_username(username),
                        new_model.get_user_team_ids(username), dry_run)

        logging.debug('Deleting users')
        for username in sorted(users_to_delete):
            delete_user(ac_api, self.get_user_by_username(username), dry_run)

        # Update existing users
        for username in cur_users & new_users:
            old_user = self.get_user_by_username(username)
            old_team_ids = self.get_user_team_ids(username)
            new_user = new_model.get_user_by_username(username)
            new_team_ids = new_model.get_user_team_ids(username)

            updates = old_user.get_updates(new_user, old_team_ids, new_team_ids)
            if updates:
                logging.debug(f'Setting updates[{USER_ID}] to {old_user.user_id}')
                updates[USER_ID] = old_user.user_id
                logging.debug(f'updates for {username}: {updates}')
                update_user(ac_api, updates, dry_run)

    def get_user_by_username(self, username):
        """Given a username, return the corresponding user object.

        In a valid configuration, if a user belongs to multiple teams,
        the user's details should be identical in each team so it
        doesn't matter which one we return.

        """
        team_map = self.user_map[username]
        for user in team_map.values():
            return user

    def get_user_team_ids(self, username):
        """Returns a set of team ids of which the specified user is a member."""
        team_ids = []
        for team_full_name in self.user_map[username]:
            team = self.team_map[team_full_name]
            if not team or not team.team_id:
                raise RuntimeError(f'Cannot determine team ID for {team_full_name}')
            team_ids.append(team.team_id)
        return set(team_ids)


class RoleManager:

    def __init__(self, ac_api):

        self.all_roles = ac_api.get_all_roles()
        logging.debug(f'all_roles: {[r.name for r in self.all_roles]}')

    def name_from_id(self, role_id):
        for role in self.all_roles:
            if role.id == role_id:
                return role.name

        raise ValueError(f'{role_id}: invalid role ID')

    def id_from_name(self, role_name):
        for role in self.all_roles:
            if role.name == role_name:
                return role.id

        raise ValueError(f'{role_name}: invalid role name')

    def valid_role_by_name(self, role_name):
        for role in self.all_roles:
            if role.name == role_name:
                return True

        return False


class AuthenticationProviderManager:

    def __init__(self, ac_api):

        self.authentication_providers = ac_api.get_all_authentication_providers()

    def name_from_id(self, provider_id):

        for provider in self.authentication_providers:
            if provider.id == provider_id:
                return provider.name

        raise ValueError(f'{provider_id}: invalid authentication provider ID')

    def id_from_name(self, provider_name):

        for provider in self.authentication_providers:
            if provider.name == provider_name:
                return provider.id

        raise ValueError(f'{provider_name}: invalid authentication provider name')

class InconsistentUser:

    def __init__(self, property, username, team_a, team_b, value_a, value_b):

        self.property = property
        self.username = username
        self.team_a = team_a
        self.team_b = team_b
        self.value_a = value_a
        self.value_b = value_b

    def __repr__(self):

        return f'InconsistentUser({self.property}, {self.username}, {self.team_a}, {self.team_b}, {self.value_a}, {self.value_b})'


class InvalidDefaultRole:

    def __init__(self, team_full_name, role):

        self.team_full_name = team_full_name
        self.role = role

    def __repr__(self):

        return f'InvalidDefaultRole({self.team_full_name}, {self.role})'


class InvalidRole:

    def __init__(self, team_full_name, username, role):

        self.team_full_name = team_full_name
        self.username = username
        self.role = role

    def __repr__(self):

        return f'InvalidRole({self.team_full_name}, {self.username}, {self.role})'


class MissingDefaultAttribute:

    def __init__(self, username, team_full_name, attr):

        self.username = username
        self.team_full_name = team_full_name
        self.attr = attr

    def __repr__(self):

        return f'MissingDefaultAttribute({self.username}, {self.team_full_name}, {self.attr})'

class ModelValidationError(Exception):

    def __init__(self, errors):

        self.errors = errors

    def __str__(self):

        return f'ModelValidationError({self.errors})'

def get_team_parent_name(full_name):
    '''Given a team's full name, return it's parent team's full name'''
    return '/'.join(full_name.split('/')[0:-1])


def retrieve_teams(ac_api, options):
    logging.info('retrieve_teams')
    cx_teams = ac_api.get_all_teams()
    cx_users = ac_api.get_all_users()
    teams = []
    for cx_team in cx_teams:
        logging.debug(f'cx_team: {cx_team}')
        team = Team(cx_team.name, cx_team.full_name, team_id=cx_team.id)
        for cx_user in cx_users:
            roles = [role_manager.name_from_id(r) for r in cx_user.role_ids]
            if cx_team.id in cx_user.team_ids:
                logging.debug(f'Adding user {cx_user.username} to team {cx_team.full_name}')
                authentication_provider_name = authentication_provider_manager.name_from_id(cx_user.authentication_provider_id)
                user = User(cx_user.username, cx_user.email,
                            cx_user.first_name, cx_user.last_name,
                            authentication_provider_name,
                            cx_user.locale_id, roles, cx_user.active,
                            cx_user.allowed_ip_list,
                            cx_user.cell_phone_number, cx_user.country,
                            cx_user.expiration_date, cx_user.job_title,
                            cx_user.other, cx_user.phone_number,
                            cx_user.id)
                user.validate()
                team.add_user(user)

        teams.append(team)

    return teams


def extract(ac_api, options):
    logging.info('extract')
    for team in retrieve_teams(ac_api, options):
        team.save(options.dest_dir)


def update(ac_api, options):
    logging.info('update')
    cur_teams = retrieve_teams(ac_api, options)
    cur_model = Model(cur_teams)
    new_model = validate(ac_api, options)
    cur_model.apply_changes(ac_api, new_model, options.dry_run)


def validate(ac_api, options):
    logging.info(f'Validating files in {options.data_dir}')
    teams = Team.load_dir(options.data_dir)
    model = Model(teams)
    errors = model.validate()
    if errors:
        logging.error('Model failed validation')
        raise ModelValidationError(errors)

    logging.info('Model validated successfully')
    return model


def create_team(ac_api, team_name, team_parent_id, dry_run):
    logging.info(f'Creating team {team_name} under parent {team_parent_id}')
    if not dry_run:
        ac_api.create_new_team(team_name, team_parent_id)


def delete_team(ac_api, team_id, dry_run):
    logging.info(f'Deleting team {team_id}')
    if not dry_run:
        ac_api.delete_a_team(team_id)


def create_user(ac_api, user, team_ids, dry_run):
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


def delete_user(ac_api, user, dry_run):
    logging.info(f'Deleting user {user.username} ({user.user_id})')
    if not dry_run:
        ac_api.delete_a_user(user.user_id)


def update_user(ac_api, updates, dry_run):
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


def usage(ac_api, args):

    print(f'''usage: py {sys.argv[0]} <extract|update|validate> [args]''')


if __name__ == '__main__':

    ac_api = AccessControlAPI()
    parser = argparse.ArgumentParser(prog='PTUM')
    parser.add_argument('--log-format', type=str,
                        default='%(asctime)s | %(levelname)s | %(funcName)s: %(message)s',
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
    validate_parser.set_defaults(func=validate)

    args = parser.parse_args([arg for arg in sys.argv[1:]
                              if not arg.startswith('--cxsast')])
    logging.basicConfig(level=args.log_level, format=args.log_format)

    try:
        authentication_provider_manager = AuthenticationProviderManager(ac_api)
        role_manager = RoleManager(ac_api)
        args.func(ac_api, args)
    except Exception as e:
        logging.error(f'{args.func.__name__} failed: {e}', exc_info=True)
        sys.exit(1)

    sys.exit(0)
