# CxMGMTaC

`CxMGMTaC.py` is a Python script that allows several CxSAST entities
to be managed by a *config-as-code* approach.

# Installation

`CxMGMTaC.py` depends on two external packages:

- CheckmarxPythonSDK
- PyYAML

The simplest way to install these is by using the **pip** command:

```
pip install -r requirements.txt
```

This can, of course, be done in a virtual environment.

## Offline Installation

Each release includes a zip file that contains the CxMGMTaC script’s
dependencies for offline installation. This file is called
`CxMGMTaC-N.N.N-with-deps.zip`. When the contents of this file are
extracted, the script’ dependencies, in the form of Python _wheel_
files, will be in the `wheels` directory. These can be installed using
the **pip3** command which comes with Python itself. Only the
`CheckmarxPythonSDK` and `PyYAML` wheel need to be explicitly
installed.

For example, assuming the zip file has been extracted under `/tmp`:

```
pip3 install CheckmarxPythonSDK --no-index --find-links /tmp/CxMGMTaC-N.N.N-with-deps/wheels
pip3 install PyYAML --no-index --find-links /tmp/CxMGMTaC-N.N.N-with-deps/wheels
```


# Usage

`CxMGMTaC.py` has three modes of operation:

- Extract
- Update
- Validate

## Extract Mode

Extract mode reads data from CxSAST and writes the corresponding
config-as-code files to the specified directory.

### Example

```
C:\...\> py CxMGMTaC.py extract -d data
```

This command will read the data from CxSAST and create the appropriate
YAML files under the `data` directory, creating it if it does not
already exist.

## Update Mode

Update mode reads files from the specified directory, reads data from
CxSAST, and applies any changes in the files to CxSAST.

### Example

```
C:\...\> py CxMGMTaC.py update -d data
```

## Validate Mode

Validate mode reads files from the specified directory and performs
consistency checks.

### Example

```
C:\...\> py CxMGMTaC.py validate -d data
```

## Retrieving User Details from an LDAP Server

The validate mode can optionally retrieve user details from an LDAP
server. This is enabled by passing either the `-r` or
`--retrieve-user-entries` command line option. If one of thes options
i passed and a user reference is found in a team file for which there
is not corresponding user entry in the `users.yml` file, the script
will try to retrieve the user’s details from the LDAP server specified
in the user reference. The comparison between the username in the team
file and the username(s) retrieved from the LDAP server is
case-insensitive.

The following fields are retrieved from the LDAP server:

* `email`
* `first_name`
* `last_name`
* `username`

The validate mode writes an updated copy of the `users.yml` file with
a new entry for the user retrieved from the LDAP server. As the
`active` and `locale_id` fields are mandatory, default values for
these fields must be provided in the `users.yml` file otherwise the
new user entry will be invalid.

If the user entry retrieved from the LDAP server has a `first_name`
field whose value is `null`, the value of the `username` field is
used.

If the user entry retrieved from the LDAP server has a `last_name`
field whose value is `null`, the value of the `username` field is
used.

If the user entry retrieved from the LDAP server has an `email` field
whose value is `null`, a dummy email address is used comprised of the
`username` field and the user reference’s
`authentication_provider_name` field.

For example, given the following user reference:

```
- authentication_provider_name: CorpDirectory
  username: testuser
```

If the user entry retrieved from the LDAP server had an `email` field with a value of `null`, the following value would be used:

```
testuser@CorpDirectory
```

### Example

```
C:\...\> py CxMGMTaC.py validate -d data -r
```

# Directory Structure and File Formats

The `CxMGMTaC.py` script, when run in `extract` mode, will crate two
directories: `teams` and `users`. In the `teams` directory, it will
create a YAML file for each team in Access Control. For each team that
has child teams, it will also create a subdirectory to hold the YAML
files for the child teams. In the `users` directory, it will create a
single file, `users.yml`, with the details of the users in Access
Control.

# The Team File Format

The data for each team is stored in a YAML file.

The following properties are mandatory:

- `full_name`
- `name`

- `users`

## User Entries

All user entries must provide values for the following properties:

- `authentication_provider_name`
- `username`

## Example

Here is an example team file:

```
full_name: /CxServer
name: CxServer
users:
- authentication_provider_name: Application
  email: admin@cx.au
```

# The Users File Format

The following property is mandatory:

- `users`

The following properties are optional:

- `default_active`
- `default_authentication_provider_name`
- `default_locale_id`
- `default_roles`

If any of these properties are present, for a user entry that lacks
the corresponding property, the value of this property is used.

## Example

Here is an eample `users.xml` file:

```
default_active: true
users:
- authentication_provider_name: Application
  email: admin@cx.au
  first_name: admin
  last_name: admin
  roles:
  - SAST Admin
  - Access Control Manager
  username: admin
```

# Troubleshooting

The `-l` (or `--log-level`) command line option controls the
granularity of logging. By default, only messages of `INFO` severity
and higher are logged. To enable debug logging, add one of the
following to the command line.

```
-l DEBUG
```

```
--log-level DEBUG
```

Note that this argument should come before the subcommand. That is:

```
C:\...\> py CxMGMTaC.py -l DEBUG extract -d data
```

For more sophisticated control over logging, a logging configuration
file may be specified using the `--log-config` command line option.

See the [Python
documentation](https://docs.python.org/3/library/logging.config.html#logging-config-fileformat)
for a description of the logging configuration file format.

# Unit Testing

The `test.py` script in the `tests` directory runs the unit test
suite. The unit tests use mock responses from CxSAST so the unit test
suite can be run without access to a live CxSAST instance.

The default log level for the unit test suite is `WARNING`. To change
this, set the `LOG_LEVEL` environment variable to the desired log
level. For example (on Windows):

```
$ LOG_LEVEL=INFO py test.py
INFO | retrieve_from_access_control: Retrieving user and team data from Access Control
INFO | apply_changes: Applying changes
INFO | add_teams: Adding teams
INFO | create_team: Creating team test4 under parent 1
INFO | add_users: Adding users
INFO | update_users: Updating users
INFO | delete_users: Deleting users
INFO | delete_teams: Deleting teams
.INFO | retrieve_from_access_control: Retrieving user and team data from Access Control
...
```

# Building Releases with Dependencies

The releases of the `CxMGMTaC.py` script include a release file that
includes third party dependencies (in the form of *wheel* files) for
offline installation. These releases are created using the
`make-release.sh` script in the `tools` directory.
