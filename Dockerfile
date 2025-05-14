# Usa una imagen base oficial de Python
FROM python:3.10-slim

# Establece variables de entorno para Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Asegúrate de que Django use la configuración correcta
ENV DJANGO_SETTINGS_MODULE=reportes_glpi.settings

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instala dependencias del sistema necesarias para algunos paquetes de Python
# (ej. matplotlib, pandas, bcrypt pueden necesitar herramientas de compilación)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libfreetype6-dev \
    libpng-dev \
    libffi-dev \
    default-libmysqlclient-dev \
 && rm -rf /var/lib/apt/lists/*

# Copia el archivo de requerimientos primero para aprovechar el caché de Docker
COPY requirements.txt /app/
# Instala las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el proyecto al directorio de trabajo en el contenedor
COPY . /app/

# Ejecuta collectstatic para recopilar archivos estáticos
# (Asegúrate de que STATIC_ROOT esté configurado en settings.py)
RUN python manage.py collectstatic --noinput

# Aplica las migraciones de la base de datos (para la base de datos SQLite por defecto, si se usa)
RUN python manage.py migrate --noinput

# Expone el puerto en el que Gunicorn se ejecutará
EXPOSE 8000

# Comando para ejecutar la aplicación usando Gunicorn
# 'reportes_glpi.wsgi:application' debe coincidir con el nombre de tu proyecto y el archivo wsgi
CMD ["gunicorn", "reportes_glpi.wsgi:application", "--bind", "0.0.0.0:8000"]
