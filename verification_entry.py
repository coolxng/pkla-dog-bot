"""Verification-safe production entrypoint for pkla dog.

This entrypoint keeps the existing bot implementation intact while disabling
features that should not be exposed by the public/verified deployment.
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import Response
from markupsafe import escape

# These must be set before importing bot.py because the state store and client
# configuration are created at import time.
os.environ["PERSIST_STATE"] = "false"
os.environ["AUTO_MEMORY_ENABLED"] = "false"
os.environ["ENABLE_LISTEN_IN"] = "false"

# The public/verified deployment must not forward Discord messages to an
# arbitrary external ingest endpoint.
os.environ.pop("POKE_INGEST_URL", None)

import bot  # noqa: E402  (environment must be locked before this import)

ROOT = Path(__file__).resolve().parent


def _legal_page(filename: str, title: str) -> Response:
    """Render a repository Markdown policy as a readable public HTML page."""

    policy_path = ROOT / filename
    try:
        policy_text = policy_path.read_text(encoding="utf-8")
    except OSError:
        return Response("Policy document is unavailable.", status=503, mimetype="text/plain")

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{
      margin: 0;
      background: #0b0b0d;
      color: #f2f3f5;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      line-height: 1.6;
    }}
    main {{
      width: min(900px, calc(100% - 40px));
      margin: 48px auto;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font: inherit;
    }}
    a {{ color: #8ea1e1; }}
  </style>
</head>
<body>
  <main><pre>{escape(policy_text)}</pre></main>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@bot.app.get("/terms")
def terms_page() -> Response:
    return _legal_page("TERMS.md", "pkla dog Terms of Service")


@bot.app.get("/privacy")
def privacy_page() -> Response:
    return _legal_page("PRIVACY.md", "pkla dog Privacy Policy")


@bot.app.get("/support")
def support_page() -> Response:
    return _legal_page("SUPPORT.md", "pkla dog Support")


# /pingdeaf repeatedly DMed another member without that member first opting in.
# Discord's Developer Policy requires explicit permission before contacting users,
# so the public deployment does not register or sync this command.
removed_pingdeaf = bot.command_tree.remove_command("pingdeaf")
if removed_pingdeaf is not None:
    bot.logger.info("Verification mode: /pingdeaf removed from the global command tree")


async def _disabled_external_message_ingest(_message) -> None:
    """Prevent the legacy Poke ingest path from transmitting Discord messages."""

    return None


# on_message resolves this module global at call time, so replacing the function
# here prevents forwarding even if POKE_INGEST_URL is added to the process later.
bot.post_message_to_poke = _disabled_external_message_ingest


def main() -> None:
    bot.logger.info(
        "Starting verification-safe deployment: persistence, auto-memory, "
        "browser listen-in, Poke ingest, and /pingdeaf are disabled"
    )
    bot.main()


if __name__ == "__main__":
    main()
