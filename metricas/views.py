# /home/oleon/Escritorio/reporte_glpi_django/metricas/views.py
import json
from django.shortcuts import render, redirect
from django.http import JsonResponse
from .services import ReportGenerator, DatabaseConnector
import re
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.http import require_http_methods, require_GET
import matplotlib.pyplot as plt
import io
import base64
import numpy as np
import logging # Importar logging
import matplotlib.ticker as mticker  # Importar para formatear los valores numéricos
import matplotlib.font_manager as fm # Para fuentes personalizadas (opcional)

# Configurar logging (puedes añadir esto al principio del archivo si no está)
logger = logging.getLogger(__name__)

@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        # Verificar si el usuario tiene el grupo requerido
        # Asegúrate de que el nombre del grupo 'Perfil Requerido' coincide
        # con el definido en tu auth_backend.py (REQUIRED_DJANGO_GROUP_NAME)
        required_group_name = 'Perfil Requerido' # O usa una constante importada
        if not request.user.groups.filter(name=required_group_name).exists():
            logger.warning(f"Usuario {request.user.username} intentó acceder sin el grupo '{required_group_name}'. Cerrando sesión.")
            logout(request)
            messages.error(request, 'No tiene los permisos necesarios para acceder a esta aplicación.')
            return redirect('login')
        logger.info(f"Usuario {request.user.username} ya autenticado y con permisos. Redirigiendo a index.")
        return redirect('index')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            messages.error(request, 'Por favor, ingrese su usuario y contraseña.')
            return render(request, 'metricas/login.html')

        # Usamos el backend personalizado GLPIAuthBackend
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # El backend ya verificó el perfil GLPI (si es necesario)
            # y añadió al usuario al grupo Django requerido.
            login(request, user)
            logger.info(f"Inicio de sesión exitoso para el usuario {username}.")
            next_url = request.GET.get('next', 'index')
            return redirect(next_url)
        else:
            # El backend devuelve None si la autenticación falla (usuario/pass incorrecto,
            # perfil GLPI faltante, error de conexión, etc.)
            logger.warning(f"Intento de inicio de sesión fallido para el usuario {username}.")
            messages.error(request, 'Usuario o contraseña incorrectos, o no cumple los requisitos de acceso.')
            # No reveles la razón exacta del fallo al usuario por seguridad

    return render(request, 'metricas/login.html')

@login_required
def logout_view(request):
    logger.info(f"Usuario {request.user.username} cerrando sesión.")
    logout(request)
    messages.info(request, 'Has cerrado sesión exitosamente.')
    return redirect('login')

@login_required
def index(request):
    # La verificación de grupo ya se hizo en login_view o el decorador @login_required
    # redirige a login si no está autenticado.
    return render(request, 'metricas/index.html')

@login_required
@require_GET # Asegurar que solo se use GET
def obtener_tecnicos(request):
    try:
        tecnicos = ReportGenerator.obtener_tecnicos()
        return JsonResponse({'tecnicos': tecnicos})
    except Exception as e:
        logger.error(f"Error al obtener técnicos: {e}", exc_info=True)
        return JsonResponse({'error': 'Ocurrió un error al obtener la lista de técnicos.'}, status=500)

@login_required
@require_http_methods(["POST"]) # Asegurar que solo se use POST
def generar_reporte(request):
    try:
        # Intentar decodificar JSON del cuerpo
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning("Error al decodificar JSON en generar_reporte", exc_info=True)
            return JsonResponse({'error': 'Formato de datos inválido (se esperaba JSON).'}, status=400)

        fecha_ini = data.get('fecha_ini')
        fecha_fin = data.get('fecha_fin')
        tecnicos_seleccionados = data.get('tecnicos') # Puede ser None, lista o string 'todos'

        # Validar fechas
        if not fecha_ini or not fecha_fin:
             return JsonResponse({'error': 'Las fechas de inicio y fin son requeridas.'}, status=400)
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_ini) or not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_fin):
            return JsonResponse({'error': 'Formato de fecha inválido (debe ser YYYY-MM-DD).'}, status=400)

        # Determinar la lista final de técnicos
        tecnicos_a_consultar = None # Por defecto, consulta todos si no se especifica
        if tecnicos_seleccionados == 'todos':
             # No es necesario obtenerlos aquí si la consulta SQL maneja bien el None o lista vacía
             # tecnicos_a_consultar = ReportGenerator.obtener_tecnicos() # Podría ser ineficiente
             tecnicos_a_consultar = None # Dejar que la consulta maneje la ausencia de filtro
        elif isinstance(tecnicos_seleccionados, list) and tecnicos_seleccionados:
            tecnicos_a_consultar = tecnicos_seleccionados
        elif isinstance(tecnicos_seleccionados, list) and not tecnicos_seleccionados:
             # Si se envía una lista vacía, quizás no se quiera ningún resultado
             return JsonResponse({'data': []}) # Devolver vacío si no se selecciona ningún técnico


        logger.info(f"Generando reporte principal para fechas {fecha_ini} a {fecha_fin} y técnicos: {tecnicos_a_consultar or 'Todos'}")
        resultados = ReportGenerator.generar_reporte_principal(fecha_ini, fecha_fin, tecnicos_a_consultar)
        return JsonResponse({'data': resultados})

    except Exception as e:
        logger.error(f"Error al generar reporte principal: {e}", exc_info=True)
        return JsonResponse({'error': 'Ocurrió un error inesperado al generar el reporte.'}, status=500)
    # No necesitas la cláusula final 'return JsonResponse...' porque @require_http_methods ya maneja otros métodos

@login_required
@require_http_methods(["POST"]) # Asegurar que solo se use POST
def tickets_reabiertos(request):
    try:
        # Asumiendo que los datos vienen como form-data o x-www-form-urlencoded
        # Si vienen como JSON, usa json.loads(request.body) como en generar_reporte
        data = request.POST
        tecnico = data.get('tecnico')
        fecha_ini = data.get('fecha_ini')
        fecha_fin = data.get('fecha_fin')

        if not tecnico:
            return JsonResponse({'error': 'El nombre del técnico es requerido.'}, status=400)
        # Añadir validación de fechas si es necesario (similar a generar_reporte)
        if not fecha_ini or not fecha_fin:
             return JsonResponse({'error': 'Las fechas de inicio y fin son requeridas.'}, status=400)
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_ini) or not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_fin):
            return JsonResponse({'error': 'Formato de fecha inválido (debe ser YYYY-MM-DD).'}, status=400)


        logger.info(f"Obteniendo tickets reabiertos para {tecnico} entre {fecha_ini} y {fecha_fin}")
        tickets = ReportGenerator.obtener_tickets_reabiertos(tecnico, fecha_ini, fecha_fin)
        return JsonResponse({'data': tickets})

    except Exception as e:
        logger.error(f"Error al obtener tickets reabiertos para {tecnico}: {e}", exc_info=True)
        return JsonResponse({'error': 'Ocurrió un error al obtener los tickets reabiertos.'}, status=500)

@login_required
@require_GET
def obtener_grupos(request):
    conn = None
    cursor = None
    try:
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)
        # Query para obtener los grupos de nivel 3 (Asegúrate que este nivel es correcto para tu GLPI)
        query = "SELECT ge.id, ge.name FROM glpi_entities ge WHERE ge.`level` = 3 ORDER BY ge.name" # Añadido ORDER BY
        cursor.execute(query)
        grupos = cursor.fetchall()
        return JsonResponse({'grupos': grupos})
    except Exception as e:
        logger.error(f"Error al obtener grupos GLPI: {e}", exc_info=True)
        return JsonResponse({'error': 'Error al obtener los grupos.'}, status=500)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@login_required
@require_GET
def obtener_tecnicos_por_grupo(request):
    conn = None
    cursor = None
    try:
        grupo_id = request.GET.get('grupo_id')
        if not grupo_id:
            return JsonResponse({'error': 'El parámetro grupo_id es requerido'}, status=400)
        try:
            grupo_id_int = int(grupo_id) # Validar que sea un entero
        except ValueError:
            return JsonResponse({'error': 'El parámetro grupo_id debe ser un número entero.'}, status=400)

        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Query para obtener los técnicos asociados DIRECTAMENTE a una ENTIDAD (grupo)
        # Ajusta esta query si la relación es diferente (e.g., a través de glpi_groups)
        # Esta query asume que los usuarios están directamente en glpi_entities_users
        # O quizás necesitas buscar usuarios en glpi_groups que pertenecen a esa entidad?
        # Consulta A: Usuarios directamente en la entidad
        # query = """
        #     SELECT gu.id, CONCAT(gu.realname, ' ', gu.firstname) AS nombre
        #     FROM glpi_entities_users geu
        #     JOIN glpi_users gu ON gu.id = geu.users_id
        #     WHERE geu.entities_id = %s AND geu.is_recursive = 1 # O 0 dependiendo de tu necesidad
        #     ORDER BY nombre;
        # """
        # Consulta B: Usuarios en grupos cuya entidad es la seleccionada
        query = """
            SELECT DISTINCT gu.id, CONCAT(gu.realname, ' ', gu.firstname) AS nombre
            FROM glpi_groups_users ggu
            JOIN glpi_users gu ON gu.id = ggu.users_id
            JOIN glpi_groups gg ON gg.id = ggu.groups_id
            WHERE gg.entities_id = %s
            ORDER BY nombre;
        """
        # Consulta C: Usuarios con perfil técnico asignados a tickets de esa entidad (más complejo)
        # ... (requeriría joins con glpi_tickets, glpi_tickets_users, etc.)

        # Elige la consulta que mejor represente "técnicos por grupo (entidad)" en tu GLPI
        cursor.execute(query, (grupo_id_int,))
        tecnicos = cursor.fetchall()

        return JsonResponse({'tecnicos': tecnicos})
    except Exception as e:
        logger.error(f"Error al obtener técnicos por grupo ID {grupo_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Error al obtener los técnicos para el grupo seleccionado.'}, status=500)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@login_required
@require_GET
def obtener_subgrupos(request):
    conn = None
    cursor = None
    try:
        grupo_id = request.GET.get('grupo_id') # Este es el ID de la entidad padre
        if not grupo_id:
            return JsonResponse({'error': 'El parámetro grupo_id (entidad padre) es requerido'}, status=400)
        try:
            grupo_id_int = int(grupo_id)
        except ValueError:
             return JsonResponse({'error': 'El parámetro grupo_id debe ser un número entero.'}, status=400)

        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Query para obtener los GRUPOS (glpi_groups) cuya entidad asociada es la entidad padre seleccionada
        query = """
            SELECT gg.id, gg.name, gg.comment # Añadido comment por si es útil
            FROM glpi_groups gg
            WHERE gg.entities_id = %s
            ORDER BY gg.name;
        """
        cursor.execute(query, (grupo_id_int,))
        subgrupos = cursor.fetchall() # Estos son los 'subgrupos' reales de GLPI

        return JsonResponse({'subgrupos': subgrupos})
    except Exception as e:
        logger.error(f"Error al obtener subgrupos para entidad ID {grupo_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Error al obtener los subgrupos.'}, status=500)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@login_required
@require_GET
def obtener_tecnicos_por_subgrupo(request):
    conn = None
    cursor = None
    try:
        subgrupo_id = request.GET.get('subgrupo_id') # Este es el ID de glpi_groups
        if not subgrupo_id:
            return JsonResponse({'error': 'El parámetro subgrupo_id es requerido'}, status=400)
        try:
            subgrupo_id_int = int(subgrupo_id)
        except ValueError:
             return JsonResponse({'error': 'El parámetro subgrupo_id debe ser un número entero.'}, status=400)

        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Query para obtener los técnicos (usuarios) que pertenecen a un glpi_group específico
        query = """
            SELECT DISTINCT gu.id, CONCAT(gu.realname, ' ', gu.firstname) AS nombre
            FROM glpi_groups_users ggu
            JOIN glpi_users gu ON gu.id = ggu.users_id
            WHERE ggu.groups_id = %s
            ORDER BY nombre;
        """
        cursor.execute(query, (subgrupo_id_int,))
        tecnicos = cursor.fetchall()

        # Devolver solo los nombres si es necesario, o la lista completa de diccionarios
        # nombres_tecnicos = [t['nombre'] for t in tecnicos]
        # return JsonResponse({'tecnicos': nombres_tecnicos})
        return JsonResponse({'tecnicos': tecnicos}) # Devuelve [{id: x, nombre: y}, ...]

    except Exception as e:
        logger.error(f"Error al obtener técnicos por subgrupo ID {subgrupo_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Error al obtener los técnicos para el subgrupo seleccionado.'}, status=500)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@login_required
@require_http_methods(["POST"]) # Solo POST
def generar_grafica(request):
    try:
        data = json.loads(request.body)
        report_data = data.get('report_data', [])

        if not report_data:
            return JsonResponse({'error': 'No hay datos para generar las gráficas.'}, status=400)

        # --- Procesamiento de Datos ---
        tecnicos = []
        tickets_recibidos = []
        tickets_cerrados = []
        cumplimiento_sla = []
        pendientes = []

        for item in report_data:
            # Acortar nombres largos si es necesario para mejor visualización
            nombre_completo = item.get('Tecnico_Asignado', 'Desconocido')
            partes_nombre = nombre_completo.split()
            # Ejemplo: Usar solo primer nombre y primer apellido
            nombre_corto = f"{partes_nombre[0]} {partes_nombre[1]}" if len(partes_nombre) > 1 else nombre_completo
            # O podrías limitar la longitud: nombre_corto = nombre_completo[:15] + '...' if len(nombre_completo) > 15 else nombre_completo
            tecnicos.append(nombre_corto)

            tickets_recibidos.append(float(item.get('Cant_tickets_recibidos', 0) or 0))
            tickets_cerrados.append(float(item.get('Cant_tickets_cerrados', 0) or 0))
            sla_value = item.get('Cumplimiento SLA', 0)
            try:
                cumplimiento_sla.append(float(sla_value) if sla_value is not None else 0.0)
            except (ValueError, TypeError):
                 logger.warning(f"Valor inválido para 'Cumplimiento SLA': {sla_value}. Usando 0.")
                 cumplimiento_sla.append(0.0)
            pendientes.append(float(item.get('tickets_pendientes_SLA', 0) or 0))


        # --- Configuración de Matplotlib Mejorada ---
        plt.style.use('default')  # Usar el estilo predeterminado para un diseño limpio
        plt.rcParams.update({
            'font.family': 'sans-serif',
            'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],  # Fuentes profesionales
            'axes.titlesize': 16,       # Tamaño del título del eje
            'axes.labelsize': 14,       # Tamaño de las etiquetas de los ejes
            'xtick.labelsize': 12,      # Tamaño de las etiquetas del eje X
            'ytick.labelsize': 12,      # Tamaño de las etiquetas del eje Y
            'legend.fontsize': 12,      # Tamaño de la leyenda
            'figure.titlesize': 18,     # Tamaño del título de la figura
            'figure.dpi': 150,          # DPI para mayor calidad
            'axes.edgecolor': '#333333',  # Color de los bordes de los ejes
            'axes.grid': True,          # Mostrar la rejilla
            'grid.color': '#E0E0E0',    # Color de la rejilla
            'grid.linestyle': '--',     # Estilo de la rejilla
            'grid.linewidth': 0.5,      # Grosor de la rejilla
            'axes.facecolor': 'white',  # Fondo blanco para los ejes
            'figure.facecolor': 'white' # Fondo blanco para la figura
        })

        # Paleta de colores profesional
        colors = {
            'primary': '#4CAF50',  # Verde profesional
            'secondary': '#2196F3',  # Azul profesional
            'accent': '#FFC107',     # Amarillo profesional
            'danger': '#F44336',     # Rojo profesional
            'neutral': '#9E9E9E',    # Gris
        }

        images_base64 = []

        # --- Gráfico 1: Cumplimiento SLA ---
        fig, ax = plt.subplots(figsize=(12, 6))
        bars = ax.bar(tecnicos, cumplimiento_sla, color=colors['primary'], alpha=0.9, edgecolor='black', linewidth=0.7)

        # Línea de meta SLA
        meta_sla = 90
        ax.axhline(y=meta_sla, color=colors['accent'], linestyle='--', linewidth=1.5, label=f'Meta SLA ({meta_sla}%)')

        ax.set_title('Cumplimiento de SLA por Técnico', pad=20, fontweight='bold')
        ax.set_xlabel('Técnico', labelpad=10)
        ax.set_ylabel('Cumplimiento (%)', labelpad=10)
        ax.set_ylim(0, max(110, max(cumplimiento_sla) * 1.1 if cumplimiento_sla else 110))

        # Etiquetas en las barras
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, height + 2, f'{height:.1f}%', ha='center', va='bottom', fontsize=10)

        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), frameon=False)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=plt.rcParams['figure.dpi'])
        buffer.seek(0)
        images_base64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
        plt.close(fig)

        # --- Gráfico 2: Volumen de Tickets ---
        fig, ax = plt.subplots(figsize=(12, 6))
        x = np.arange(len(tecnicos))
        width = 0.25

        bars1 = ax.bar(x - width, tickets_recibidos, width, label='Recibidos', color=colors['secondary'], edgecolor='black', linewidth=0.7)
        bars2 = ax.bar(x, tickets_cerrados, width, label='Cerrados', color=colors['primary'], edgecolor='black', linewidth=0.7)
        bars3 = ax.bar(x + width, pendientes, width, label='Pendientes SLA', color=colors['danger'], edgecolor='black', linewidth=0.7)

        ax.set_title('Volumen de Tickets por Técnico', pad=20, fontweight='bold')
        ax.set_xlabel('Técnico', labelpad=10)
        ax.set_ylabel('Cantidad de Tickets', labelpad=10)
        ax.set_xticks(x)
        ax.set_xticklabels(tecnicos, rotation=45, ha='right')

        # Etiquetas en las barras
        def autolabel(bars):
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2, height + 2, f'{int(height)}', ha='center', va='bottom', fontsize=10)

        autolabel(bars1)
        autolabel(bars2)
        autolabel(bars3)

        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), frameon=False)
        plt.tight_layout()

        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=plt.rcParams['figure.dpi'])
        buffer.seek(0)
        images_base64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
        plt.close(fig)

        return JsonResponse({'images': images_base64})

    except Exception as e:
        logger.error(f"Error al generar las gráficas: {e}", exc_info=True)
        return JsonResponse({'error': 'Ocurrió un error al generar las gráficas.'}, status=500)
