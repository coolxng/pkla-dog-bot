"""Flask entrypoint for deployment platforms that scan conventional app files."""

from bot import app


if __name__ == "__main__":
    from bot import main

    main()
