import mysql.connector
import pandas as pd
from django.conf import settings
from datetime import datetime, date
import calendar
import logging # Añadir logging
import json # Para trabajar con datos JSON (en requests/responses)
import logging # Para registrar eventos y errores
import mysql.connector # Para conexiones a base de datos MySQL
from django.conf import settings # Para acceder a la configuración de Django
import pandas as pd # Para procesamiento eficiente de datos
from datetime import date, datetime, timedelta # Para manejo de fechas
import calendar # Para cálculos de meses
from concurrent.futures import ThreadPoolExecutor, as_completed # Para procesamiento paralelo
import hashlib # Para generar claves de cache
from django.core.cache import cache # Para sistema de cache de Django
from typing import List, Dict, Optional, Tuple # Para type hints
import time # Para medición de tiempos

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
    # Cache keys
    CACHE_TIMEOUT = 3600  # 1 hour cache
    CACHE_PREFIX = "report_generator"
    
    # Configuración de optimización
    MAX_QUERY_TIMEOUT = 30  # 30 segundos máximo por consulta
    CHUNK_SIZE_DAYS = 90    # Procesar en chunks de 3 meses máximo
    MAX_RECORDS_PER_QUERY = 10000  # Límite de registros por consulta

    @staticmethod
    def _generate_cache_key(fecha_ini: str, fecha_fin: str, tecnicos: Optional[List[str]] = None) -> str:
        """Genera clave de cache única para los parámetros dados"""
        tecnicos_str = ','.join(sorted(tecnicos)) if tecnicos else 'all'
        return f"{ReportGenerator.CACHE_PREFIX}:{fecha_ini}:{fecha_fin}:{hash(tecnicos_str)}"

    @staticmethod
    def _get_date_chunks(fecha_ini: str, fecha_fin: str, chunk_days: int = 90) -> List[Tuple[str, str]]:
        """Divide el rango de fechas en chunks más pequeños para optimizar consultas"""
        start_date = datetime.strptime(fecha_ini, '%Y-%m-%d').date()
        end_date = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        
        # Si el rango es menor a chunk_days, devolver como un solo chunk
        if (end_date - start_date).days <= chunk_days:
            return [(fecha_ini, fecha_fin)]
        
        chunks = []
        current_date = start_date
        
        while current_date <= end_date:
            chunk_end = min(current_date + timedelta(days=chunk_days - 1), end_date)
            chunks.append((
                current_date.strftime('%Y-%m-%d'),
                chunk_end.strftime('%Y-%m-%d')
            ))
            current_date = chunk_end + timedelta(days=1)
        
        return chunks

    @staticmethod
    def _execute_optimized_query_tickets_recibidos(fecha_ini: str, fecha_fin: str, tecnicos: Optional[List[str]] = None) -> pd.DataFrame:
        """Consulta ultra-optimizada para tickets recibidos"""
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Configurar timeout
        cursor.execute("SET SESSION innodb_lock_wait_timeout = %s", (ReportGenerator.MAX_QUERY_TIMEOUT,))
        
        tecnicos_condition = ""
        params = [fecha_ini, fecha_fin]
        
        if tecnicos:
            placeholders = ', '.join(['%s'] * len(tecnicos))
            tecnicos_condition = f"AND CONCAT(gu.realname, ' ', gu.firstname) IN ({placeholders})"
            params.extend(tecnicos)
        
        # Consulta optimizada sin conversiones de timezone innecesarias
        query = f"""
            SELECT 
                CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
                COUNT(DISTINCT gt.id) AS total_tickets_recibidos
            FROM glpi_tickets gt
            STRAIGHT_JOIN glpi_tickets_users gtu ON gt.id = gtu.tickets_id AND gtu.type = 2
            STRAIGHT_JOIN glpi_users gu ON gtu.users_id = gu.id
            STRAIGHT_JOIN glpi_entities ge ON gt.entities_id = ge.id
            WHERE gt.is_deleted = 0
                AND DATE(gt.date) BETWEEN %s AND %s
                AND ge.completename IS NOT NULL
                AND ge.completename NOT LIKE '%@%'
                AND UPPER(ge.completename) NOT LIKE '%CASOS DUPLICADOS%'
                {tecnicos_condition}
            GROUP BY gu.id, gu.realname, gu.firstname
            LIMIT {ReportGenerator.MAX_RECORDS_PER_QUERY}
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return pd.DataFrame(results)

    @staticmethod
    def _execute_optimized_query_tickets_cerrados(fecha_ini: str, fecha_fin: str, tecnicos: Optional[List[str]] = None) -> pd.DataFrame:
        """Consulta ultra-optimizada para tickets cerrados"""
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Configurar timeout
        cursor.execute("SET SESSION innodb_lock_wait_timeout = %s", (ReportGenerator.MAX_QUERY_TIMEOUT,))
        
        tecnicos_condition = ""
        params = [fecha_ini, fecha_fin]
        
        if tecnicos:
            placeholders = ', '.join(['%s'] * len(tecnicos))
            tecnicos_condition = f"AND CONCAT(gu.realname, ' ', gu.firstname) IN ({placeholders})"
            params.extend(tecnicos)
        
        query = f"""
            SELECT 
                CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
                COUNT(DISTINCT gt.id) AS total_tickets_cerrados
            FROM glpi_tickets gt
            STRAIGHT_JOIN glpi_tickets_users gtu ON gt.id = gtu.tickets_id AND gtu.type = 2
            STRAIGHT_JOIN glpi_users gu ON gtu.users_id = gu.id
            WHERE gt.is_deleted = 0
                AND gt.status > 4
                AND DATE(gt.solvedate) BETWEEN %s AND %s
                {tecnicos_condition}
            GROUP BY gu.id, gu.realname, gu.firstname
            LIMIT {ReportGenerator.MAX_RECORDS_PER_QUERY}
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return pd.DataFrame(results)

    @staticmethod
    def _execute_optimized_query_sla_metrics(fecha_ini: str, fecha_fin: str, tecnicos: Optional[List[str]] = None) -> pd.DataFrame:
        """Consulta ultra-optimizada para métricas SLA"""
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Configurar timeout
        cursor.execute("SET SESSION innodb_lock_wait_timeout = %s", (ReportGenerator.MAX_QUERY_TIMEOUT,))
        
        tecnicos_condition = ""
        params = [fecha_ini, fecha_fin]
        
        if tecnicos:
            placeholders = ', '.join(['%s'] * len(tecnicos))
            tecnicos_condition = f"AND CONCAT(gu.realname, ' ', gu.firstname) IN ({placeholders})"
            params.extend(tecnicos)
        
        query = f"""
            SELECT 
                CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
                SUM(CASE WHEN gt.solvedate <= gt.time_to_resolve THEN 1 ELSE 0 END) AS cerrados_dentro_sla,
                COUNT(DISTINCT gt.id) AS cerrados_con_sla,
                SUM(CASE 
                    WHEN gt.solvedate IS NULL OR gt.solvedate > gt.time_to_resolve THEN 1 
                    ELSE 0 
                END) AS pendientes_sla
            FROM glpi_tickets gt
            STRAIGHT_JOIN glpi_tickets_users gtu ON gt.id = gtu.tickets_id AND gtu.type = 2
            STRAIGHT_JOIN glpi_users gu ON gtu.users_id = gu.id
            WHERE gt.is_deleted = 0
                AND gt.status > 4
                AND DATE(gt.solvedate) BETWEEN %s AND %s
                AND gt.time_to_resolve IS NOT NULL
                {tecnicos_condition}
            GROUP BY gu.id, gu.realname, gu.firstname
            LIMIT {ReportGenerator.MAX_RECORDS_PER_QUERY}
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return pd.DataFrame(results)

    @staticmethod
    def _execute_optimized_query_reabiertos(fecha_ini: str, fecha_fin: str, tecnicos: Optional[List[str]] = None) -> pd.DataFrame:
        """Consulta ultra-optimizada para tickets reabiertos"""
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Configurar timeout
        cursor.execute("SET SESSION innodb_lock_wait_timeout = %s", (ReportGenerator.MAX_QUERY_TIMEOUT,))
        
        tecnicos_condition = ""
        params = [fecha_ini, fecha_fin]
        
        if tecnicos:
            placeholders = ', '.join(['%s'] * len(tecnicos))
            tecnicos_condition = f"AND CONCAT(gu.realname, ' ', gu.firstname) IN ({placeholders})"
            params.extend(tecnicos)
        
        query = f"""
            SELECT 
                CONCAT(gu.realname, ' ', gu.firstname) AS tecnico_asignado,
                COUNT(DISTINCT gi.items_id) AS tickets_reabiertos
            FROM glpi_itilsolutions gi
            STRAIGHT_JOIN glpi_users gu ON gi.users_id = gu.id
            WHERE gi.status = 4
                AND gi.users_id_approval > 0
                AND DATE(gi.date_approval) BETWEEN %s AND %s
                {tecnicos_condition}
            GROUP BY gu.id, gu.realname, gu.firstname
            LIMIT {ReportGenerator.MAX_RECORDS_PER_QUERY}
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return pd.DataFrame(results)

    @staticmethod
    def _process_chunk_parallel(chunk_dates: Tuple[str, str], tecnicos: Optional[List[str]] = None) -> Dict:
        """Procesa un chunk de fechas en paralelo con optimizaciones"""
        fecha_ini, fecha_fin = chunk_dates
        logger.info(f"🔄 Procesando chunk: {fecha_ini} a {fecha_fin}")
        
        # Configurar conexión optimizada para este chunk
        ReportGenerator._configure_database_for_chunk()
        
        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                # Ejecutar consultas en paralelo con timeouts
                futures = {
                    'recibidos': executor.submit(
                        ReportGenerator._execute_with_retry,
                        ReportGenerator._execute_optimized_query_tickets_recibidos, 
                        fecha_ini, fecha_fin, tecnicos
                    ),
                    'cerrados': executor.submit(
                        ReportGenerator._execute_with_retry,
                        ReportGenerator._execute_optimized_query_tickets_cerrados, 
                        fecha_ini, fecha_fin, tecnicos
                    ),
                    'sla': executor.submit(
                        ReportGenerator._execute_with_retry,
                        ReportGenerator._execute_optimized_query_sla_metrics, 
                        fecha_ini, fecha_fin, tecnicos
                    ),
                    'reabiertos': executor.submit(
                        ReportGenerator._execute_with_retry,
                        ReportGenerator._execute_optimized_query_reabiertos, 
                        fecha_ini, fecha_fin, tecnicos
                    )
                }
                
                # Recopilar resultados con timeout
                results = {}
                for key, future in futures.items():
                    try:
                        results[key] = future.result(timeout=ReportGenerator.MAX_QUERY_TIMEOUT)
                        logger.debug(f"✅ Consulta {key} completada para chunk {fecha_ini}-{fecha_fin}")
                    except Exception as e:
                        logger.error(f"❌ Error en consulta {key} para chunk {fecha_ini}-{fecha_fin}: {e}")
                        # Devolver DataFrame vacío en caso de error
                        results[key] = pd.DataFrame()
                
                return results
                
        except Exception as e:
            logger.error(f"❌ Error crítico procesando chunk {fecha_ini}-{fecha_fin}: {e}")
            # Devolver estructura vacía en caso de error crítico
            return {
                'recibidos': pd.DataFrame(),
                'cerrados': pd.DataFrame(),
                'sla': pd.DataFrame(),
                'reabiertos': pd.DataFrame()
            }

    @staticmethod
    def _execute_with_retry(func, *args, max_retries=2):
        """Ejecuta una función con reintentos en caso de error"""
        for attempt in range(max_retries + 1):
            try:
                return func(*args)
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"❌ Función {func.__name__} falló después de {max_retries} reintentos: {e}")
                    raise
                else:
                    logger.warning(f"⚠️ Reintento {attempt + 1}/{max_retries} para {func.__name__}: {e}")
                    time.sleep(1)  # Esperar 1 segundo antes del reintento

    @staticmethod
    def _configure_database_for_chunk():
        """Configura la base de datos para optimizar consultas de chunks"""
        try:
            conn = DatabaseConnector.get_connection()
            cursor = conn.cursor()
            
            # Configuraciones de optimización para consultas grandes
            optimizations = [
                "SET SESSION query_cache_type = OFF",  # Desactivar cache para consultas grandes
                "SET SESSION sort_buffer_size = 2097152",  # 2MB para ordenamiento
                "SET SESSION read_buffer_size = 1048576",  # 1MB para lectura
                "SET SESSION join_buffer_size = 1048576",  # 1MB para joins
                "SET SESSION tmp_table_size = 16777216",  # 16MB para tablas temporales
                "SET SESSION max_heap_table_size = 16777216",  # 16MB para tablas en memoria
                f"SET SESSION innodb_lock_wait_timeout = {ReportGenerator.MAX_QUERY_TIMEOUT}",
                "SET SESSION net_read_timeout = 60",
                "SET SESSION net_write_timeout = 60"
            ]
            
            for optimization in optimizations:
                try:
                    cursor.execute(optimization)
                except Exception as e:
                    logger.debug(f"⚠️ No se pudo aplicar optimización '{optimization}': {e}")
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.debug(f"⚠️ No se pudieron aplicar optimizaciones de BD: {e}")

    @staticmethod
    def generar_reporte_principal(fecha_ini=None, fecha_fin=None, tecnicos=None):
        """
        Versión ultra-optimizada del generador de reportes principal
        - Usa consultas paralelas optimizadas
        - Implementa cache inteligente con TTL
        - Procesa por chunks para rangos largos (>90 días)
        - Timeouts configurables y manejo de errores robusto
        - Límites de memoria y registros
        """
        start_time = time.time()
        logger.info(f"🚀 Iniciando reporte ultra-optimizado para rango {fecha_ini} - {fecha_fin}")
        
        # Valores por defecto
        if fecha_ini is None:
            today = date.today()
            fecha_ini = date(today.year, today.month, 1).strftime('%Y-%m-%d')
        
        if fecha_fin is None:
            today = date.today()
            _, last_day = calendar.monthrange(today.year, today.month)
            fecha_fin = date(today.year, today.month, last_day).strftime('%Y-%m-%d')
        
        # Calcular días del rango
        start_date = datetime.strptime(fecha_ini, '%Y-%m-%d').date()
        end_date = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        total_days = (end_date - start_date).days + 1
        
        logger.info(f"📊 Rango de {total_days} días - {'Chunk processing' if total_days > ReportGenerator.CHUNK_SIZE_DAYS else 'Single query'}")
        
        # Verificar cache
        cache_key = ReportGenerator._generate_cache_key(fecha_ini, fecha_fin, tecnicos)
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"📦 Cache hit - retornando resultado cacheado")
            return cached_result
        
        try:
            # Dividir en chunks si el rango es muy largo
            date_chunks = ReportGenerator._get_date_chunks(fecha_ini, fecha_fin, ReportGenerator.CHUNK_SIZE_DAYS)
            logger.info(f"📊 Procesando {len(date_chunks)} chunks de datos")
            
            # Procesar chunks
            if len(date_chunks) > 1:
                # Múltiples chunks - procesamiento paralelo con límites
                logger.info(f"🔄 Procesamiento paralelo de {len(date_chunks)} chunks")
                all_results = []
                
                # Procesar chunks en lotes para evitar sobrecarga
                chunk_batches = [date_chunks[i:i+3] for i in range(0, len(date_chunks), 3)]
                
                for batch_idx, batch in enumerate(chunk_batches):
                    logger.info(f"📦 Procesando lote {batch_idx + 1}/{len(chunk_batches)}")
                    
                    with ThreadPoolExecutor(max_workers=min(len(batch), 3)) as executor:
                        future_to_chunk = {
                            executor.submit(ReportGenerator._process_chunk_parallel, chunk, tecnicos): chunk 
                            for chunk in batch
                        }
                        
                        for future in as_completed(future_to_chunk, timeout=ReportGenerator.MAX_QUERY_TIMEOUT * 2):
                            try:
                                chunk_result = future.result(timeout=ReportGenerator.MAX_QUERY_TIMEOUT)
                                all_results.append(chunk_result)
                            except Exception as e:
                                logger.error(f"❌ Error procesando chunk: {e}")
                                # Continuar con otros chunks
                                continue
                
                if not all_results:
                    raise Exception("No se pudieron procesar ningún chunk")
                
                # Consolidar resultados de todos los chunks
                consolidated_result = ReportGenerator._consolidate_chunk_results(all_results)
            else:
                # Un solo chunk - procesamiento directo optimizado
                logger.info(f"⚡ Procesamiento directo (rango pequeño)")
                consolidated_result = ReportGenerator._process_chunk_parallel(date_chunks[0], tecnicos)
            
            # Combinar y calcular métricas finales
            final_df = ReportGenerator._combine_and_calculate_metrics(consolidated_result)
            
            # Validar que tenemos datos
            if final_df.empty:
                logger.warning("⚠️ No se encontraron datos para el rango especificado")
                return []
            
            # Convertir a formato de salida
            final_result = final_df.to_dict(orient='records')
            
            # Guardar en cache solo si el resultado es válido
            if final_result:
                cache_timeout = ReportGenerator.CACHE_TIMEOUT
                # Cache más largo para rangos grandes
                if total_days > 180:
                    cache_timeout = ReportGenerator.CACHE_TIMEOUT * 2
                    
                cache.set(cache_key, final_result, cache_timeout)
                logger.info(f"💾 Resultado guardado en cache por {cache_timeout/60:.0f} minutos")
            
            execution_time = time.time() - start_time
            logger.info(f"✅ Reporte ultra-optimizado completado en {execution_time:.2f} segundos")
            logger.info(f"📈 Procesados {len(final_result)} técnicos en {len(date_chunks)} chunks")
            
            return final_result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ Error en reporte optimizado después de {execution_time:.2f}s: {e}", exc_info=True)
            
            # Fallback inteligente: si el rango es muy grande, intentar con método simplificado
            if total_days > 365:
                logger.info("🔄 Rango muy grande (>1 año), intentando método simplificado")
                try:
                    return ReportGenerator._generar_reporte_simplificado(fecha_ini, fecha_fin, tecnicos)
                except Exception as fallback_error:
                    logger.error(f"❌ Error en método simplificado: {fallback_error}")
            
            # Último recurso: método original con timeout
            logger.info("🔄 Ejecutando método original como último recurso")
            try:
                return ReportGenerator._generar_reporte_original_con_timeout(fecha_ini, fecha_fin, tecnicos)
            except Exception as original_error:
                logger.error(f"❌ Error en método original: {original_error}")
                raise Exception(f"Todos los métodos fallaron. Último error: {original_error}")

    @staticmethod
    def _generar_reporte_simplificado(fecha_ini: str, fecha_fin: str, tecnicos: Optional[List[str]] = None):
        """Método simplificado para rangos muy grandes (>1 año)"""
        logger.info("🔧 Ejecutando método simplificado para rango grande")
        
        # Dividir en chunks de 6 meses para rangos muy grandes
        date_chunks = ReportGenerator._get_date_chunks(fecha_ini, fecha_fin, 180)
        
        # Procesar secuencialmente para evitar sobrecarga
        consolidated_data = {
            'recibidos': pd.DataFrame(),
            'cerrados': pd.DataFrame(),
            'sla': pd.DataFrame(),
            'reabiertos': pd.DataFrame()
        }
        
        for i, chunk in enumerate(date_chunks):
            logger.info(f"📦 Procesando chunk simplificado {i+1}/{len(date_chunks)}")
            try:
                chunk_result = ReportGenerator._process_chunk_parallel(chunk, tecnicos)
                
                # Consolidar inmediatamente para liberar memoria
                for key in consolidated_data.keys():
                    if not chunk_result[key].empty:
                        if consolidated_data[key].empty:
                            consolidated_data[key] = chunk_result[key].copy()
                        else:
                            consolidated_data[key] = pd.concat([
                                consolidated_data[key], 
                                chunk_result[key]
                            ], ignore_index=True)
                            # Agrupar inmediatamente para optimizar memoria
                            consolidated_data[key] = consolidated_data[key].groupby('tecnico_asignado').sum().reset_index()
                
                # Forzar garbage collection
                import gc
                gc.collect()
                
            except Exception as e:
                logger.warning(f"⚠️ Error en chunk {i+1}, continuando: {e}")
                continue
        
        # Combinar y calcular métricas finales
        final_df = ReportGenerator._combine_and_calculate_metrics(consolidated_data)
        return final_df.to_dict(orient='records') if not final_df.empty else []

    @staticmethod
    def _generar_reporte_original_con_timeout(fecha_ini: str, fecha_fin: str, tecnicos: Optional[List[str]] = None):
        """Método original con timeout para último recurso"""
        logger.info("🔧 Ejecutando método original con timeout")
        
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Consulta cancelada por timeout")
        
        # Configurar timeout de 60 segundos
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(60)
        
        try:
            result = ReportGenerator.generar_reporte_principal_original(fecha_ini, fecha_fin, tecnicos)
            signal.alarm(0)  # Cancelar timeout
            return result
        except TimeoutError:
            logger.error("❌ Timeout en método original")
            raise Exception("La consulta tardó demasiado tiempo (>60s)")
        finally:
            signal.alarm(0)  # Asegurar que se cancele el timeout

    @staticmethod
    def _consolidate_chunk_results(chunk_results: List[Dict]) -> Dict:
        """Consolida resultados de múltiples chunks"""
        consolidated = {
            'recibidos': pd.DataFrame(),
            'cerrados': pd.DataFrame(),
            'sla': pd.DataFrame(),
            'reabiertos': pd.DataFrame()
        }
        
        for chunk_result in chunk_results:
            for key in consolidated.keys():
                if not chunk_result[key].empty:
                    consolidated[key] = pd.concat([consolidated[key], chunk_result[key]], ignore_index=True)
        
        # Agrupar y sumar por técnico
        for key in consolidated.keys():
            if not consolidated[key].empty:
                consolidated[key] = consolidated[key].groupby('tecnico_asignado').sum().reset_index()
        
        return consolidated

    @staticmethod
    def _combine_and_calculate_metrics(data_dict: Dict) -> pd.DataFrame:
        """Combina todos los dataframes y calcula métricas"""
        df_recibidos = data_dict['recibidos']
        df_cerrados = data_dict['cerrados']
        df_sla = data_dict['sla']
        df_reabiertos = data_dict['reabiertos']
        
        # Crear base con todos los técnicos únicos
        all_tecnicos = set()
        for df in [df_recibidos, df_cerrados, df_sla, df_reabiertos]:
            if not df.empty and 'tecnico_asignado' in df.columns:
                all_tecnicos.update(df['tecnico_asignado'].tolist())
        
        base_df = pd.DataFrame({'Tecnico_Asignado': list(all_tecnicos)})
        
        # Combinar dataframes
        if not df_recibidos.empty:
            base_df = base_df.merge(
                df_recibidos[['tecnico_asignado', 'total_tickets_recibidos']],
                left_on='Tecnico_Asignado', right_on='tecnico_asignado', how='left'
            ).drop('tecnico_asignado', axis=1)
        else:
            base_df['total_tickets_recibidos'] = 0
        
        if not df_cerrados.empty:
            base_df = base_df.merge(
                df_cerrados[['tecnico_asignado', 'total_tickets_cerrados']],
                left_on='Tecnico_Asignado', right_on='tecnico_asignado', how='left'
            ).drop('tecnico_asignado', axis=1)
        else:
            base_df['total_tickets_cerrados'] = 0
        
        if not df_sla.empty:
            base_df = base_df.merge(
                df_sla[['tecnico_asignado', 'cerrados_dentro_sla', 'cerrados_con_sla', 'pendientes_sla']],
                left_on='Tecnico_Asignado', right_on='tecnico_asignado', how='left'
            ).drop('tecnico_asignado', axis=1)
        else:
            base_df['cerrados_dentro_sla'] = 0
            base_df['cerrados_con_sla'] = 0
            base_df['pendientes_sla'] = 0
        
        if not df_reabiertos.empty:
            base_df = base_df.merge(
                df_reabiertos[['tecnico_asignado', 'tickets_reabiertos']],
                left_on='Tecnico_Asignado', right_on='tecnico_asignado', how='left'
            ).drop('tecnico_asignado', axis=1)
        else:
            base_df['tickets_reabiertos'] = 0
        
        # Llenar NaN con 0
        base_df = base_df.fillna(0)
        
        # Calcular métricas
        base_df['Cumplimiento SLA'] = base_df.apply(
            lambda row: round((row['cerrados_dentro_sla'] / (row['cerrados_con_sla'] + row['pendientes_sla']) * 100), 2) 
            if (row['cerrados_con_sla'] + row['pendientes_sla']) > 0 else 0, axis=1
        )
        
        base_df['Proporción Reabiertos/Cerrados (%)'] = base_df.apply(
            lambda row: round((row['tickets_reabiertos'] / row['total_tickets_cerrados'] * 100), 2) 
            if row['total_tickets_cerrados'] > 0 else 0, axis=1
        )
        
        # Renombrar columnas para compatibilidad
        base_df = base_df.rename(columns={
            'total_tickets_recibidos': 'Cant_tickets_recibidos',
            'total_tickets_cerrados': 'Cant_tickets_cerrados',
            'cerrados_dentro_sla': 'Cerrados_dentro_SLA',
            'cerrados_con_sla': 'Cerrados_con_SLA',
            'pendientes_sla': 'tickets_pendientes_SLA',
            'tickets_reabiertos': 'Reabiertos'
        })
        
        return base_df

    @staticmethod
    def obtener_tecnicos():
        """Obtiene lista de técnicos disponibles"""
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
    def generar_reporte_principal_original(fecha_ini=None, fecha_fin=None, tecnicos=None):
        """Método original como backup - mantener intacto para compatibilidad"""
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
                    SUM((((YEAR(CASE WHEN gt.solvedate IS NULL THEN DATE(%s) + INTERVAL 1 DAY ELSE gt.solvedate END) - YEAR(gt.`date`)) * 12) + MONTH(CASE WHEN gt.solvedate IS NULL THEN DATE(%s) + INTERVAL 1 DAY ELSE gt.solvedate END)) - MONTH(gt.`date`)) AS T_pendiente_sla_vencido
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