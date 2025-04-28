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

@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        # Verificar si el usuario tiene el perfil requerido
        if not request.user.groups.filter(name='Perfil Requerido').exists():
            logout(request)
            messages.error(request, 'No tiene permisos para acceder.')
            return redirect('login')
        return redirect('index')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            messages.error(request, 'Por favor, ingrese su usuario y contraseña.')
            return render(request, 'metricas/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', 'index')
            return redirect(next_url)
        else:
            messages.error(request, 'Usuario o contraseña incorrectos o no tiene permisos para acceder.')

    return render(request, 'metricas/login.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def index(request):
    return render(request, 'metricas/index.html')

@login_required
def obtener_tecnicos(request):
    try:
        tecnicos = ReportGenerator.obtener_tecnicos()
        return JsonResponse({'tecnicos': tecnicos})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def generar_reporte(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.body else request.POST
            fecha_ini = data.get('fecha_ini')
            fecha_fin = data.get('fecha_fin')
            
            # Manejar la selección de todos los técnicos
            if data.get('seleccionar_todos', False):
                tecnicos = ReportGenerator.obtener_tecnicos()
            else:
                tecnicos = data.get('tecnicos', '[]')
                if isinstance(tecnicos, str):
                    tecnicos = json.loads(tecnicos)

            # Validar fechas
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_ini) or not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha_fin):
                return JsonResponse({'error': 'Formato de fecha inválido (YYYY-MM-DD)'}, status=400)

            resultados = ReportGenerator.generar_reporte_principal(fecha_ini, fecha_fin, tecnicos)
            return JsonResponse({'data': resultados})
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Formato de datos inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
def tickets_reabiertos(request):
    if request.method == 'POST':
        try:
            data = request.POST
            tecnico = data.get('tecnico')
            fecha_ini = data.get('fecha_ini')
            fecha_fin = data.get('fecha_fin')

            tickets = ReportGenerator.obtener_tickets_reabiertos(tecnico, fecha_ini, fecha_fin)
            return JsonResponse({'data': tickets})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
@require_GET
def obtener_grupos(request):
    try:
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query para obtener los grupos de nivel 3
        query = "SELECT ge.id, ge.name FROM glpi_entities ge WHERE ge.`level` = 3"
        cursor.execute(query)
        grupos = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return JsonResponse({'grupos': grupos})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_GET
def obtener_tecnicos_por_grupo(request):
    try:
        grupo_id = request.GET.get('grupo_id')
        if not grupo_id:
            return JsonResponse({'error': 'El parámetro grupo_id es requerido'}, status=400)
        
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query para obtener los técnicos según el grupo seleccionado
        query = """
            SELECT gu.id, CONCAT(gu.realname, ' ', gu.firstname) AS nombre
            FROM glpi_groups_users ggu
            JOIN glpi_users gu ON gu.id = ggu.users_id
            WHERE ggu.groups_id = %s
        """
        cursor.execute(query, (grupo_id,))
        tecnicos = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return JsonResponse({'tecnicos': tecnicos})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_GET
def obtener_subgrupos(request):
    try:
        grupo_id = request.GET.get('grupo_id')
        if not grupo_id:
            return JsonResponse({'error': 'El parámetro grupo_id es requerido'}, status=400)
        
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query para obtener los subgrupos según el grupo seleccionado
        query = """
            SELECT gg.id, gg.entities_id, gg.name
            FROM glpi_groups gg
            JOIN glpi_entities ge ON gg.entities_id = ge.id
            WHERE ge.id = %s
        """
        cursor.execute(query, (grupo_id,))
        subgrupos = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return JsonResponse({'subgrupos': subgrupos})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_GET
def obtener_tecnicos_por_subgrupo(request):
    try:
        subgrupo_id = request.GET.get('subgrupo_id')
        if not subgrupo_id:
            return JsonResponse({'error': 'El parámetro subgrupo_id es requerido'}, status=400)
        
        conn = DatabaseConnector.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query para obtener los técnicos según el subgrupo seleccionado
        query = """
            SELECT CONCAT(gu.realname, ' ', gu.firstname) AS nombre
            FROM glpi_groups_users ggu
            JOIN glpi_users gu ON gu.id = ggu.users_id
            WHERE ggu.groups_id = %s
        """
        cursor.execute(query, (subgrupo_id,))
        tecnicos = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return JsonResponse({'tecnicos': tecnicos})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def generar_grafica(request):
    if request.method == 'POST':
        try:
            # Obtener los datos del reporte enviados desde el frontend
            data = json.loads(request.body)
            report_data = data.get('report_data', [])

            if not report_data:
                return JsonResponse({'error': 'No hay datos para generar la gráfica'}, status=400)

            # Extraer datos para la gráfica
            tecnicos = [item['Tecnico_Asignado'] for item in report_data]
            tickets_recibidos = [item['Cant_tickets_recibidos'] for item in report_data]
            tickets_cerrados = [item['Cant_tickets_cerrados'] for item in report_data]
            cumplimiento_sla = [item['Cumplimiento SLA'] for item in report_data]
            pendientes = [item['tickets_pendientes_SLA'] for item in report_data]

            # Crear la gráfica
            plt.figure(figsize=(14, 8))
            bar_width = 0.2
            index = range(len(tecnicos))

            # Barras para cada métrica
            plt.bar(index, tickets_recibidos, bar_width, label='Tickets Recibidos', color='skyblue')
            plt.bar([i + bar_width for i in index], tickets_cerrados, bar_width, label='Tickets Cerrados', color='green')
            plt.bar([i + 2 * bar_width for i in index], pendientes, bar_width, label='Pendientes', color='orange')
            plt.bar([i + 3 * bar_width for i in index], cumplimiento_sla, bar_width, label='Cumplimiento SLA (%)', color='purple')

            plt.xlabel('Técnicos')
            plt.ylabel('Valores')
            plt.title('Métricas por Técnico')
            plt.xticks([i + 1.5 * bar_width for i in index], tecnicos, rotation=45, ha='right')
            plt.legend()

            # Guardar la gráfica en un buffer
            buffer = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buffer, format='png')
            buffer.seek(0)

            # Convertir la gráfica a base64
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            buffer.close()

            # Devolver la imagen en formato base64
            return JsonResponse({'image': image_base64})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Método no permitido'}, status=405)