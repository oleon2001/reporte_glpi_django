# /home/oleon/Escritorio/reporte_glpi_django/metricas/views.py
import json # Para trabajar con datos JSON (en requests/responses)
from django.shortcuts import render, redirect # Funciones básicas de Django para renderizar plantillas y redirigir
from django.http import JsonResponse # Para devolver respuestas en formato JSON
from .services import ReportGenerator, DatabaseConnector # Importa clases del módulo services para lógica de negocio (reportes, conexión DB)
import re # Para usar expresiones regulares (validación de fechas)
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie # Decoradores para manejo de CSRF
from django.contrib.auth.decorators import login_required # Decorador para requerir que el usuario esté autenticado
from django.contrib.auth import login, logout, authenticate # Funciones de autenticación de Django
from django.contrib import messages # Para mostrar mensajes flash al usuario (éxito, error, info)
from django.contrib.auth.forms import AuthenticationForm # Formulario estándar de autenticación (aunque aquí se usa uno personalizado implícitamente)
from django.views.decorators.http import require_http_methods, require_GET # Decoradores para restringir métodos HTTP permitidos
import logging # Para registrar eventos y errores de la aplicación
import plotly.graph_objects as go # Biblioteca principal para gráficos interactivos
import plotly.express as px # Interfaz de alto nivel para Plotly
from plotly.utils import PlotlyJSONEncoder # Para serializar figuras de Plotly a JSON
import pandas as pd # Importar pandas para manejar el DataFrame del servicio

# Configura el logger para este módulo. Usará la configuración definida en settings.py
logger = logging.getLogger(__name__)

# --- Vista de Login ---
@ensure_csrf_cookie # Asegura que se envíe una cookie CSRF al cliente (necesario para el POST del login)
@require_http_methods(["GET", "POST"]) # Permite solo peticiones GET (mostrar formulario) y POST (enviar credenciales)
def login_view(request):
    """
    Gestiona el inicio de sesión del usuario.
    - GET: Muestra el formulario de login.
    - POST: Procesa las credenciales usando el backend GLPIAuthBackend.
            Verifica si el usuario autenticado pertenece al grupo Django requerido.
    """
    # Si el usuario ya está autenticado
    if request.user.is_authenticated:
        # Nombre del grupo Django requerido para acceder (debe coincidir con auth_backend.py)
        required_group_name = 'Perfil Requerido' # Podría importarse desde settings o una constante
        # Verifica si el usuario pertenece a ese grupo
        if not request.user.groups.filter(name=required_group_name).exists():
            # Si no pertenece, se registra el intento y se cierra la sesión
            logger.warning(f"Usuario {request.user.username} intentó acceder sin el grupo '{required_group_name}'. Cerrando sesión.")
            logout(request) # Cierra la sesión actual
            messages.error(request, 'No tiene los permisos necesarios para acceder a esta aplicación.') # Mensaje de error
            return redirect('login') # Redirige de vuelta al login
        # Si está autenticado y tiene el grupo, redirige al índice
        logger.info(f"Usuario {request.user.username} ya autenticado y con permisos. Redirigiendo a index.")
        return redirect('index')

    # Si la petición es POST (intento de login)
    if request.method == 'POST':
        username = request.POST.get('username') # Obtiene el usuario del formulario
        password = request.POST.get('password') # Obtiene la contraseña del formulario

        # Validación básica de que los campos no estén vacíos
        if not username or not password:
            messages.error(request, 'Por favor, ingrese su usuario y contraseña.')
            return render(request, 'metricas/login.html') # Vuelve a mostrar el formulario

        # Intenta autenticar usando TODOS los backends configurados en settings.py
        # En este caso, debería usar principalmente GLPIAuthBackend
        user = authenticate(request, username=username, password=password)

        # Si authenticate() devuelve un objeto User, la autenticación fue exitosa
        if user is not None:
            # El backend GLPIAuthBackend ya se encargó de:
            # 1. Validar credenciales contra GLPI.
            # 2. Verificar el perfil GLPI (si no es usuario especial).
            # 3. Crear/obtener el usuario Django.
            # 4. Añadir el usuario al grupo Django 'Perfil Requerido'.
            login(request, user) # Inicia la sesión en Django para este usuario
            logger.info(f"Inicio de sesión exitoso para el usuario {username}.")
            # Redirige a la página 'next' si existe (ej. si intentó acceder a una página protegida antes de loguearse)
            # o a la página 'index' por defecto.
            next_url = request.GET.get('next', 'index')
            return redirect(next_url)
        else:
            # Si authenticate() devuelve None, el login falló por alguna razón
            # (usuario/pass incorrecto, perfil GLPI no válido, error de conexión, etc.)
            logger.warning(f"Intento de inicio de sesión fallido para el usuario {username}.")
            # Mensaje de error genérico por seguridad (no revelar detalles)
            messages.error(request, 'Usuario o contraseña incorrectos, o no cumple los requisitos de acceso.')
            # Vuelve a mostrar el formulario de login
            return render(request, 'metricas/login.html')

    # Si la petición es GET (o si el POST falló y no se redirigió), muestra el formulario
    return render(request, 'metricas/login.html')

# --- Vista de Logout ---
@login_required # Requiere que el usuario esté logueado para poder desloguearse
def logout_view(request):
    """Cierra la sesión del usuario actual."""
    logger.info(f"Usuario {request.user.username} cerrando sesión.")
    logout(request) # Cierra la sesión de Django
    messages.info(request, 'Has cerrado sesión exitosamente.') # Mensaje informativo
    return redirect('login') # Redirige a la página de login

# --- Vista Principal (Index) ---
@login_required # Requiere autenticación para acceder
def index(request):
    """Muestra la página principal de la aplicación."""
    # La verificación de permisos (grupo) ya se hizo en login_view al iniciar sesión.
    # Si un usuario sin el grupo intenta acceder directamente, @login_required lo mandará
    # a login, y allí se le negará el acceso si intenta loguearse de nuevo.
    return render(request, 'metricas/index.html')

# --- API: Obtener Técnicos ---
@login_required # Requiere autenticación
@require_GET # Permite solo peticiones GET
def obtener_tecnicos(request):
    """Devuelve una lista de nombres de técnicos (perfil 10 en GLPI) en formato JSON."""
    try:
        # Llama al método estático de ReportGenerator para obtener los técnicos
        tecnicos = ReportGenerator.obtener_tecnicos()
        # Devuelve la lista en formato JSON
        return JsonResponse({'tecnicos': tecnicos})
    except Exception as e:
        # Registra cualquier error que ocurra
        logger.error(f"Error al obtener técnicos: {e}", exc_info=True) # exc_info=True añade el traceback al log
        # Devuelve una respuesta de error en JSON con estado HTTP 500
        return JsonResponse({'error': 'Ocurrió un error al obtener la lista de técnicos.'}, status=500)

# --- API: Generar Reporte Principal ---
@login_required # Requiere autenticación
@require_http_methods(["POST"]) # Permite solo peticiones POST
def generar_reporte(request):
    """
    Genera el reporte principal con métricas por técnico.
    Espera datos JSON en el cuerpo de la petición con 'fecha_ini', 'fecha_fin', y 'tecnicos'.
    Devuelve los resultados del reporte en formato JSON.
    """
    try:
        # Intenta decodificar el cuerpo de la petición como JSON
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning("Error al decodificar JSON en generar_reporte", exc_info=True)
            return JsonResponse({'error': 'Formato de datos inválido (se esperaba JSON).'}, status=400) # Error 400: Bad Request

        # Extrae los datos del JSON decodificado
        fecha_ini = data.get('fecha_ini')
        fecha_fin = data.get('fecha_fin')
        tecnicos_seleccionados = data.get('tecnicos') # Puede ser None, una lista ['Tecnico1', 'Tecnico2'], o el string 'todos'

        # Validación de fechas: deben existir
        if not fecha_ini or not fecha_fin:
             return JsonResponse({'error': 'Las fechas de inicio y fin son requeridas.'}, status=400)
        # Validación de fechas: formato YYYY-MM-DD usando expresión regular
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_ini) or not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_fin):
            return JsonResponse({'error': 'Formato de fecha inválido (debe ser YYYY-MM-DD).'}, status=400)

        # Determina la lista final de técnicos para pasar a la consulta SQL
        tecnicos_a_consultar = None # Por defecto, si es None, la consulta SQL no filtrará por técnico
        if tecnicos_seleccionados == 'todos':
             tecnicos_a_consultar = None # La consulta SQL está preparada para manejar None (no filtra)
        elif isinstance(tecnicos_seleccionados, list) and tecnicos_seleccionados:
            # Si es una lista y no está vacía, usa esa lista
            tecnicos_a_consultar = tecnicos_seleccionados
        elif isinstance(tecnicos_seleccionados, list) and not tecnicos_seleccionados:
             # Si se envió una lista vacía explícitamente, no devolvemos resultados
             return JsonResponse({'data': []}) # Devuelve una lista vacía

        # Registra la acción
        logger.info(f"Generando reporte principal para fechas {fecha_ini} a {fecha_fin} y técnicos: {tecnicos_a_consultar or 'Todos'}")
        # Llama al método del servicio para generar el reporte
        resultados = ReportGenerator.generar_reporte_principal(fecha_ini, fecha_fin, tecnicos_a_consultar)
        # Devuelve los resultados en formato JSON
        return JsonResponse({'data': resultados})

    except Exception as e:
        # Registra cualquier error inesperado
        logger.error(f"Error al generar reporte principal: {e}", exc_info=True)
        # Devuelve una respuesta de error genérica
        return JsonResponse({'error': 'Ocurrió un error inesperado al generar el reporte.'}, status=500)

# --- API: Obtener Tickets Reabiertos ---
@login_required # Requiere autenticación
@require_http_methods(["POST"]) # Permite solo peticiones POST
def tickets_reabiertos(request):
    """
    Obtiene la lista de tickets reabiertos para un técnico específico en un rango de fechas.
    Espera datos en formato form-data o x-www-form-urlencoded (request.POST).
    Devuelve los detalles de los tickets en formato JSON.
    """
    try:
        # Obtiene los datos de la petición POST
        data = request.POST
        tecnico = data.get('tecnico')
        fecha_ini = data.get('fecha_ini')
        fecha_fin = data.get('fecha_fin')

        # Validación: el técnico es requerido
        if not tecnico:
            return JsonResponse({'error': 'El nombre del técnico es requerido.'}, status=400)
        # Validación de fechas (similar a generar_reporte)
        if not fecha_ini or not fecha_fin:
             return JsonResponse({'error': 'Las fechas de inicio y fin son requeridas.'}, status=400)
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_ini) or not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_fin):
            return JsonResponse({'error': 'Formato de fecha inválido (debe ser YYYY-MM-DD).'}, status=400)

        # Registra la acción
        logger.info(f"Obteniendo tickets reabiertos para {tecnico} entre {fecha_ini} y {fecha_fin}")
        # Llama al método del servicio para obtener los tickets
        tickets = ReportGenerator.obtener_tickets_reabiertos(tecnico, fecha_ini, fecha_fin)
        # Devuelve los resultados en JSON
        return JsonResponse({'data': tickets})

    except Exception as e:
        # Registra cualquier error
        # Es buena práctica incluir el técnico en el mensaje de error para facilitar la depuración
        logger.error(f"Error al obtener tickets reabiertos para {tecnico}: {e}", exc_info=True)
        # Devuelve una respuesta de error
        return JsonResponse({'error': 'Ocurrió un error al obtener los tickets reabiertos.'}, status=500)

# --- API: Obtener Grupos (Entidades GLPI Nivel 3) ---
@login_required # Requiere autenticación
@require_GET # Permite solo peticiones GET
def obtener_grupos(request):
    """
    Obtiene una lista de entidades GLPI de nivel 3 (usadas como 'grupos' principales).
    Devuelve la lista (id, name) en formato JSON.
    """
    conn = None # Inicializa la conexión a None
    cursor = None # Inicializa el cursor a None
    try:
        # Obtiene una conexión a la base de datos GLPI
        conn = DatabaseConnector.get_connection()
        # Crea un cursor que devuelve resultados como diccionarios
        cursor = conn.cursor(dictionary=True)
        # Query para obtener entidades de nivel 3, ordenadas por nombre
        query = "SELECT ge.id, ge.name FROM glpi_entities ge WHERE ge.`level` = 3 ORDER BY ge.name"
        cursor.execute(query) # Ejecuta la query
        grupos = cursor.fetchall() # Obtiene todos los resultados
        # Devuelve los grupos en formato JSON
        return JsonResponse({'grupos': grupos})
    except Exception as e:
        # Registra cualquier error
        logger.error(f"Error al obtener grupos GLPI: {e}", exc_info=True)
        # Devuelve una respuesta de error
        return JsonResponse({'error': 'Error al obtener los grupos.'}, status=500)
    finally:
        # Bloque finally: se ejecuta siempre, haya error o no
        # Asegura que el cursor y la conexión se cierren correctamente
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

# --- API: Obtener Técnicos por Grupo (Entidad GLPI) ---
@login_required # Requiere autenticación
@require_GET # Permite solo peticiones GET
def obtener_tecnicos_por_grupo(request):
    """
    Obtiene una lista de técnicos asociados a una entidad GLPI específica (grupo principal).
    Espera el parámetro 'grupo_id' (ID de la entidad) en la query string.
    Devuelve la lista de técnicos (id, nombre) en formato JSON.
    """
    conn = None
    cursor = None
    grupo_id = request.GET.get('grupo_id') # Obtiene el ID del grupo de los parámetros GET
    try:
        # Validación: grupo_id es requerido
        if not grupo_id:
            return JsonResponse({'error': 'El parámetro grupo_id es requerido'}, status=400)
        # Validación: grupo_id debe ser un número entero
        try:
            grupo_id_int = int(grupo_id)
        except ValueError:
            return JsonResponse({'error': 'El parámetro grupo_id debe ser un número entero.'}, status=400)

        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Query para obtener técnicos (usuarios) que pertenecen a grupos (glpi_groups)
        # cuya entidad asociada (entities_id) es la entidad padre seleccionada.
        # DISTINCT evita duplicados si un usuario está en varios grupos de la misma entidad.
        query = """
            SELECT DISTINCT gu.id, CONCAT(gu.realname, ' ', gu.firstname) AS nombre
            FROM glpi_groups_users ggu
            JOIN glpi_users gu ON gu.id = ggu.users_id
            JOIN glpi_groups gg ON gg.id = ggu.groups_id
            WHERE gg.entities_id = %s
            ORDER BY nombre;
        """
        # Ejecuta la query pasando el ID del grupo como parámetro seguro
        cursor.execute(query, (grupo_id_int,))
        tecnicos = cursor.fetchall() # Obtiene los resultados

        # Devuelve la lista de técnicos en JSON
        return JsonResponse({'tecnicos': tecnicos})
    except Exception as e:
        # Registra el error, incluyendo el grupo_id para contexto
        logger.error(f"Error al obtener técnicos por grupo ID {grupo_id}: {e}", exc_info=True)
        # Devuelve una respuesta de error
        return JsonResponse({'error': 'Error al obtener los técnicos para el grupo seleccionado.'}, status=500)
    finally:
        # Cierra cursor y conexión
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

# --- API: Obtener Subgrupos (Grupos GLPI asociados a una Entidad) ---
@login_required # Requiere autenticación
@require_GET # Permite solo peticiones GET
def obtener_subgrupos(request):
    """
    Obtiene una lista de grupos GLPI (glpi_groups) cuya entidad asociada es la entidad padre especificada.
    Espera el parámetro 'grupo_id' (ID de la entidad padre) en la query string.
    Devuelve la lista de subgrupos (id, name, comment) en formato JSON.
    """
    conn = None
    cursor = None
    grupo_id = request.GET.get('grupo_id') # ID de la entidad padre
    try:
        # Validación: grupo_id es requerido
        if not grupo_id:
            return JsonResponse({'error': 'El parámetro grupo_id (entidad padre) es requerido'}, status=400)
        # Validación: grupo_id debe ser entero
        try:
            grupo_id_int = int(grupo_id)
        except ValueError:
             return JsonResponse({'error': 'El parámetro grupo_id debe ser un número entero.'}, status=400)

        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Query para obtener los grupos (glpi_groups) asociados a la entidad padre
        query = """
            SELECT gg.id, gg.name, gg.comment
            FROM glpi_groups gg
            WHERE gg.entities_id = %s
            ORDER BY gg.name;
        """
        cursor.execute(query, (grupo_id_int,))
        subgrupos = cursor.fetchall() # Estos son los 'subgrupos' reales de GLPI

        # Devuelve la lista de subgrupos en JSON
        return JsonResponse({'subgrupos': subgrupos})
    except Exception as e:
        # Registra el error
        logger.error(f"Error al obtener subgrupos para entidad ID {grupo_id}: {e}", exc_info=True)
        # Devuelve respuesta de error
        return JsonResponse({'error': 'Error al obtener los subgrupos.'}, status=500)
    finally:
        # Cierra cursor y conexión
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

# --- API: Obtener Técnicos por Subgrupo (Grupo GLPI) ---
@login_required # Requiere autenticación
@require_GET # Permite solo peticiones GET
def obtener_tecnicos_por_subgrupo(request):
    """
    Obtiene una lista de técnicos (usuarios) que pertenecen a un grupo GLPI específico (glpi_groups).
    Espera el parámetro 'subgrupo_id' (ID del grupo GLPI) en la query string.
    Devuelve la lista de técnicos (id, nombre) en formato JSON.
    """
    conn = None
    cursor = None
    subgrupo_id = request.GET.get('subgrupo_id') # ID del grupo GLPI (subgrupo)
    try:
        # Validación: subgrupo_id es requerido
        if not subgrupo_id:
            return JsonResponse({'error': 'El parámetro subgrupo_id es requerido'}, status=400)
        # Validación: subgrupo_id debe ser entero
        try:
            subgrupo_id_int = int(subgrupo_id)
        except ValueError:
             return JsonResponse({'error': 'El parámetro subgrupo_id debe ser un número entero.'}, status=400)

        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Query para obtener los usuarios que pertenecen directamente al grupo GLPI especificado
        query = """
            SELECT DISTINCT gu.id, CONCAT(gu.realname, ' ', gu.firstname) AS nombre
            FROM glpi_groups_users ggu
            JOIN glpi_users gu ON gu.id = ggu.users_id
            JOIN glpi_profiles_users gpu ON gu.id = gpu.users_id
            JOIN glpi_profiles gp ON gpu.profiles_id = gp.id
            WHERE ggu.groups_id = %s and gp.id=10
            ORDER BY nombre;
        """
        cursor.execute(query, (subgrupo_id_int,))
        tecnicos = cursor.fetchall() # Obtiene la lista de técnicos

        # Devuelve la lista completa de diccionarios {id: x, nombre: y}
        return JsonResponse({'tecnicos': tecnicos})

    except Exception as e:
        # Registra el error
        logger.error(f"Error al obtener técnicos por subgrupo ID {subgrupo_id}: {e}", exc_info=True)
        # Devuelve respuesta de error
        return JsonResponse({'error': 'Error al obtener los técnicos para el subgrupo seleccionado.'}, status=500)
    finally:
        # Cierra cursor y conexión
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

# --- API: Generar Gráficas ---
@login_required # Requiere autenticación
@require_http_methods(["POST"]) # Permite solo peticiones POST
def generar_grafica(request):
    """
    Genera imágenes de gráficos (Cumplimiento SLA y Volumen de Tickets)
    basadas en los datos del reporte principal recibidos vía JSON, usando Plotly.
    Devuelve las imágenes codificadas en Base64 en formato JSON.
    """
    try:
        # Decodifica los datos JSON del cuerpo de la petición
        data = json.loads(request.body)
        # Extrae la lista de datos del reporte (lista de diccionarios)
        report_data = data.get('report_data', [])

        # Si no hay datos, no se pueden generar gráficos
        if not report_data:
            return JsonResponse({'error': 'No hay datos para generar las gráficas.'}, status=404) # 404 Not Found es más apropiado si no hay datos

        # --- 1. Procesamiento de Datos para los Gráficos ---
        tecnicos = []           # Lista para nombres de técnicos (eje X)
        tickets_recibidos = []  # Lista para cantidad de tickets recibidos
        tickets_cerrados = []   # Lista para cantidad de tickets cerrados
        cumplimiento_sla = []   # Lista para porcentaje de cumplimiento SLA
        pendientes = []         # Lista para cantidad de tickets pendientes SLA

        # Itera sobre cada fila (diccionario) de los datos del reporte
        for item in report_data:
            # Obtiene el nombre completo del técnico
            nombre_completo = item.get('Tecnico_Asignado', 'Desconocido')
            # Acorta el nombre para mejor visualización en el gráfico (ej: primer nombre y primer apellido)
            partes_nombre = nombre_completo.split()
            nombre_corto = f"{partes_nombre[0]} {partes_nombre[1]}" if len(partes_nombre) > 1 else nombre_completo
            tecnicos.append(nombre_corto) # Añade el nombre corto a la lista

            # Extrae y convierte los valores numéricos, usando 0 por defecto si falta o es None/vacío
            tickets_recibidos.append(float(item.get('Cant_tickets_recibidos', 0) or 0))
            tickets_cerrados.append(float(item.get('Cant_tickets_cerrados', 0) or 0))
            sla_value = item.get('Cumplimiento SLA', 0) # Obtiene el valor de SLA
            try:
                # Intenta convertir a float, maneja None explícitamente
                cumplimiento_sla.append(float(sla_value) if sla_value is not None else 0.0)
            except (ValueError, TypeError):
                 # Si la conversión falla (ej. si es un string no numérico), registra y usa 0
                 logger.warning(f"Valor inválido para 'Cumplimiento SLA': {sla_value}. Usando 0.")
                 cumplimiento_sla.append(0.0)
            pendientes.append(float(item.get('tickets_pendientes_SLA', 0) or 0))

        # --- 2. Definición de Colores (puedes personalizarlos) ---
        colors = {
            'primary': '#4CAF50',  # Verde
            'secondary': '#2196F3',  # Azul
            'accent': '#FFC107',     # Amarillo/Naranja
            'danger': '#F44336',     # Rojo
            'neutral': '#9E9E9E',    # Gris
            'text_light': '#FFFFFF',
            'text_dark': '#333333'
        }

        # Lista para almacenar los JSON de las figuras de Plotly
        plotly_figures_json = []

        # --- 3. Generación del Gráfico 1: Cumplimiento SLA con Plotly ---
        fig_sla = go.Figure()

        # Añadir barras de cumplimiento
        fig_sla.add_trace(go.Bar(
            x=tecnicos,
            y=cumplimiento_sla,
            name='Cumplimiento SLA',
            marker_color=colors['primary'],
            text=[f'{val:.1f}%' for val in cumplimiento_sla], # Texto para mostrar en las barras
            textposition='outside', # Posición del texto
            hoverinfo='x+y', # Información al pasar el mouse
            hovertemplate='%{x}: %{y:.1f}%<extra></extra>' # Plantilla del hover
        ))

        # Añadir línea de meta SLA
        meta_sla = 90 # Define la meta
        fig_sla.add_hline(y=meta_sla, line_dash="dash", line_color=colors['accent'],
                          annotation_text=f"Meta SLA ({meta_sla}%)",
                          annotation_position="bottom right")

        # Configurar layout del gráfico SLA
        fig_sla.update_layout(
            title='Cumplimiento de SLA por Técnico',
            xaxis_title='Técnico',
            yaxis_title='Cumplimiento (%)',
            yaxis_range=[0, max(105, max(cumplimiento_sla) * 1.1 if cumplimiento_sla else 105)], # Rango eje Y
            legend_title_text='Leyenda',
            template='plotly_white', # Estilo base
            title_x=0.5, # Centrar título
            margin=dict(l=40, r=40, t=80, b=80), # Márgenes
            xaxis_tickangle=-45, # Rotar etiquetas eje X
            hovermode='x unified' # Mostrar info de todas las barras al pasar por una categoría X
        )

        # Convertir figura SLA a JSON y añadir a la lista
        plotly_figures_json.append(json.dumps(fig_sla, cls=PlotlyJSONEncoder))

        # --- 4. Generación del Gráfico 2: Volumen de Tickets con Plotly ---
        fig_volumen = go.Figure()

        # Añadir barras para 'Recibidos'
        fig_volumen.add_trace(go.Bar(
            x=tecnicos,
            y=tickets_recibidos,
            name='Recibidos',
            marker_color=colors['secondary'],
            text=[f'{int(val)}' for val in tickets_recibidos],
            textposition='outside',
            hoverinfo='x+y',
            hovertemplate='%{x} (Recibidos): %{y}<extra></extra>'
        ))

        # Añadir barras para 'Cerrados'
        fig_volumen.add_trace(go.Bar(
            x=tecnicos,
            y=tickets_cerrados,
            name='Cerrados',
            marker_color=colors['primary'],
            text=[f'{int(val)}' for val in tickets_cerrados],
            textposition='outside',
            hoverinfo='x+y',
            hovertemplate='%{x} (Cerrados): %{y}<extra></extra>'
        ))

        # Añadir barras para 'Pendientes SLA'
        fig_volumen.add_trace(go.Bar(
            x=tecnicos,
            y=pendientes,
            name='Pendientes SLA',
            marker_color=colors['danger'],
            text=[f'{int(val)}' for val in pendientes],
            textposition='outside',
            hoverinfo='x+y',
            hovertemplate='%{x} (Pendientes SLA): %{y}<extra></extra>'
        ))

        # Configurar layout del gráfico de Volumen
        fig_volumen.update_layout(
            title='Volumen de Tickets por Técnico',
            xaxis_title='Técnico',
            yaxis_title='Cantidad de Tickets',
            barmode='group', # Modo de barras agrupadas
            legend_title_text='Métrica',
            template='plotly_white',
            title_x=0.5,
            margin=dict(l=40, r=40, t=80, b=80),
            xaxis_tickangle=-45,
            hovermode='x unified',
            yaxis=dict(rangemode='tozero') # Asegurar que el eje Y empiece en 0
        )

        # Convertir figura Volumen a JSON y añadir a la lista
        plotly_figures_json.append(json.dumps(fig_volumen, cls=PlotlyJSONEncoder))

        # --- 5. Respuesta ---
        # Devuelve la lista de JSONs de las figuras de Plotly
        # El frontend usará Plotly.js para renderizar estos JSONs
        return JsonResponse({'plotly_figures': plotly_figures_json})

    except Exception as e:
        # Registra cualquier error durante la generación de gráficos
        logger.error(f"Error al generar las gráficas: {e}", exc_info=True)
        # Devuelve una respuesta de error
        return JsonResponse({'error': 'Ocurrió un error al generar las gráficas.'}, status=500)

# --- API: Generar Gráfica de Tendencia por Técnico ---
@login_required
@require_http_methods(["POST"])
def generar_grafica_tendencia(request):
    """
    Genera una imagen de gráfico de tendencia (Recibidos vs Cerrados por día)
    para un técnico específico en un rango de fechas, usando Plotly.
    Espera datos JSON con 'tecnico', 'fecha_ini', 'fecha_fin'.
    Devuelve el JSON de la figura de Plotly.
    """
    try:
        # Decodifica los datos JSON del cuerpo de la petición
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning("Error al decodificar JSON en generar_grafica_tendencia", exc_info=True)
            return JsonResponse({'error': 'Formato de datos inválido (se esperaba JSON).'}, status=400)

        # Extrae los datos necesarios
        tecnico = data.get('tecnico')
        fecha_ini = data.get('fecha_ini')
        fecha_fin = data.get('fecha_fin')

        # Validación básica
        if not all([tecnico, fecha_ini, fecha_fin]):
            return JsonResponse({'error': 'Faltan parámetros requeridos (tecnico, fecha_ini, fecha_fin).'}, status=400)
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_ini) or not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_fin):
            return JsonResponse({'error': 'Formato de fecha inválido (debe ser YYYY-MM-DD).'}, status=400)

        logger.info(f"Generando gráfica de tendencia para {tecnico} entre {fecha_ini} y {fecha_fin}")

        # Obtener datos del servicio
        df_tendencia = ReportGenerator.obtener_datos_tendencia_tecnico(tecnico, fecha_ini, fecha_fin)

        if df_tendencia.empty:
            logger.warning(f"No se encontraron datos de tendencia para {tecnico} en el rango {fecha_ini} - {fecha_fin}")
            return JsonResponse({'error': 'No hay datos disponibles para generar la gráfica de tendencia en el rango seleccionado.'}, status=404)
        # Asegurarse que 'dia' sea datetime si no lo es ya
        df_tendencia['dia'] = pd.to_datetime(df_tendencia['dia'])

        # --- Generación del Gráfico de Tendencia con Plotly ---
        fig_tendencia = go.Figure()

        # Añadir línea para 'Recibidos'
        fig_tendencia.add_trace(go.Scatter(
            x=df_tendencia['dia'],
            y=df_tendencia['recibidos'],
            mode='lines+markers+text', # Mostrar línea, marcadores y texto
            name='Recibidos',
            line=dict(color='#2196F3', width=2),
            marker=dict(symbol='circle', size=8),
            text=[f'{y}' if y > 0 else '' for y in df_tendencia['recibidos']], # Texto solo si > 0
            textposition='top center',
            textfont=dict(size=10),
            hoverinfo='x+y',
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>Recibidos: %{y}<extra></extra>'
        ))

        # Añadir línea para 'Cerrados'
        fig_tendencia.add_trace(go.Scatter(
            x=df_tendencia['dia'],
            y=df_tendencia['cerrados'],
            mode='lines+markers+text',
            name='Cerrados',
            line=dict(color='#4CAF50', width=2, dash='dash'), # Línea discontinua
            marker=dict(symbol='x', size=8),
            text=[f'{y}' if y > 0 else '' for y in df_tendencia['cerrados']],
            textposition='bottom center', # Posición diferente para evitar solapamiento
            textfont=dict(size=10),
            hoverinfo='x+y',
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>Cerrados: %{y}<extra></extra>'
        ))

        # Configurar layout del gráfico de Tendencia
        fig_tendencia.update_layout(
            title=f'Tendencia de Tickets para {tecnico}<br><sup>{fecha_ini} a {fecha_fin}</sup>', # Título con subtítulo
            xaxis_title='Fecha',
            yaxis_title='Cantidad de Tickets',
            legend_title_text='Métrica',
            template='plotly_white',
            title_x=0.5,
            margin=dict(l=40, r=40, t=90, b=40),
            hovermode='x unified', # Información unificada al pasar el mouse
            xaxis=dict(
                tickformat='%Y-%m-%d', # Formato de fecha en el eje
                dtick='D1', # Mostrar cada día si hay espacio, Plotly ajustará
                tickangle=-45
            ),
            yaxis=dict(rangemode='tozero') # Asegurar que el eje Y empiece en 0
        )

        # Convertir figura a JSON
        figure_json = json.dumps(fig_tendencia, cls=PlotlyJSONEncoder)

        return JsonResponse({'plotly_figure': figure_json})

    except Exception as e:
        logger.error(f"Error al generar gráfica de tendencia para {tecnico}: {e}", exc_info=True)
        return JsonResponse({'error': 'Ocurrió un error inesperado al generar la gráfica de tendencia.'}, status=500)
