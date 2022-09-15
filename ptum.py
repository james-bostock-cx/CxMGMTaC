import argparse
import copy
import logging
import os
import pathlib
import sys
import yaml

from CheckmarxPythonSDK.CxRestAPISDK import AccessControlAPI

# Constants for dictionary access
AUTHENTICATION_PROVIDER_ID = 'authenticationProviderId'
DEFAULT_ROLES = 'defaultRoles'
EMAIL = 'email'
FIRST_NAME = 'firstName'
FULL_NAME = 'fullName'
LAST_NAME = 'lastName'
LOCALE_ID = 'localeId'
NAME = 'name'
ROLES = 'roles'
USERNAME = 'username'
USERS = 'users'

# The following are for when we update a user and have to match the
# corresponding parameters of the update_a_user method

U_EMAIL = 'email'
U_FIRST_NAME = 'first_name'
U_LAST_NAME = 'last_name'
U_LOCALE_ID = 'locale_id'
U_ROLE_IDS = 'role_ids'
U_TEAM_IDS = 'team_ids'
U_USER_ID = 'user_id'

# Global variables
role_manager = None

class Team:

    def __init__(self, name, full_name, default_roles=[], team_id=None):
        self.team_id = team_id
        self.name = name
        self.full_name = full_name
        self.default_roles = default_roles
        self.users = []

    def add_user(self, user):

        self.users.append(user)

    def to_dict(self):
        """Generate a dictionary representation of the team (which leads to
        prettier YAML output)."""

        return {
            NAME: self.name,
            FULL_NAME: self.full_name,
            DEFAULT_ROLES: self.default_roles,
            USERS: [user.to_dict() for user in self.users]
        }

    @staticmethod
    def from_dict(d):
        logging.debug(f'd: {d}')
        type_check([
            (d[NAME], str, NAME),
            (d[FULL_NAME], str, FULL_NAME),
            (d[DEFAULT_ROLES], list, DEFAULT_ROLES)
        ])
        team = Team(d[NAME], d[FULL_NAME], d[DEFAULT_ROLES])
        for ud in d[USERS]:
            team.add_user(User.from_dict(ud))

        return team

    def save(self, dest_dir="."):
        """Save the team to a file in the specified directory.

        The filename is the team's full name, URL encoded, with a ".yml" suffix.
        """
        logging.debug(f'Team.save: full_name: {self.full_name}, dest_dir: {dest_dir}')

        path = pathlib.Path(dest_dir) / pathlib.Path(f'./{self.full_name}.yml')
        logging.info(f'Saving team {self.name} to {path}')
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            print(yaml.dump(self.to_dict(), Dumper=yaml.CDumper),
                  file=f)

    @staticmethod
    def load(filename):
        logging.debug(f'Loading team from {filename}')
        with open(filename, 'r') as f:
            data = yaml.load(f, Loader=yaml.CLoader)
            return Team.from_dict(data)

    @staticmethod
    def load_dir(dirname):
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

        return teams

    def validate_default_roles(self, errors):
        logging.debug(f'Validating default roles for {self.full_name}')
        for role in self.default_roles:
            if not role_manager.valid_role_by_name(role):
                logging.error(f'default role {role} for team {self.full_name} is not a valid role')
                errors.append(InvalidDefaultRole(self.full_name, role))

    def __str__(self):
        return f'Team[name={self.name},full_name={self.full_name}'

    def __repr__(self):

        return f'Team({self.name}, {self.full_name}, {self.default_roles})'


class User:

    def __init__(self, username, email, first_name, last_name,
                 authentication_provider_id, locale_id, roles=[],
                 user_id=None):

        self.user_id = user_id
        self.username = username
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.authentication_provider_id = authentication_provider_id
        self.locale_id = locale_id
        self.roles = roles

    def to_dict(self):
        """Generate a dictionary representation of the user (which leads to
        prettier YAML output)."""

        return {
            USERNAME: self.username,
            EMAIL: self.email,
            FIRST_NAME: self.first_name,
            LAST_NAME: self.last_name,
            AUTHENTICATION_PROVIDER_ID: self.authentication_provider_id,
            LOCALE_ID: self.locale_id,
            ROLES: self.roles
        }

    @staticmethod
    def from_dict(d):
        logging.debug(f'd: {d}')
        roles = d.get(ROLES, [])
        return User(d[USERNAME], d[EMAIL], d[FIRST_NAME], d[LAST_NAME],
                    d[AUTHENTICATION_PROVIDER_ID], d[LOCALE_ID],
                    roles)

    def validate_roles(self, errors, team_full_name):
        logging.debug(f'Validating roles of user {self.username}')
        for role in self.roles:
            if not role_manager.valid_role_by_name(role):
                logging.error(f'Role {role} for user {self.username} in team {team_full_name} is not a valid role')
                errors.append(InvalidRole(team_full_name, self.username, role))

    def get_updates(self, other):

        #logging.debug(f'Comparing {self} with {other}')
        updates = {}
        if self.username != other.username:
            raise valueError(f'Cannot generate updates for different users ({self.username} and {other.username})')
        if self.email != other.email:
            updates[U_EMAIL] = other.email
        if self.first_name != other.first_name:
            updates[U_FIRST_NAME] = other.first_name
        if self.last_name != other.last_name:
            updates[U_LAST_NAME] = other.last_name
        if self.authentication_provider_id != other.authentication_provider_id:
            raise ValueError('Cannot change authentication provider ID')
        if self.locale_id != other.locale_id:
            updates[U_LOCALE_ID] = other.locale_id
        if self.roles != other.roles:
            updates[U_ROLE_IDS] = [role_manager.role_id_from_name(r) for r in other.roles]

        return updates

    def __repr__(self):

        return f'User({self.username}, {self.email}, {self.first_name}, {self.last_name}, {self.authentication_provider_id}, {self.locale_id}, {self.roles})'


class Model:

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
        logging.debug('Validating model')

        errors = []
        self.validate_default_roles(errors)
        self.validate_users(errors)
        return errors

    def validate_default_roles(self, errors):
        # make sure that all default roles are valid roles
        logging.debug('Validating default roles')
        for team in self.teams:
            team.validate_default_roles(errors)

    def validate_users(self, errors):
        # Make sure users are consistent across all teams
        for username in self.user_map:
            self.validate_user(errors, username, self.user_map[username])

    def validate_user(self, errors, username, team_user_map):
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
                first_roles = self.get_user_roles(first_user, first_team)
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
                roles = self.get_user_roles(user, team)
                if first_roles != roles:
                    logging.debug(f'{first_roles} != {roles}')
                    errors.append(InconsistentUser('roles',
                                                   first_user.username,
                                                   first_team.full_name,
                                                   team_full_name,
                                                   first_roles,
                                                   roles))

    def get_user_roles(self, user, team):
        logging.debug(f'user: {user}, team: {team}')
        if user.roles:
            logging.debug(f'Using user\'s roles: {user.roles}')
            return user.roles
        else:
            logging.debug(f'Using team\'s roles: {team.default_roles}')
            return team.default_roles

    def apply_changes(self, ac_api, new_model, dry_run):
        logging.debug('Applying changes')
        self.apply_team_changes(ac_api, new_model, dry_run)
        self.apply_user_changes(ac_api, new_model, dry_run)

    def apply_team_changes(self, ac_api, new_model, dry_run):
        logging.debug('Applying team changes')
        cur_team_names = set(self.team_map.keys())
        new_team_names = set(new_model.team_map.keys())
        teams_to_create = new_team_names - cur_team_names
        teams_to_delete = cur_team_names - new_team_names

        logging.debug('Creating new teams')
        team_map = copy.deepcopy(self.team_map)
        for team_full_name in sorted(teams_to_create):
            team = new_model.team_map[team_full_name]
            parent_full_name = get_team_parent_name(team_full_name)
            parent_id = team_map[parent_full_name].team_id
            team_id = create_team(ac_api, team.name, parent_id, dry_run)
            team.team_id = team_id
            team_map[team.full_name] = team

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
        logging.debug('Applying user changes')

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

            updates = old_user.get_updates(new_user)
            if updates:
                updates[U_USER_ID] = old_user.user_id
                if old_team_ids != new_team_ids:
                    updates[U_TEAM_IDS] = new_team_ids
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
        team_ids = []
        for team_full_name in self.user_map[username]:
            team = self.team_map[team_full_name]
            if not team or not team.team_id:
                raise RuntimeError(f'Cannot determine team ID for {team_full_name}')
            team_ids.append(team.team_id)
        return team_ids


class RoleManager:

    def __init__(self, ac_api):

        self.all_roles = ac_api.get_all_roles()
        logging.debug(f'all_roles: {[r.name for r in self.all_roles]}')

    def role_name_from_id(self, role_id):
        for role in self.all_roles:
            if role.id == role_id:
                return role.name

        raise ValueError(f'{role_id}: invalid role ID')

    def role_id_from_name(self, role_name):
        for role in self.all_roles:
            if role.name == role_name:
                return role.id

        raise ValueError(f'{role_name}: invalid role name')

    def valid_role_by_name(self, role_name):
        for role in self.all_roles:
            if role.name == role_name:
                return True

        return False


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
            roles = [role_manager.role_name_from_id(r) for r in cx_user.role_ids]
            if cx_team.id in cx_user.team_ids:
                team.add_user(User(cx_user.username, cx_user.email,
                                   cx_user.first_name, cx_user.last_name,
                                   cx_user.authentication_provider_id,
                                   cx_user.locale_id, roles, cx_user.id))
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


def create_team(self, ac_api, team_name, team_parent_id, dry_run):
    logging.debug(f'Creating team {team_name} under parent {team_parent_id}')
    if not dry_run:
        team_id = ac_api.create_new_team(team_name, team_parent_id)
        logging.debug(f'New team_id is {team_id}')


def delete_team(ac_api, team_id, dry_run):
    logging.debug(f'Deleting team {team_id}')
    if not dry_run:
        ac_api.delete_a_team(team_id)


def create_user(ac_api, user, team_ids, dry_run):
    logging.debug(f'Creating user {user.username}')
    if not dry_run:
        role_ids = [role_manager.role_id_from_name(r) for r in user.roles]
        ac_api.create_new_user(user.username, '', role_ids, team_ids,
                               user.authentication_provider_id, user.first_name,
                               user.last_name, user.email, '', '', '', '', '',
                               True, None, None, user.locale_id)


def delete_user(ac_api, user, dry_run):
    logging.debug(f'Deleting user {user.username} ({user.user_id})')
    if not dry_run:
        ac_api.delete_a_user(user.user_id)


def update_user(ac_api, updates, dry_run):
    logging.debug(f'Updating user with ID {updates[U_USER_ID]}')
    if not dry_run:
        ac_api.update_a_user(**updates)


def type_check(items):
    for item in items:
        if type(item[0]) != item[1]:
            raise TypeError(f'Type of {item[2]} is {type(item[0])} (expected {item[1]})')


def usage(ac_api, args):

    print(f'''usage: py {sys.argv[0]} <extract|update|validate> [args]''')


if __name__ == '__main__':

    ac_api = AccessControlAPI()
    parser = argparse.ArgumentParser(prog='PTUM')
    parser.add_argument('--log-format', type=str,
                        default='%(asctime)s | %(levelname)s | %(funcName)s: %(message)s',
                        help='The log format')
    parser.add_argument('--log-level', type=str, default='INFO',
                        help='The log level')
    parser.set_defaults(func=usage)
    subparsers = parser.add_subparsers(help='sub-command help')

    # Parser for the extract command
    extract_parser = subparsers.add_parser('extract')
    extract_parser.add_argument('--dest-dir', type=str, default='.',
                                help='Destination directory')
    extract_parser.set_defaults(func=extract)

    # Parser for the update command
    update_parser = subparsers.add_parser('update')
    update_parser.add_argument('--data-dir', type=str, default='.',
                               help='Data directory')
    update_parser.add_argument('--dry-run', action='store_true', default=False,
                               help='Display updates without performing them')
    update_parser.set_defaults(func=update)

    # Parser for the validate command
    validate_parser = subparsers.add_parser('validate')
    validate_parser.add_argument('--data-dir', type=str, default='.',
                                 help='Data directory')
    validate_parser.set_defaults(func=validate)

    args = parser.parse_args([arg for arg in sys.argv[1:]
                              if not arg.startswith('--cxsast')])
    logging.basicConfig(level=args.log_level, format=args.log_format)

    try:
        role_manager = RoleManager(ac_api)
        args.func(ac_api, args)
    except Exception as e:
        logging.error(f'{args.func.__name__} failed: {e}', exc_info=True)

    sys.exit(0)
