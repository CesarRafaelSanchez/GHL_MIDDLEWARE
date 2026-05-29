FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar requerimientos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer el puerto en el que corre run.py (5001)
EXPOSE 5001

# Ejecutar con Gunicorn para producción (evita usar el servidor de desarrollo de Flask)
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "run.py:app"]