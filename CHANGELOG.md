# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
but this project **does not adhere** to Semantic Versioning.

https://[api.]imager.kiwix.org are auto-deploying `main`.

## [Current]

### Added

- [health-check] New existence check for all auto-iamges's HTTP URL (200 OK)
- [health-check] New S3 auto-delete date check for all auto-images (fail if less than 4d)
- [scheduler.periodic-tasks] auto-extending S3 deletion dates for auto-images under 5d

### Changed

- [scheduler] Endpoint `/auto-images/:slug` now includes `autodelete_on` (ISO date)

## [2025-05] - 2025-05-07

### Added

- CHANGELOG
- Ability to close the shop via `SHOP_IS_DISABLED` environ
- Versioning.
  - Imager-Service is now *versioned*: we still deploy continuously from main
    but we have a roughly-dated changelog that is tagged about monthly.
  - `manager.__about__.get_version()` to return that version
  - Also accepts `extended` param to return git commit SHA (short)
  - [manager] Version (extended) is shown on Admin page

### Changed

- [manager] Using offspot-config 2.6.1
- [manager.builder] Now setting Hotspot version as imager-service version

## [Unnamed] - 2025-05-06

- No release management, no CHANGELOG
