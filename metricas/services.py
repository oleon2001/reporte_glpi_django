import mysql.connector
import pandas as pd
from django.conf import settings
from datetime import datetime, date
import calendar
import logging # Añadir logging

class DatabaseConnector:
    @staticmethod
    def get_connection():
        return mysql.connector.connect(
            user=settings.DATABASES['glpi']['USER'],
            password=settings.DATABASES['glpi']['PASSWORD'],
            host=settings.DATABASES['glpi']['HOST'],
            database=settings.DATABASES['glpi']['NAME'],
            port=int(settings.DATABASES['glpi']['PORT'])
        )

# Configurar logger para services
logger = logging.getLogger(__name__)

class ReportGenerator:
    @staticmethod
    def obtener_tecnicos():
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor()
        query = """
            SELECT DISTINCT CONCAT(gu.realname, ' ', gu.firstname) 
            FROM glpi_users gu
            JOIN glpi_profiles_users gpu ON gu.id = gpu.users_id
            JOIN glpi_profiles gp ON gpu.profiles_id = gp.id
            WHERE gp.id = 10
            ORDER BY gu.realname, gu.firstname
        """
        cursor.execute(query)
        tecnicos = [r[0] for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        return tecnicos

    @staticmethod
    def generar_reporte_principal(fecha_ini=None, fecha_fin=None, tecnicos=None):
        # Si no se proporcionan fechas, usar el mes en curso
        if fecha_ini is None:
            # Primer día del mes actual
            today = date.today()
            fecha_ini = date(today.year, today.month, 1).strftime('%Y-%m-%d')
        
        if fecha_fin is None:
            # Último día del mes actual
            today = date.today()
            _, last_day = calendar.monthrange(today.year, today.month)
            fecha_fin = date(today.year, today.month, last_day).strftime('%Y-%m-%d')
        
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor()

        # Construcción segura de la condición de técnicos
        tecnicos_condicion = ""
        params_tecnicos = []
        if tecnicos:
            placeholders = ', '.join(['%s'] * len(tecnicos))
            tecnicos_condicion = f"AND CONCAT(gu.realname, ' ', gu.firstname) IN ({placeholders})"
            params_tecnicos = tecnicos.copy()

        # Contar correctamente las subconsultas que usan la condición (5 veces)
        num_condiciones = 5  # ¡Corregido de 6 a 5!
        params_tecnicos_repetidos = params_tecnicos * num_condiciones

        query = f"""
            SELECT
                recibidos.tecnico_asignado,
                COALESCE(cerrados_sla.Cant_tickets_cerrados_dentro_SLA, 0) AS Cant_tickets_cerrados_dentro_SLA,
                COALESCE(cerrados_sla.Cant_tickets_cerrados_con_SLA, 0) AS Cant_tickets_cerrados_con_SLA,
                COALESCE(pendientes_sla.T_pendiente_sla_vencido, 0) AS tickets_pendientes_SLA,
                ROUND(
                    (COALESCE(cerrados_sla.Cant_tickets_cerrados_dentro_SLA, 0) / 
                    (COALESCE(cerrados_sla.Cant_tickets_cerrados_con_SLA, 0) + COALESCE(pendientes_sla.T_pendiente_sla_vencido, 0))) * 100, 
                    2
                ) AS `Cumplimiento SLA`,
                COALESCE(cerrados_count.total_tickets_cerrados, 0) AS Cant_tickets_cerrados,
                COALESCE(recibidos.total_tickets_del_mes, 0) AS Cant_tickets_recibidos,
                COALESCE(reabiertos.cuenta_de_tickets_reabiertos, 0) AS cuenta_de_tickets_reabiertos,
                CASE
                    WHEN COALESCE(reabiertos.cuenta_de_tickets_reabiertos, 0) = 0 THEN '0'
                    ELSE ROUND(
                        (COALESCE(reabiertos.cuenta_de_tickets_reabiertos, 0) / COALESCE(cerrados_count.total_tickets_cerrados, 1)) * 100, 
                        2
                    )
                END AS `Proporción Reabiertos/Cerrados (%)`
            FROM (
                SELECT
                    CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
                    COUNT(DISTINCT gt.id) AS total_tickets_del_mes
                FROM
                    glpi_tickets gt
                JOIN glpi_entities ge ON gt.entities_id = ge.id
                JOIN glpi_tickets_users t_users_tec ON gt.id = t_users_tec.tickets_id AND t_users_tec.type = 2
                JOIN glpi_users gu ON t_users_tec.users_id = gu.id
                JOIN glpi_profiles_users gpu ON gu.id = gpu.users_id
                JOIN glpi_profiles gp ON gpu.profiles_id = gp.id
                WHERE
                    gt.is_deleted = 0
                    AND ge.completename IS NOT NULL
                    AND LOCATE('@', ge.completename) = 0
                    AND LOCATE('CASOS DUPLICADOS', UPPER(ge.completename)) = 0 
                    AND gt.date BETWEEN CONVERT_TZ(%s, 'America/Caracas', 'UTC')
                                    AND CONVERT_TZ(%s, 'America/Caracas', 'UTC')
                    {tecnicos_condicion}
                GROUP BY tecnico_asignado
            ) AS recibidos
            LEFT JOIN (
                SELECT
                    CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
                    COUNT(DISTINCT gt.id) AS total_tickets_cerrados
                FROM
                    glpi_tickets gt
                JOIN glpi_entities ge ON gt.entities_id = ge.id
                JOIN glpi_tickets_users t_users_tec ON gt.id = t_users_tec.tickets_id AND t_users_tec.type = 2
                JOIN glpi_users gu ON t_users_tec.users_id = gu.id
                WHERE
                    gt.is_deleted = 0
                    AND gt.status > 4
                    AND gt.solvedate BETWEEN CONVERT_TZ(%s, 'America/Caracas', 'UTC')
                                        AND CONVERT_TZ(%s, 'America/Caracas', 'UTC')
                    AND gt.date BETWEEN CONVERT_TZ(%s, 'America/Caracas', 'UTC') - INTERVAL 90 DAY
                                    AND CONVERT_TZ(%s, 'America/Caracas', 'UTC')
                    {tecnicos_condicion}
                GROUP BY tecnico_asignado
            ) AS cerrados_count ON recibidos.tecnico_asignado = cerrados_count.tecnico_asignado
            LEFT JOIN (
                SELECT
                    CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
                    SUM(CASE WHEN gt.solvedate <= gt.time_to_resolve THEN 1 ELSE 0 END) AS Cant_tickets_cerrados_dentro_SLA,
                    COUNT(DISTINCT gt.id) AS Cant_tickets_cerrados_con_SLA
                FROM
                    glpi_tickets gt
                JOIN glpi_entities ge ON gt.entities_id = ge.id
                JOIN glpi_tickets_users t_users_tec ON gt.id = t_users_tec.tickets_id AND t_users_tec.type = 2
                JOIN glpi_users gu ON t_users_tec.users_id = gu.id
                WHERE
                    gt.is_deleted = 0
                    AND gt.status > 4
                    AND gt.solvedate BETWEEN CONVERT_TZ(%s, 'America/Caracas', 'UTC')
                                        AND CONVERT_TZ(%s, 'America/Caracas', 'UTC')
                    AND gt.date BETWEEN CONVERT_TZ(%s, 'America/Caracas', 'UTC') - INTERVAL 90 DAY
                                AND CONVERT_TZ(%s, 'America/Caracas', 'UTC')
                    {tecnicos_condicion}
                GROUP BY tecnico_asignado
            ) AS cerrados_sla ON recibidos.tecnico_asignado = cerrados_sla.tecnico_asignado
            LEFT JOIN (
                SELECT
                    CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
                    COUNT(DISTINCT gi.items_id) AS cuenta_de_tickets_reabiertos
                FROM
                    glpi_itilsolutions gi
                INNER JOIN glpi_tickets gt ON gi.items_id = gt.id
                INNER JOIN glpi_users gu ON gi.users_id = gu.id
                WHERE
                    gi.status = 4
                    AND gi.users_id_approval > 0
                    AND CONVERT_TZ(gi.date_approval, 'UTC', 'America/Caracas') BETWEEN %s AND %s
                    {tecnicos_condicion}
                GROUP BY tecnico_asignado
            ) AS reabiertos ON recibidos.tecnico_asignado = reabiertos.tecnico_asignado
            LEFT JOIN (
                SELECT
                    CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
                    SUM(
                        (
                            (YEAR(CASE WHEN gt.solvedate IS NULL THEN DATE(%s) + INTERVAL 1 DAY ELSE gt.solvedate END) - YEAR(gt.`date`)) * 12
                        ) + 
                        (
                            MONTH(CASE WHEN gt.solvedate IS NULL THEN DATE(%s) + INTERVAL 1 DAY ELSE gt.solvedate END) - MONTH(gt.`date`)
                        )
                    ) AS T_pendiente_sla_vencido
                FROM
                    glpi_tickets gt
                JOIN glpi_entities ge ON gt.entities_id = ge.id
                JOIN glpi_tickets_users t_users_tec ON gt.id = t_users_tec.tickets_id AND t_users_tec.type = 2
                JOIN glpi_users gu ON t_users_tec.users_id = gu.id
                WHERE
                    gt.is_deleted = 0
                    AND gt.date BETWEEN CONVERT_TZ(%s, 'America/Caracas', 'UTC')
                                    AND CONVERT_TZ(%s, 'America/Caracas', 'UTC')
                    AND (
                        (gt.solvedate > gt.time_to_resolve
                        AND MONTH(gt.time_to_resolve) = MONTH(gt.date)
                        AND MONTH(gt.solvedate) != MONTH(gt.date))
                        OR gt.solvedate IS NULL
                    )
                    {tecnicos_condicion}
                GROUP BY tecnico_asignado
            ) AS pendientes_sla ON recibidos.tecnico_asignado = pendientes_sla.tecnico_asignado
            ORDER BY recibidos.tecnico_asignado;
        """

        # Parámetros en el orden CORRECTO (técnicos intercalados)
        params = [
            # Primer bloque (recibidos)
            f'{fecha_ini} 00:00:00', f'{fecha_fin} 23:59:59',
            *params_tecnicos,
            
            # Segundo bloque (cerrados_count)
            f'{fecha_ini} 00:00:00', f'{fecha_fin} 23:59:59',
            f'{fecha_ini} 00:00:00', f'{fecha_fin} 23:59:59',
            *params_tecnicos,
            
            # Tercer bloque (cerrados_sla)
            f'{fecha_ini} 00:00:00', f'{fecha_fin} 23:59:59',
            f'{fecha_ini} 00:00:00', f'{fecha_fin} 23:59:59',
            *params_tecnicos,
            
            # Cuarto bloque (reabiertos)
            f'{fecha_ini} 00:00:00', f'{fecha_fin} 23:59:59',
            *params_tecnicos,
            
            # Quinto bloque (pendientes_sla)
            fecha_fin, fecha_fin,
            f'{fecha_ini} 00:00:00', f'{fecha_fin} 23:59:59',
            *params_tecnicos,
        ]
        
        #params = params_tecnicos_repetidos + params_fechas
        
        cursor.execute(query, params)
        resultados = cursor.fetchall()
        
        df = pd.DataFrame(resultados, columns=[
            "Tecnico_Asignado", "Cerrados_dentro_SLA", "Cerrados_con_SLA",
            "tickets_pendientes_SLA", "Cumplimiento SLA", "Cant_tickets_cerrados",
            "Cant_tickets_recibidos", "Reabiertos", "Proporción Reabiertos/Cerrados (%)"
        ])

        cursor.close()
        conn.close()
        return df.to_dict(orient='records')

    @staticmethod
    def obtener_tickets_reabiertos(tecnico, fecha_ini=None, fecha_fin=None):
        # Si no se proporcionan fechas, usar el mes en curso
        if fecha_ini is None:
            # Primer día del mes actual
            today = date.today()
            fecha_ini = date(today.year, today.month, 1).strftime('%Y-%m-%d')
        
        if fecha_fin is None:
            # Último día del mes actual
            today = date.today()
            _, last_day = calendar.monthrange(today.year, today.month)
            fecha_fin = date(today.year, today.month, last_day).strftime('%Y-%m-%d')
            
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor()

        query = """
            SELECT gi.items_id AS Nro_Ticket,
                MAX(DATE_FORMAT(gi.date_approval, GET_FORMAT(DATE,'ISO'))) AS Fecha_Reapertura,
                MAX(DATE_FORMAT(gt.date_creation, GET_FORMAT(DATE,'ISO'))) AS Fecha_Apertura,
                CONCAT(gu.realname, " ", gu.firstname) AS Tecnico_Asignado
            FROM glpi_itilsolutions gi
            INNER JOIN glpi_tickets gt ON gt.id = gi.items_id
            INNER JOIN glpi_users gu ON gu.id = gi.users_id
            WHERE gi.status = 4 
                AND gi.users_id_approval > 0 
                AND CONVERT_TZ(gi.date_approval,'UTC', 'America/Caracas') BETWEEN %s AND %s
                AND CONCAT(gu.realname, ' ', gu.firstname) = %s
            GROUP BY Nro_Ticket;
        """

        params = (
            f'{fecha_ini} 00:00:00', 
            f'{fecha_fin} 23:59:59', 
            tecnico
        )

        cursor.execute(query, params)
        resultados = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return [dict(zip(['Nro_Ticket', 'Fecha_Reapertura', 'Fecha_Apertura', 'Tecnico_Asignado'], row)) for row in resultados]

    @staticmethod
    def obtener_datos_tendencia_tecnico(tecnico, fecha_ini, fecha_fin):
        """
        Obtiene datos diarios de tickets recibidos, cerrados, cerrados dentro de SLA
        y cerrados con SLA para un técnico específico dentro de un rango de fechas.
        """
        conn = None
        cursor = None
        timezone = 'America/Caracas' # O la timezone configurada

        try:
            conn = DatabaseConnector.get_connection()
            cursor = conn.cursor(dictionary=True) # Usar dictionary=True para facilitar el manejo

            # Convertir fechas a formato datetime para la consulta
            fecha_ini_dt = f'{fecha_ini} 00:00:00'
            fecha_fin_dt = f'{fecha_fin} 23:59:59'

            # Query para tickets recibidos por día
            query_recibidos = f"""
                SELECT
                    DATE(CONVERT_TZ(gt.date, 'UTC', %s)) AS dia,
                    COUNT(DISTINCT gt.id) AS recibidos
                FROM glpi_tickets gt
                JOIN glpi_tickets_users gtu ON gt.id = gtu.tickets_id AND gtu.type = 2 -- Asignado
                JOIN glpi_users gu ON gtu.users_id = gu.id
                WHERE
                    gt.is_deleted = 0
                    AND CONCAT(gu.realname, ' ', gu.firstname) = %s
                    AND gt.date BETWEEN CONVERT_TZ(%s, %s, 'UTC') AND CONVERT_TZ(%s, %s, 'UTC')
                GROUP BY dia
                ORDER BY dia;
            """
            params_recibidos = (timezone, tecnico, fecha_ini_dt, timezone, fecha_fin_dt, timezone)
            cursor.execute(query_recibidos, params_recibidos)
            recibidos_data = cursor.fetchall()

            # Query para tickets cerrados por día
            query_cerrados = f"""
                SELECT
                    DATE(CONVERT_TZ(gt.solvedate, 'UTC', %s)) AS dia,
                    COUNT(DISTINCT gt.id) AS cerrados
                FROM glpi_tickets gt
                JOIN glpi_tickets_users gtu ON gt.id = gtu.tickets_id AND gtu.type = 2 -- Asignado
                JOIN glpi_users gu ON gtu.users_id = gu.id
                WHERE
                    gt.is_deleted = 0
                    AND gt.status > 4 
                    AND CONCAT(gu.realname, ' ', gu.firstname) = %s
                    AND gt.solvedate BETWEEN CONVERT_TZ(%s, %s, 'UTC') AND CONVERT_TZ(%s, %s, 'UTC')
                GROUP BY dia
                ORDER BY dia;
            """
            params_cerrados = (timezone, tecnico, fecha_ini_dt, timezone, fecha_fin_dt, timezone)
            cursor.execute(query_cerrados, params_cerrados)
            cerrados_data = cursor.fetchall()

            # Query para datos de SLA por día de cierre
            query_sla = f"""
                SELECT
                    DATE(CONVERT_TZ(gt.solvedate, 'UTC', %s)) AS dia,
                    SUM(CASE WHEN gt.solvedate <= gt.time_to_resolve THEN 1 ELSE 0 END) AS cerrados_dentro_sla,
                    COUNT(DISTINCT gt.id) AS cerrados_con_sla -- Cuenta tickets cerrados que tenían un SLA
                FROM glpi_tickets gt
                JOIN glpi_tickets_users gtu ON gt.id = gtu.tickets_id AND gtu.type = 2 -- Asignado
                JOIN glpi_users gu ON gtu.users_id = gu.id
                WHERE
                    gt.is_deleted = 0
                    AND gt.status > 4
                    AND gt.time_to_resolve IS NOT NULL -- Asegura que el ticket tenía un SLA definido
                    AND CONCAT(gu.realname, ' ', gu.firstname) = %s
                    AND gt.solvedate BETWEEN CONVERT_TZ(%s, %s, 'UTC') AND CONVERT_TZ(%s, %s, 'UTC')
                GROUP BY dia
                ORDER BY dia;
            """
            params_sla = (timezone, tecnico, fecha_ini_dt, timezone, fecha_fin_dt, timezone)
            cursor.execute(query_sla, params_sla)
            sla_data = cursor.fetchall()

            # Combinar los datos usando Pandas para facilidad
            df_recibidos = pd.DataFrame(recibidos_data)
            df_cerrados = pd.DataFrame(cerrados_data)
            df_sla = pd.DataFrame(sla_data)

            # Asegurarse de que la columna 'dia' sea datetime
            if not df_recibidos.empty:
                df_recibidos['dia'] = pd.to_datetime(df_recibidos['dia'])
            if not df_cerrados.empty:
                df_cerrados['dia'] = pd.to_datetime(df_cerrados['dia'])
            if not df_sla.empty:
                df_sla['dia'] = pd.to_datetime(df_sla['dia'])

            # Crear un DataFrame base con todas las fechas del rango para asegurar continuidad
            date_range = pd.date_range(start=fecha_ini, end=fecha_fin, freq='D')
            df_base = pd.DataFrame({'dia': date_range})

            # Fusionar los dataframes con el base usando outer merge
            df_merged = df_base
            if not df_recibidos.empty: df_merged = pd.merge(df_merged, df_recibidos, on='dia', how='left')
            if not df_cerrados.empty: df_merged = pd.merge(df_merged, df_cerrados, on='dia', how='left')
            if not df_sla.empty: df_merged = pd.merge(df_merged, df_sla, on='dia', how='left')
            else:
                # Si todos están vacíos, df_merged será solo el df_base con fechas
                df_merged['recibidos'] = 0
                df_merged['cerrados'] = 0
                df_merged['cerrados_dentro_sla'] = 0
                df_merged['cerrados_con_sla'] = 0

            df_merged = df_merged.fillna(0).sort_values(by='dia')
            # Convertir columnas numéricas a enteros
            df_merged['recibidos'] = df_merged['recibidos'].astype(int)
            df_merged['cerrados'] = df_merged['cerrados'].astype(int)
            df_merged['cerrados_dentro_sla'] = df_merged['cerrados_dentro_sla'].astype(int)
            df_merged['cerrados_con_sla'] = df_merged['cerrados_con_sla'].astype(int)

            return df_merged # Devolver el DataFrame combinado

        except mysql.connector.Error as err:
            logger.error(f"Error de base de datos al obtener datos de tendencia para {tecnico}: {err}")
            raise # Re-lanzar la excepción para que la vista la maneje
        except Exception as e:
            logger.error(f"Error inesperado al obtener datos de tendencia para {tecnico}: {e}", exc_info=True)
            raise
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()