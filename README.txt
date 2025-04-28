# Proyecto: Reporte GLPI Django

Este proyecto es una aplicación web desarrollada en Django para la generación de reportes de métricas de técnicos utilizando datos almacenados en una base de datos GLPI.

## Requisitos del Sistema

- Python 3.8 o superior
- Django 5.2
- MySQL Server
- Paquetes adicionales especificados en `requirements.txt`

## Instalación

1. Clona este repositorio en tu máquina local:
   ```
   git clone <URL_DEL_REPOSITORIO>
   cd reporte_glpi_django
   ```

2. Crea y activa un entorno virtual:
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Instala las dependencias:
   ```
   pip install -r requirements.txt
   ```

4. Configura la base de datos:
   - Asegúrate de que las credenciales de la base de datos GLPI estén correctamente configuradas en `reportes_glpi/settings.py` bajo la clave `DATABASES['glpi']`.

5. Realiza las migraciones de la base de datos:
   ```
   python manage.py migrate
   ```

6. Inicia el servidor de desarrollo:
   ```
   python manage.py runserver
   ```

7. Accede a la aplicación en tu navegador en `http://127.0.0.1:8000`.

## Funcionalidades Principales

- **Autenticación**: Los usuarios se autentican utilizando las credenciales almacenadas en la base de datos GLPI.
- **Generación de Reportes**: Permite generar reportes de métricas de técnicos, incluyendo tickets cerrados, pendientes y reabiertos.
- **Exportación de Datos**: Los reportes pueden exportarse en formatos como Excel, PDF y CSV.
- **Gestión de Técnicos**: Selección de técnicos por grupo o subgrupo.

## Estructura del Proyecto

- `metricas/`: Contiene la lógica principal de la aplicación, incluyendo modelos, vistas, servicios y plantillas.
- `reportes_glpi/`: Configuración del proyecto Django.
- `requirements.txt`: Lista de dependencias del proyecto.
- `db.sqlite3`: Base de datos SQLite utilizada para desarrollo.

## Archivos Clave

- `metricas/views.py`: Contiene las vistas principales para la generación de reportes y manejo de usuarios.
- `metricas/services.py`: Lógica para la conexión a la base de datos GLPI y generación de reportes.
- `metricas/auth_backend.py`: Backend de autenticación personalizado para integrar GLPI con Django.
- `metricas/templates/`: Plantillas HTML para la interfaz de usuario.

## Notas de Desarrollo

- **Configuración de Seguridad**: Asegúrate de cambiar la clave secreta (`SECRET_KEY`) en `settings.py` antes de desplegar en producción.
- **Depuración**: Los logs de depuración se almacenan en el archivo `debug.log` en el directorio raíz del proyecto.
- **CSRF**: Configura los dominios de confianza en `CSRF_TRUSTED_ORIGINS` en `settings.py` si accedes desde un dominio diferente.