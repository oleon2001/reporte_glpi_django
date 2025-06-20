#!/bin/bash

# Configuración del servidor remoto
REMOTE_HOST="10.48.63.60"
REMOTE_USER="cpgadmin"
REMOTE_PASS="Cpgretail01"
PROJECT_NAME="reporte_glpi_django"
REMOTE_PATH="/home/cpgadmin/$PROJECT_NAME"

echo "=== Iniciando despliegue del proyecto $PROJECT_NAME ==="

# 1. Crear un archivo tar con el proyecto (excluyendo archivos innecesarios)
echo "1. Empaquetando proyecto..."
tar --exclude='venv' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='debug.log' \
    --exclude='db.sqlite3' \
    -czf ${PROJECT_NAME}.tar.gz .

echo "Proyecto empaquetado en ${PROJECT_NAME}.tar.gz"

# 2. Copiar el archivo al servidor remoto usando sshpass
echo "2. Copiando proyecto al servidor remoto..."
sshpass -p "$REMOTE_PASS" scp ${PROJECT_NAME}.tar.gz ${REMOTE_USER}@${REMOTE_HOST}:~/ 

# 3. Conectarse al servidor remoto y ejecutar los comandos de despliegue
echo "3. Conectando al servidor remoto y desplegando..."
sshpass -p "$REMOTE_PASS" ssh ${REMOTE_USER}@${REMOTE_HOST} << 'EOF'
    # Detener contenedor existente si existe
    docker stop reporte_glpi_django 2>/dev/null || true
    docker rm reporte_glpi_django 2>/dev/null || true
    
    # Limpiar directorio anterior si existe
    rm -rf ~/reporte_glpi_django
    
    # Extraer el proyecto
    tar -xzf ~/reporte_glpi_django.tar.gz -C ~/ --one-top-level=reporte_glpi_django
    
    # Ir al directorio del proyecto
    cd ~/reporte_glpi_django
    
    # Construir la imagen Docker
    docker build -t reporte_glpi_django .
    
    # Ejecutar el contenedor
    docker run -d \
        --name reporte_glpi_django \
        -p 8000:8000 \
        --restart unless-stopped \
        reporte_glpi_django
    
    # Mostrar estado del contenedor
    docker ps | grep reporte_glpi_django
    
    echo "=== Despliegue completado ==="
    echo "La aplicación debería estar disponible en: http://10.48.63.60:8000"
EOF

# 4. Limpiar archivo temporal local
rm ${PROJECT_NAME}.tar.gz

echo "=== Proceso de despliegue finalizado ==="
echo "Puedes acceder a tu aplicación en: http://10.48.63.60:8000"