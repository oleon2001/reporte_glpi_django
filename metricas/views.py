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
import matplotlib.pyplot as plt # Biblioteca principal para generar gráficos
import io # Para manejar streams de bytes en memoria (guardar imagen del gráfico)
import base64 # Para codificar la imagen del gráfico en base64 y enviarla al frontend
import numpy as np # Biblioteca numérica, usada aquí para calcular posiciones de barras agrupadas
import logging # Para registrar eventos y errores de la aplicación
import matplotlib.ticker as mticker  # Importar para formatear los valores numéricos en los ejes (no usado activamente aquí, pero útil)
import matplotlib.font_manager as fm # Para gestión de fuentes en Matplotlib (opcional)

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
            WHERE ggu.groups_id = %s
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
    basadas en los datos del reporte principal recibidos vía JSON.
    Devuelve las imágenes codificadas en Base64 en formato JSON.
    """
    try:
        # Decodifica los datos JSON del cuerpo de la petición
        data = json.loads(request.body)
        # Extrae la lista de datos del reporte (lista de diccionarios)
        report_data = data.get('report_data', [])

        # Si no hay datos, no se pueden generar gráficos
        if not report_data:
            return JsonResponse({'error': 'No hay datos para generar las gráficas.'}, status=400)

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

        # --- 2. Configuración de Estilo de Matplotlib ---
        plt.style.use('default') # Empieza con un estilo base limpio
        plt.rcParams.update({ # Actualiza parámetros globales de Matplotlib
            'font.family': 'sans-serif', # Familia de fuentes general
            'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'], # Fuentes específicas a probar
            'axes.titlesize': 16,       # Tamaño título de los ejes (gráficos)
            'axes.labelsize': 14,       # Tamaño etiquetas X e Y
            'xtick.labelsize': 12,      # Tamaño etiquetas de las marcas en eje X
            'ytick.labelsize': 12,      # Tamaño etiquetas de las marcas en eje Y
            'legend.fontsize': 12,      # Tamaño texto de la leyenda
            'figure.titlesize': 18,     # Tamaño título de la figura completa
            'figure.dpi': 150,          # Resolución (puntos por pulgada) para mayor calidad
            'axes.edgecolor': '#333333',  # Color de los bordes de los ejes
            'axes.grid': True,          # Mostrar rejilla
            'grid.color': '#E0E0E0',    # Color de la rejilla
            'grid.linestyle': '--',     # Estilo de línea de la rejilla
            'grid.linewidth': 0.5,      # Grosor de la rejilla
            'axes.facecolor': 'white',  # Color de fondo del área de trazado
            'figure.facecolor': 'white' # Color de fondo de la figura completa
        })

        # Define una paleta de colores
        colors = {
            'primary': '#4CAF50',  # Verde
            'secondary': '#2196F3',  # Azul
            'accent': '#FFC107',     # Amarillo/Naranja
            'danger': '#F44336',     # Rojo
            'neutral': '#9E9E9E',    # Gris
        }

        # Lista para almacenar las imágenes codificadas en base64
        images_base64 = []

        # --- 3. Generación del Gráfico 1: Cumplimiento SLA ---
        fig, ax = plt.subplots(figsize=(12, 6)) # Crea figura y ejes (12x6 pulgadas)
        # Crea el gráfico de barras: x=tecnicos, y=cumplimiento_sla
        bars = ax.bar(tecnicos, cumplimiento_sla, color=colors['primary'], alpha=0.9, edgecolor='black', linewidth=0.7)

        # Añade una línea horizontal para la meta de SLA
        meta_sla = 90 # Define la meta
        ax.axhline(y=meta_sla, color=colors['accent'], linestyle='--', linewidth=1.5, label=f'Meta SLA ({meta_sla}%)')

        # Configura títulos y etiquetas
        ax.set_title('Cumplimiento de SLA por Técnico', pad=20, fontweight='bold')
        ax.set_xlabel('Técnico', labelpad=10)
        ax.set_ylabel('Cumplimiento (%)', labelpad=10)
        # Ajusta el límite superior del eje Y para dar espacio a las etiquetas y la línea de meta
        ax.set_ylim(0, max(110, max(cumplimiento_sla) * 1.1 if cumplimiento_sla else 110))

        # Añade etiquetas de valor encima de cada barra
        for bar in bars: # Itera sobre cada objeto barra devuelto por ax.bar()
            height = bar.get_height() # Obtiene la altura (valor) de la barra
            # Coloca el texto: en la posición x central de la barra, un poco por encima de la altura (height + 2)
            # El texto es la altura formateada a 1 decimal con '%'.
            # ha='center' alinea horizontalmente el texto al centro.
            # va='bottom' alinea verticalmente la base del texto con la coordenada y.
            ax.text(bar.get_x() + bar.get_width() / 2, height + 2, f'{height:.1f}%', ha='center', va='bottom', fontsize=10)

        # Muestra la leyenda (para la línea de meta), colocándola fuera del área del gráfico
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), frameon=False)
        # Rota las etiquetas del eje X para evitar solapamiento
        plt.xticks(rotation=45, ha='right')
        # Ajusta el layout para que todo encaje bien
        plt.tight_layout()

        # Guarda el gráfico en un buffer de memoria en formato PNG
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=plt.rcParams['figure.dpi'])
        buffer.seek(0) # Vuelve al inicio del buffer
        # Codifica la imagen en base64 y la añade a la lista
        images_base64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
        plt.close(fig) # Cierra la figura para liberar memoria

        # --- 4. Generación del Gráfico 2: Volumen de Tickets ---
        fig, ax = plt.subplots(figsize=(12, 6)) # Nueva figura y ejes
        x = np.arange(len(tecnicos)) # Crea un array de números [0, 1, 2, ...] para las posiciones X de los grupos de barras
        width = 0.25 # Ancho de cada barra individual

        # Crea las barras para 'Recibidos', desplazadas a la izquierda (-width)
        bars1 = ax.bar(x - width, tickets_recibidos, width, label='Recibidos', color=colors['secondary'], edgecolor='black', linewidth=0.7)
        # Crea las barras para 'Cerrados', en la posición central (x)
        bars2 = ax.bar(x, tickets_cerrados, width, label='Cerrados', color=colors['primary'], edgecolor='black', linewidth=0.7)
        # Crea las barras para 'Pendientes SLA', desplazadas a la derecha (+width)
        bars3 = ax.bar(x + width, pendientes, width, label='Pendientes SLA', color=colors['danger'], edgecolor='black', linewidth=0.7)

        # Configura títulos y etiquetas
        ax.set_title('Volumen de Tickets por Técnico', pad=20, fontweight='bold')
        ax.set_xlabel('Técnico', labelpad=10)
        ax.set_ylabel('Cantidad de Tickets', labelpad=10)
        # Establece las posiciones de las marcas del eje X para que coincidan con los grupos
        ax.set_xticks(x)
        # Establece las etiquetas del eje X (nombres de técnicos), rotándolas
        ax.set_xticklabels(tecnicos, rotation=45, ha='right')

        # --- Función para añadir etiquetas encima de las barras (Explicación detallada abajo) ---
        def autolabel(bars_container):
            """Añade una etiqueta de texto encima de cada barra en un BarContainer."""
            for bar in bars_container: # Itera sobre cada barra individual en el contenedor
                height = bar.get_height() # Obtiene la altura (valor) de la barra
                if height > 0: # Solo añade etiqueta si la barra tiene altura > 0
                    # Coloca el texto:
                    # x: centro horizontal de la barra (bar.get_x() + bar.get_width() / 2)
                    # y: un poco por encima de la barra (height + 2)
                    # texto: la altura como entero (f'{int(height)}')
                    # ha='center': alineación horizontal centrada
                    # va='bottom': alineación vertical (la base del texto en la coordenada y)
                    ax.text(bar.get_x() + bar.get_width() / 2, height + 0.005, f'{int(height)}',
                            ha='center', va='bottom', fontsize=10)

        # Llama a la función autolabel para cada conjunto de barras
        autolabel(bars1) # Añade etiquetas a las barras de 'Recibidos'
        autolabel(bars2) # Añade etiquetas a las barras de 'Cerrados'
        autolabel(bars3) # Añade etiquetas a las barras de 'Pendientes SLA'

        # Muestra la leyenda, fuera del gráfico
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), frameon=False)
        # Ajusta el layout
        plt.tight_layout()

        # Guarda el segundo gráfico en el buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=plt.rcParams['figure.dpi'])
        buffer.seek(0)
        # Codifica en base64 y añade a la lista
        images_base64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
        plt.close(fig) # Cierra la figura

        # --- 5. Respuesta ---
        # Devuelve la lista de imágenes codificadas en base64 en formato JSON
        return JsonResponse({'images': images_base64})

    except Exception as e:
        # Registra cualquier error durante la generación de gráficos
        logger.error(f"Error al generar las gráficas: {e}", exc_info=True)
        # Devuelve una respuesta de error
        return JsonResponse({'error': 'Ocurrió un error al generar las gráficas.'}, status=500)
