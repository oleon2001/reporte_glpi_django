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

            # Configurar el estilo de la gráfica
            # Usar el estilo por defecto de matplotlib
            plt.style.use('default')
            
            # Definir colores personalizados
            colors = {
                'recibidos': '#2A9D8F',  # Verde turquesa
                'cerrados': '#264653',   # Azul oscuro
                'pendientes': '#E9C46A', # Amarillo
                'sla': '#E76F51'         # Naranja
            }

            # Crear lista para almacenar las imágenes base64
            images_base64 = []

            # Gráfico 1: Cumplimiento SLA
            plt.figure(figsize=(12, 6))
            bars = plt.bar(tecnicos, cumplimiento_sla, color=colors['sla'], alpha=0.9)
            
            # Personalizar el gráfico de cumplimiento
            plt.title('Cumplimiento SLA por Técnico', fontsize=14, pad=20, fontweight='bold')
            plt.xlabel('Técnicos', fontsize=12, labelpad=10)
            plt.ylabel('Cumplimiento (%)', fontsize=12, labelpad=10)
            plt.xticks(rotation=45, ha='right', fontsize=10)
            plt.yticks(fontsize=10)
            
            # Añadir grid
            plt.grid(True, axis='y', linestyle='--', alpha=0.7)
            
            # Añadir valores en las barras
            for bar in bars:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                        f'{height:.1f}%', ha='center', va='bottom', fontsize=10)
            
            # Añadir línea de referencia al 90%
            plt.axhline(y=90, color='red', linestyle='--', alpha=0.5)
            plt.text(len(tecnicos)-0.5, 90, 'Meta: 90%', ha='right', va='bottom', color='red')
            
            # Ajustar el layout
            plt.tight_layout()
            
            # Guardar la primera gráfica
            buffer1 = io.BytesIO()
            plt.savefig(buffer1, format='png', dpi=300, bbox_inches='tight')
            buffer1.seek(0)
            images_base64.append(base64.b64encode(buffer1.getvalue()).decode('utf-8'))
            buffer1.close()
            plt.close()

            # Gráfico 2: Métricas de Tickets
            plt.figure(figsize=(12, 6))
            
            # Configurar el ancho de las barras y el espaciado
            bar_width = 0.25
            index = range(len(tecnicos))
            spacing = 0.05

            # Crear las barras con colores personalizados
            plt.bar([i - bar_width - spacing for i in index], tickets_recibidos, bar_width, 
                   label='Tickets Recibidos', color=colors['recibidos'], alpha=0.9)
            plt.bar([i for i in index], tickets_cerrados, bar_width, 
                   label='Tickets Cerrados', color=colors['cerrados'], alpha=0.9)
            plt.bar([i + bar_width + spacing for i in index], pendientes, bar_width, 
                   label='Pendientes', color=colors['pendientes'], alpha=0.9)

            # Personalizar el gráfico de métricas
            plt.title('Métricas de Tickets por Técnico', fontsize=14, pad=20, fontweight='bold')
            plt.xlabel('Técnicos', fontsize=12, labelpad=10)
            plt.ylabel('Cantidad de Tickets', fontsize=12, labelpad=10)
            plt.xticks(index, tecnicos, rotation=45, ha='right', fontsize=10)
            plt.yticks(fontsize=10)
            
            # Añadir grid
            plt.grid(True, axis='y', linestyle='--', alpha=0.7)
            
            # Añadir leyenda
            plt.legend(fontsize=10, loc='upper right')
            
            # Añadir valores en las barras
            for i, v in enumerate(tickets_recibidos):
                plt.text(i - bar_width - spacing, float(v) + 0.5, f'{float(v):.0f}', ha='center', fontsize=9)
            for i, v in enumerate(tickets_cerrados):
                plt.text(i, float(v) + 0.5, f'{float(v):.0f}', ha='center', fontsize=9)
            for i, v in enumerate(pendientes):
                plt.text(i + bar_width + spacing, float(v) + 0.5, f'{float(v):.0f}', ha='center', fontsize=9)

            # Ajustar el layout
            plt.tight_layout()
            
            # Guardar la segunda gráfica
            buffer2 = io.BytesIO()
            plt.savefig(buffer2, format='png', dpi=300, bbox_inches='tight')
            buffer2.seek(0)
            images_base64.append(base64.b64encode(buffer2.getvalue()).decode('utf-8'))
            buffer2.close()
            plt.close()

            # Devolver ambas imágenes
            return JsonResponse({'images': images_base64})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Método no permitido'}, status=405)