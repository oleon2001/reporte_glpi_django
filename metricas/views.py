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
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning("Error al decodificar JSON en generar_grafica", exc_info=True)
            return JsonResponse({'error': 'Formato de datos inválido (se esperaba JSON).'}, status=400)

        report_data = data.get('report_data', [])

        if not report_data:
            logger.warning("Intento de generar gráfica sin datos.")
            return JsonResponse({'error': 'No hay datos para generar la gráfica'}, status=400)

        # --- Procesamiento de Datos ---
        tecnicos = []
        tickets_recibidos = []
        tickets_cerrados = []
        cumplimiento_sla = []
        pendientes = []

        for item in report_data:
            try:
                tecnicos.append(item.get('Tecnico_Asignado', 'Desconocido'))
                tickets_recibidos.append(float(item.get('Cant_tickets_recibidos', 0) or 0))
                tickets_cerrados.append(float(item.get('Cant_tickets_cerrados', 0) or 0))
                sla_val = item.get('Cumplimiento SLA', 0)
                cumplimiento_sla.append(float(sla_val) if sla_val not in [None, 'N/A', ''] else 0.0)
                pendientes.append(float(item.get('tickets_pendientes_SLA', 0) or 0))
            except (ValueError, TypeError) as conv_error:
                logger.error(f"Error convirtiendo datos para gráfica: {conv_error} en item: {item}", exc_info=True)
                return JsonResponse({'error': f'Error en los datos numéricos del reporte para {item.get("Tecnico_Asignado")}.'}, status=400)

        # --- Configuración de Matplotlib ---
        plt.style.use('seaborn-v0_8-whitegrid')
        plt.rcParams.update({
            'font.family': 'sans-serif',
            'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
            'font.size': 16,
            'axes.labelsize': 20,
            'axes.titlesize': 24,
            'xtick.labelsize': 14,
            'ytick.labelsize': 16,
            'legend.fontsize': 18,
            'figure.titlesize': 26,
            'figure.dpi': 300,
            'axes.grid': True,
            'grid.alpha': 0.4,
            'grid.linestyle': '--',
            'figure.constrained_layout.use': True
        })
        colors = {
            'primary': '#3B82F6', 'secondary': '#10B981', 'accent': '#F59E0B',
            'neutral': '#6B7280', 'background': '#FFFFFF', 'grid': '#D1D5DB', 'text': '#111827'
        }

        images_base64 = []

        # --- Gráfico 1: Cumplimiento SLA ---
        try:
            fig, ax = plt.subplots(figsize=(30, 18)) # Tamaño aumentado
            fig.patch.set_facecolor(colors['background'])
            ax.set_facecolor(colors['background'])
            bars = ax.bar(tecnicos, cumplimiento_sla, color=colors['primary'], alpha=0.9, width=0.6)
            ax.axhline(y=90, color=colors['accent'], linestyle=':', linewidth=3, label='Meta SLA (90%)')
            ax.set_title('Cumplimiento de SLA por Técnico', pad=30, fontweight='bold', color=colors['text'])
            ax.set_xlabel('Técnico', labelpad=20, color=colors['text'])
            ax.set_ylabel('Cumplimiento (%)', labelpad=20, color=colors['text'])
            ax.grid(True, axis='y', linestyle=plt.rcParams['grid.linestyle'], alpha=plt.rcParams['grid.alpha'], color=colors['grid'])
            ax.grid(False, axis='x')
            plt.xticks(rotation=45, ha='right')

            # --- MODIFICACIÓN PARA EVITAR ERROR xytext ---
            for bar in bars:
                height = bar.get_height()
                # Ajusta el valor sumado a 'height' (ej. 0.5, 1, 2...) según necesites
                label_y_position = height + 0.5 # Pequeño offset vertical
                ax.text(bar.get_x() + bar.get_width()/2., label_y_position, # Usar la nueva posición Y
                      f'{height:.1f}%',
                      ha='center', va='bottom', # va='bottom' ahora se alinea con la base de la barra + offset
                      fontsize=14,
                      fontweight='medium',
                      color=colors['text'])
            # --- FIN MODIFICACIÓN ---

            max_value_sla = max(cumplimiento_sla) if cumplimiento_sla else 0
            ax.set_ylim(0, max(max_value_sla * 1.15, 105))
            ax.legend(loc='best', frameon=True, facecolor=colors['background'], edgecolor=colors['neutral'], framealpha=0.8)

            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', facecolor=colors['background'], pad_inches=0.5)
            buffer.seek(0)
            images_base64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
            plt.close(fig)
            logger.info("Gráfico de Cumplimiento SLA generado.")

        except Exception as e_sla:
            logger.error(f"Error generando gráfico SLA: {e_sla}", exc_info=True)
            # Considera si retornar aquí o continuar con el siguiente gráfico
            # return JsonResponse({'error': 'Error al generar el gráfico de SLA.'}, status=500)


        # --- Gráfico 2: Métricas de Tickets ---
        try:
            fig, ax = plt.subplots(figsize=(30, 18)) # Tamaño aumentado
            fig.patch.set_facecolor(colors['background'])
            ax.set_facecolor(colors['background'])
            x = np.arange(len(tecnicos))
            width = 0.25
            bars1 = ax.bar(x - width, tickets_recibidos, width, label='Recibidos', color=colors['primary'], alpha=0.9)
            bars2 = ax.bar(x, tickets_cerrados, width, label='Cerrados', color=colors['secondary'], alpha=0.9)
            bars3 = ax.bar(x + width, pendientes, width, label='Pendientes SLA Vencido', color=colors['accent'], alpha=0.9)
            ax.set_title('Volumen de Tickets por Técnico', pad=30, fontweight='bold', color=colors['text'])
            ax.set_xlabel('Técnico', labelpad=20, color=colors['text'])
            ax.set_ylabel('Cantidad de Tickets', labelpad=20, color=colors['text'])
            ax.set_xticks(x)
            ax.set_xticklabels(tecnicos, rotation=45, ha='right')
            ax.grid(True, axis='y', linestyle=plt.rcParams['grid.linestyle'], alpha=plt.rcParams['grid.alpha'], color=colors['grid'])
            ax.grid(False, axis='x')

            # --- MODIFICACIÓN PARA EVITAR ERROR xytext ---
            def autolabel(bars_group):
                for bar in bars_group:
                    height = bar.get_height()
                    if height > 0:
                        # Ajusta el valor sumado a 'height' (ej. 0.5, 1, 2...) según necesites
                        label_y_position = height + 0.5 # Pequeño offset vertical
                        ax.text(bar.get_x() + bar.get_width()/2., label_y_position, # Usar la nueva posición Y
                              f'{int(height)}',
                              ha='center', va='bottom', # va='bottom' ahora se alinea con la base de la barra + offset
                              fontsize=14,
                              fontweight='medium',
                              color=colors['text'])
            # --- FIN MODIFICACIÓN ---

            autolabel(bars1)
            autolabel(bars2)
            autolabel(bars3)

            max_val_tickets = 0
            if tickets_recibidos or tickets_cerrados or pendientes:
                 max_val_tickets = max([max(tickets_recibidos or [0]), max(tickets_cerrados or [0]), max(pendientes or [0])])
            ax.set_ylim(0, max_val_tickets * 1.15 if max_val_tickets > 0 else 10)
            ax.legend(loc='best', frameon=True, facecolor=colors['background'], edgecolor=colors['neutral'], framealpha=0.8)

            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', facecolor=colors['background'], pad_inches=0.5)
            buffer.seek(0)
            images_base64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
            plt.close(fig)
            logger.info("Gráfico de Volumen de Tickets generado.")

        except Exception as e_vol:
            logger.error(f"Error generando gráfico de Volumen: {e_vol}", exc_info=True)
            # return JsonResponse({'error': 'Error al generar el gráfico de volumen de tickets.'}, status=500)

        # --- Respuesta Final ---
        if not images_base64:
             # Si hubo error en ambos gráficos, images_base64 estará vacío
             return JsonResponse({'error': 'No se pudieron generar las gráficas debido a errores internos.'}, status=500)
        elif len(images_base64) < 2: # Si solo se generó una
             logger.warning("Solo se pudo generar una de las dos gráficas.")
             # Decide si devolver la única que se generó o un error. Aquí devolvemos la que hay:
             return JsonResponse({'images': images_base64, 'warning': 'Una de las gráficas no pudo ser generada.'})


        logger.info(f"Gráficas generadas exitosamente para {len(tecnicos)} técnicos.")
        return JsonResponse({'images': images_base64})

    except Exception as e:
        logger.error(f"Error general en generar_grafica: {e}", exc_info=True)
        return JsonResponse({'error': 'Ocurrió un error inesperado al generar las gráficas.'}, status=500)

# Asegúrate de que las otras vistas (obtener_grupos, etc.) también tengan manejo de errores
# y cierren conexiones/cursores en un bloque finally si usan DatabaseConnector directamente.
# (He añadido bloques try/finally a esas vistas en este ejemplo)
