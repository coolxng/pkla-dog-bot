# Changelog

## Unreleased

- Add optional SQLite persistence for universal memory and conversation history via `PERSIST_STATE`.
- Require `/say` control posts to be authenticated instead of allowing unauthenticated controls when `EXTERNAL_SAY_CONTROL_TOKEN` is unset.
- Require Mute Members permission for `/pingdeaf`.
- Add GitHub Actions CI for dependency installation and unit tests.
- Add project metadata files for license and contribution guidance.
- Update the `ddgs` dependency pin to an available PyPI release.
