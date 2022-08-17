from flask import Flask
from project import events

def create_app():
    app = Flask(__name__)
    app.register_blueprint(events.bp)
    return app