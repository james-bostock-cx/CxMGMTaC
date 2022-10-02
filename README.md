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

# The Team File Format

The data for each team is stored in a YAML file.

The following properties are mandatory:

- full\_name
- name

The following peoperties are optional:

- default\_active
- default\_allowed_ip_list
- default\_authentication_provider_id
- default\_locale_id
- default\_roles
- users

The properties starting with “default\_” apply to all users in the
team unless overridden at the user level.

The following section describes the properties of the user entries.


## User Entries

All user entries must provide values for the following properties:

- email
- first\_name
- last\_name
- username

The following properties will be inherited from the team’s
corresponding default properties:

- active
- allowed\_ip\_list
- authentication\_provider\_id
- locale\_id
- roles

The following properties are optional:

- cell\_phone\_number
- country
- expiration\_date
- job\_title
- other
- phone\_number

## Example

Here is an example team file:

```
default_active: true
default_authentication_provider_id: 1
default_locale_id: 1
full_name: /CxServer
name: CxServer
users:
- authentication_provider_id: 1
  email: admin@cx.au
  first_name: admin
  last_name: admin
  roles:
  - SAST Admin
  - SAST Auditor
  - Access Control Manager
  - CxAnalytix
  - CxReportingService
  - Admin
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
