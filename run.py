from app import create_app

# Llamamos a la fábrica de aplicaciones que hicimos en el __init__.py
app = create_app()

if __name__ == '__main__':
    # Encendemos el servidor en el puerto 5001 para recibir a Tailscale/Cloudflare
    app.run(host='0.0.0.0', port=5001, debug=True)