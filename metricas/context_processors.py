import mysql.connector
from django.conf import settings
import logging

logger = logging.getLogger('metricas')

def user_initial(request):
    if request.user.is_authenticated:
        try:
            conn = mysql.connector.connect(
                user=settings.DATABASES['glpi']['USER'],
                password=settings.DATABASES['glpi']['PASSWORD'],
                host=settings.DATABASES['glpi']['HOST'],
                database=settings.DATABASES['glpi']['NAME'],
                port=int(settings.DATABASES['glpi']['PORT'])
            )
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT gu.name, gu.realname, gu.firstname FROM glpi_users gu WHERE gu.name = %s",
                (request.user.username,)
            )
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()

            if user_data:
                user_initial = user_data['realname'][0].upper() if user_data.get('realname') else user_data['name'][0].upper()
                return {
                    'user_initial': user_initial,
                    'user_realname': user_data.get('realname', ''),
                    'user_firstname': user_data.get('firstname', '')  # Agregar firstname
                }
        except Exception as e:
            logger.error(f"Error getting user data: {str(e)}")
    return {'user_initial': '', 'user_realname': '', 'user_firstname': ''}  # Valores predeterminados