import logging

from flask import request

from . import config

logger = logging.getLogger("lendwise")


def init_logging() -> None:
    """Send application logs to <data dir>/logs/app.log (re-initialised per app instance)."""
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    handler = logging.FileHandler(config.path("logs", "app.log"))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False


def register(app) -> None:
    @app.before_request
    def _log_request():
        logger.debug("request body=%s", request.get_data(as_text=True))  # PLANTED:V1:log
