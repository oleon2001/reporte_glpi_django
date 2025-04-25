import mysql.connector
from django.conf import settings
import logging

logger = logging.getLogger('metricas')

def user_initial(request):
    """
    Context processor to add the user's initial to the template context.
    """
    if request.user.is_authenticated:
        logger.info(f"Processing user_initial for user: {request.user.username}")
        try:
            # Connect to the GLPI database
            conn = mysql.connector.connect(
                user=settings.DATABASES['glpi']['USER'],
                password=settings.DATABASES['glpi']['PASSWORD'],
                host=settings.DATABASES['glpi']['HOST'],
                database=settings.DATABASES['glpi']['NAME'],
                port=int(settings.DATABASES['glpi']['PORT'])
            )
            
            cursor = conn.cursor(dictionary=True)
            
            # Query the GLPI users table to get the user's name
            cursor.execute(
                "SELECT gu.name, gu.realname, gu.firstname FROM glpi_users gu WHERE gu.name = %s",
                (request.user.username,)
            )
            
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user_data:
                logger.info(f"Found user data: {user_data}")
                # Intentar usar realname primero, luego name si realname no está disponible
                if user_data.get('realname'):
                    user_initial = user_data['realname'][0].upper()
                else:
                    user_initial = user_data['name'][0].upper()
                logger.info(f"Generated initial: {user_initial}")
                return {'user_initial': user_initial}
            else:
                logger.warning(f"No user data found for username: {request.user.username}")
            
        except Exception as e:
            logger.error(f"Error getting user initial: {str(e)}")
    else:
        logger.info("User not authenticated")
    
    # Default to empty if not authenticated or error occurred
    return {'user_initial': ''} 