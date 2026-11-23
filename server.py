"""
Legacy compatibility entrypoint.

The new preferred entrypoint is `main_server/server.py`. This wrapper keeps
`python server.py` working for older scripts and local habits.
"""

from main_server.server import app


if __name__ == "__main__":
    from main_server.server import main

    main()
