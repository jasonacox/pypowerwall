# TeslaPy Release Notes

This fork is maintained as part of pypowerwall. Original repository: https://github.com/tdorssers/TeslaPy

## v2.9.2 - Fix Backup History API Endpoint

* Fix backup event history retrieval after Tesla deprecated `/api/v2/energy_site/backup_history` endpoint
* Update `get_history_data()` to use `CALENDAR_HISTORY_DATA` endpoint when `kind='backup'`
* Addresses issue where backup history queries returned 410 Gone errors
* See: https://github.com/jasonacox/Powerwall-Dashboard/issues/714

## v2.9.1 - Initial Fork

* Forked from TeslaPy version 2.9.0 (https://github.com/tdorssers/TeslaPy)
* Embedded into pypowerwall to provide timely fixes for Tesla API changes
* Original TeslaPy repository is no longer actively maintained
* See: https://github.com/jasonacox/pypowerwall/issues/197

---

## Original TeslaPy Credits

TeslaPy was created and maintained by Tim Dorssers.

Copyright (c) 2019 Tim Dorssers

Licensed under the MIT License. See the LICENSE file for details.
