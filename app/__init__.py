from flask import Flask
from app.routes.webhooks import webhooks_bp


def create_app():
    # Creamos la aplicación principal
    app = Flask(__name__)

    # Le pegamos la "etiqueta" (Blueprint) que contiene todas tus rutas de webhooks
    app.register_blueprint(webhooks_bp)

    return app