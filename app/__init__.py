from flask import Flask
from app.routes.webhooks import webhooks_bp
from app.database import init_db


def create_app():
    # Inicializamos la base de datos y ejecutamos migraciones si aplica
    init_db()

    # Creamos la aplicación principal
    app = Flask(__name__)

    # Le pegamos la "etiqueta" (Blueprint) que contiene todas tus rutas de webhooks
    app.register_blueprint(webhooks_bp)

    @app.before_request
    def log_request_info():
        from flask import request
        print(f"🌍 [INCOMING REQUEST] {request.method} {request.url}", flush=True)

    return app