# /home/oleon/Escritorio/reportes_glpi_django/metricas/auth_backend.py

import bcrypt
import mysql.connector
import logging
from django.conf import settings
# Asegúrate de importar Group y make_password
from django.contrib.auth.models import User, Group
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import make_password

# Configurar logging
logger = logging.getLogger(__name__)

# --- Constantes Configurables ---
# Este es el ID de perfil que tu consulta requiere
REQUIRED_GLPI_PROFILE_ID = 11
# Nombre del grupo en Django que deben tener los usuarios para acceder (verifica en views.py)
REQUIRED_DJANGO_GROUP_NAME = 'Perfil Requerido'
# Lista de usuarios especiales que no necesitan el perfil 11
SPECIAL_USERNAMES = ['28492679'] # Añade más si es necesario
# ---------------------------------

class GLPIAuthBackend(BaseBackend):
    """
    Backend de autenticación personalizado contra la base de datos GLPI.
    Verifica la contraseña usando bcrypt.
    Asegura que el usuario tenga el perfil requerido en GLPI (ID 11),
    a menos que sea un usuario especial.
    Crea/actualiza el usuario de Django si la autenticación GLPI es exitosa.
    """

    def _get_glpi_connection(self):
        """Método auxiliar para obtener la conexión a la BD de GLPI."""
        try:
            conn = mysql.connector.connect(
                user=settings.DATABASES['glpi']['USER'],
                password=settings.DATABASES['glpi']['PASSWORD'],
                host=settings.DATABASES['glpi']['HOST'],
                database=settings.DATABASES['glpi']['NAME'],
                port=int(settings.DATABASES['glpi']['PORT']),
                connection_timeout=10
            )
            return conn
        except mysql.connector.Error as e:
            logger.error(f"Error de conexión MySQL: {str(e)}")
            return None
        except Exception as e:
             logger.error(f"Error inesperado al conectar a GLPI: {str(e)}")
             return None

    def authenticate(self, request, username=None, password=None):
        if not username or not password:
            logger.warning("Intento de autenticación con usuario o contraseña faltante")
            return None

        conn = self._get_glpi_connection()
        if not conn:
            return None # Falló la conexión

        user_data = None

        try:
            with conn.cursor(dictionary=True) as cursor:
                # --- Consulta Optimizada ---
                # Esta consulta busca al usuario por nombre y verifica si *al menos uno*
                # de sus perfiles coincide con REQUIRED_GLPI_PROFILE_ID (11).
                # Es más eficiente que hacer JOIN y luego filtrar en Python.
                query = """
                    SELECT
                        gu.id AS glpi_id, gu.name, gu.password, gu.firstname, gu.realname,
                        MAX(CASE WHEN gp.id = %s THEN 1 ELSE 0 END) AS has_required_profile
                    FROM glpi_users gu
                    LEFT JOIN glpi_profiles_users gpu ON gu.id = gpu.users_id
                    LEFT JOIN glpi_profiles gp ON gpu.profiles_id = gp.id
                    WHERE gu.name = %s
                    GROUP BY gu.id, gu.name, gu.password, gu.firstname, gu.realname
                """
                cursor.execute(query, (REQUIRED_GLPI_PROFILE_ID, username))
                user_data = cursor.fetchone()
                # ---------------------------

        except mysql.connector.Error as e:
            logger.error(f"Error MySQL durante consulta de autenticación para {username}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado durante consulta GLPI para {username}: {str(e)}")
            return None
        finally:
            if conn and conn.is_connected():
                conn.close()

        if not user_data:
            logger.warning(f"Usuario {username} no encontrado en la base de datos GLPI.")
            return None

        # --- Verificación de Perfil (basado en tu consulta) ---
        # Comprueba si el usuario tiene el perfil 11, a menos que sea un usuario especial.
        is_special_user = username in SPECIAL_USERNAMES
        has_required_profile = user_data.get('has_required_profile') == 1

        if not has_required_profile and not is_special_user:
             logger.warning(f"Usuario {username} no tiene el perfil GLPI requerido ID {REQUIRED_GLPI_PROFILE_ID} y no es usuario especial.")
             return None # Acceso denegado si no tiene el perfil y no es especial
        # ------------------------------------------------------

        # --- Verificación de Contraseña ---
        stored_hash = user_data.get('password')
        if not stored_hash:
             logger.error(f"No se encontró hash de contraseña para el usuario {username} en GLPI.")
             return None

        try:
            # Usa bcrypt para comparar la contraseña ingresada con el hash de GLPI
            password_valid = bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
        except ValueError as e:
             logger.error(f"Error al comparar hash para {username}. ¿Hash inválido en BD GLPI? Error: {e}")
             return None
        except Exception as e:
             logger.error(f"Error inesperado al verificar contraseña para {username}: {e}")
             return None
        # ---------------------------------

        if password_valid:
            logger.info(f"Credenciales GLPI válidas para usuario {username}.")
            # --- ¡Clave del Éxito! Manejo del Usuario en Django ---
            # Si la contraseña y el perfil (si aplica) son correctos en GLPI,
            # ahora buscamos o creamos el usuario en Django.
            try:
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'password': make_password(None), # Contraseña no usable en Django
                        'first_name': user_data.get('firstname', ''),
                        'last_name': user_data.get('realname', ''),
                        'email': user_data.get('email', ''),
                        'is_staff': False,
                        'is_active': True,
                        'is_superuser': False,
                    }
                )

                if created:
                    logger.info(f"Usuario Django creado para {username}.")
                # else: # Opcional: Actualizar datos si ya existía
                #     # ... (código de actualización omitido por brevedad) ...

                # --- Asegurar Pertenencia al Grupo Django ---
                # Añade al usuario al grupo requerido en Django para que pase
                # la verificación en login_view.
                try:
                    required_group = Group.objects.get(name=REQUIRED_DJANGO_GROUP_NAME)
                    user.groups.add(required_group)
                    logger.info(f"Usuario {username} añadido/asegurado en grupo Django '{REQUIRED_DJANGO_GROUP_NAME}'.")
                except Group.DoesNotExist:
                    logger.error(f"¡Error Crítico! El grupo Django '{REQUIRED_DJANGO_GROUP_NAME}' no existe. Créalo en el admin.")
                    # Considera si devolver None aquí para evitar accesos sin grupo
                    # return None
                except Exception as e:
                    logger.error(f"Error al añadir usuario {username} al grupo Django: {e}")
                    # return None # Podrías denegar el acceso si falla la asignación de grupo

                return user # ¡Autenticación completa y exitosa!

            except Exception as e:
                logger.error(f"Error inesperado durante manejo de usuario Django para {username}: {str(e)}")
                return None
            # ----------------------------------------------------
        else:
            logger.warning(f"Contraseña inválida para usuario: {username}")
            return None # Contraseña incorrecta

    def get_user(self, user_id):
        # Método estándar requerido por Django
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            logger.warning(f"get_user: Usuario Django con ID {user_id} no encontrado.")
            return None
        except Exception as e:
            logger.error(f"Error inesperado en get_user para ID {user_id}: {e}")
            return None

