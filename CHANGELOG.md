# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
but this project **does not adhere** to Semantic Versioning.

https://[api.]imager.kiwix.org are auto-deploying `main`.

## [Unreleased]

### Changed

- [manager.builder] Including Kiwix macOS 3.12.0

## [2025-12] - 2025-12-02

### Added

- [health-check] New existence check for all auto-iamges's HTTP URL (200 OK)
- [health-check] New S3 auto-delete date check for all auto-images (fail if less than 4d)
- [scheduler.periodic-tasks] auto-extending S3 deletion dates for auto-images under 5d
- [scheduler.emailing] Added support for requested-delivery time in emails (max 3d)
- [scheduler.stripe] Customer now added to CRM upon Strip webhook
- [scheduler.stripe] New Sales CSV export endpoint.
- [scheduler.stripe] Preppers Premium Package (H1 and OS-only)
- [scheduler.stripe] Record StripeSession on successful transactions
- [scheduler] `SKIP_PRESTART` dev-only ENV to skip prestart
- [manager] Added variant support (Demo, Preppers, etc)

### Fixed

- [scheduler.stripe] Webhook failing if no discount on device order
- [scheduler.stripe] Email dates zero-padded hours and minutes
- [scheduler.periodic_tasks] Task.get_size() used in cleanup
- [scheduler] Skipping creator tasks without order
- [manager] Multiple config creation instead of update (#496)

### Changed

- [scheduler.api] Endpoint `/auto-images/:slug` now includes `autodelete_on` (ISO date)
- [scheduler.stripe] Email date now aligned with order time if webhook runs late
- [scheduler.stripe] Update Shop card design 1 / 2 / 3 columns. SD size req moved next to OS-only
- [scheduler.email] Image order creation design improved for clarity (button, size, wording)
- [scheduler.email] Image ready design improved for clarity (button, size, highlight important)
- [scheduler.assembly] Shipment tracking number delays its email to client by 24h
- [manager] Orders and config listings:
  - Common
    - harmonized look of both config and orders list
    - 20 items per page (should be enough for most users to skip pagination)
    - Lighter table design
    - using purple as link and button color
    - Better formatting of dates with new `human_date` filter
  - Orders listing
    - Using “Your xx” wording
    - Simplified subtext
    - Removed filters (not that useful)
    - Order status now in colored badge
  - Configs listing
    - Reduced Export/Clone/Delete buttons to icon-only
    - Removed Media size column
    - Config size now red if it cannot fit on any media
- [manager] Current Tab (and ZIM language) now preserved upon save
- [manager] New simpler order detail page with download buttons
- [manager.builder] Including Kiwix macOS 3.11.0
- [manager] Now running on bookwork (python 3.8)
- [manager] Using offspot-config 2.9.0
- [manager] Using base-image 1.4.0

### Removed

- [scheduler.stripe] TED Talks Package
- [scheduler.stripe] Shipping to US (with banner in shop)

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
