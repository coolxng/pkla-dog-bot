"""Flask entrypoint for deployment platforms that scan conventional app files.

Route all conventional app imports through the verification-safe entrypoint so
platforms that auto-detect ``app:app`` cannot bypass deployment safeguards or
omit the public policy/support routes.
"""

from verification_entry import bot

app = bot.app

if __name__ == "__main__":
    from verification_entry import main

    main()
