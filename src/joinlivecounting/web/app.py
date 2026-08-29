import logging

from flask import Flask

from .. import config, storage
from ..reddit import scanner
from .routes import bp


def create_app() -> Flask:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    application = Flask(__name__)
    application.secret_key = config.FLASK_SECRET_KEY
    storage.init()
    scanner.start()
    application.register_blueprint(bp)
    return application


app = create_app()
