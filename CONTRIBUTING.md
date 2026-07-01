# Contributing

## Local checks

Use Python 3.11 and install the pinned runtime dependencies:

```sh
python -m pip install -r requirements-dev.txt
ruff check .
mypy bot.py audio_relay.py pcm_relay.py browser_talk.py
python -m unittest discover -s tests
```

FFmpeg and libopus must be available for voice-related runtime behavior. Unit tests mock most Discord voice paths, but CI installs both so the test environment matches deployment more closely.

## Change guidelines

- Keep changes small and focused.
- Add or update tests for command behavior, external `/say` controls, uploads, and voice state changes.
- Do not commit real tokens, API keys, `.env` files, logs, virtualenvs, or generated caches.
- Keep `EXTERNAL_SAY_CONTROL_TOKEN` configured for any public deployment.

