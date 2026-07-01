# Changelog

## Unreleased

- Fix `!deletedms` to honor `OWNER_ID` instead of the hardcoded default owner.
- Add Ruff and mypy to CI and `requirements-dev.txt`.
- Remove stale `ENABLE_TRANSCRIPTION` and Piper TTS entries from `.env.example`.
- Require `/say` control posts to be authenticated instead of allowing unauthenticated controls when `EXTERNAL_SAY_CONTROL_TOKEN` is unset.
- Require Mute Members permission for `/pingdeaf`.
- Add GitHub Actions CI for dependency installation and unit tests.
- Add project metadata files for license and contribution guidance.
- Update the `ddgs` dependency pin to an available PyPI release.
