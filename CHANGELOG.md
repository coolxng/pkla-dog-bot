# Changelog

## Unreleased

- Add `/health` JSON endpoint for Discord readiness, uptime, and voice relay state.
- Replace the Flask dev server with gevent WSGI by default for production WebSocket support.
- Add structured logging via the `LOG_LEVEL` environment variable.
- Require `/say` control posts to be authenticated instead of allowing unauthenticated controls when `EXTERNAL_SAY_CONTROL_TOKEN` is unset.
- Require Mute Members permission for `/pingdeaf`.
- Add GitHub Actions CI for dependency installation and unit tests.
- Add project metadata files for license and contribution guidance.
- Update the `ddgs` dependency pin to an available PyPI release.
