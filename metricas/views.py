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
            data = json.loads(request.body)
            report_data = data.get('report_data', [])

            if not report_data:
                return JsonResponse({'error': 'No hay datos para generar la gráfica'}, status=400)

            # Extraer y convertir datos a números
            tecnicos = [item['Tecnico_Asignado'] for item in report_data]
            tickets_recibidos = [float(item['Cant_tickets_recibidos']) for item in report_data]
            tickets_cerrados = [float(item['Cant_tickets_cerrados']) for item in report_data]
            cumplimiento_sla = [float(item['Cumplimiento SLA']) for item in report_data]
            pendientes = [float(item['tickets_pendientes_SLA']) for item in report_data]

            # Configuración global de estilo
            plt.style.use('seaborn-v0_8-whitegrid')
            plt.rcParams.update({
                'font.family': 'sans-serif',
                'font.sans-serif': ['Arial', 'Helvetica'],
                'font.size': 16,
                'axes.labelsize': 20,
                'axes.titlesize': 24,
                'xtick.labelsize': 16,
                'ytick.labelsize': 16,
                'legend.fontsize': 18,
                'figure.titlesize': 26,
                'figure.dpi': 300,
                'axes.grid': True,
                'grid.alpha': 0.3,
                'figure.constrained_layout.use': True
            })

            # Paleta de colores moderna y profesional
            colors = {
                'primary': '#2563EB',      # Azul principal
                'secondary': '#16A34A',    # Verde
                'accent': '#EA580C',       # Naranja
                'neutral': '#6B7280',      # Gris
                'background': '#F8FAFC',   # Fondo claro
                'grid': '#E2E8F0',        # Gris claro para cuadrícula
                'text': '#1F2937'         # Color de texto oscuro para mejor contraste
            }

            # Lista para almacenar las imágenes base64
            images_base64 = []

            # Gráfico 1: Cumplimiento SLA
            fig, ax = plt.subplots(figsize=(24, 14))
            fig.patch.set_facecolor(colors['background'])
            ax.set_facecolor(colors['background'])

            # Crear barras con gradiente
            bars = ax.bar(tecnicos, cumplimiento_sla, color=colors['primary'], 
                        alpha=0.85, width=0.65)
            
            # Línea de meta SLA
            ax.axhline(y=90, color=colors['accent'], linestyle='--', 
                     label='Meta SLA (90%)', linewidth=4)

            # Títulos y etiquetas
            ax.set_title('Cumplimiento de SLA por Técnico', 
                       pad=40, fontweight='bold', color=colors['text'])
            ax.set_xlabel('Técnico', labelpad=25, color=colors['text'])
            ax.set_ylabel('Porcentaje de Cumplimiento (%)', 
                        labelpad=25, color=colors['text'])

            # Personalizar grid
            ax.grid(True, linestyle='--', alpha=0.2, color=colors['neutral'])
            
            # Rotar y ajustar etiquetas del eje x
            plt.xticks(rotation=45, ha='right')
            
            # Añadir valores sobre las barras con mayor tamaño y mejor posicionamiento
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                      f'{height:.1f}%',
                      ha='center', va='bottom',
                      fontsize=16,
                      fontweight='bold',
                      color=colors['text'])

            # Ajustar límites y márgenes con más espacio
            max_value = max(cumplimiento_sla)
            ax.set_ylim(0, max(max_value * 1.2, 100))

            # Añadir leyenda
            ax.legend(loc='upper right', frameon=True,
                    facecolor=colors['background'],
                    edgecolor=colors['neutral'],
                    framealpha=0.9,
                    fontsize=18,
                    bbox_to_anchor=(1, 1))

            # Guardar primer gráfico
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', 
                      facecolor=colors['background'], pad_inches=0.7)
            buffer.seek(0)
            images_base64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
            plt.close()

            # Gráfico 2: Métricas de Tickets
            fig, ax = plt.subplots(figsize=(24, 14))
            fig.patch.set_facecolor(colors['background'])
            ax.set_facecolor(colors['background'])

            # Configurar las barras agrupadas con más espacio
            x = np.arange(len(tecnicos))
            width = 0.22

            # Crear las barras para cada métrica con colores distintos
            bars1 = ax.bar(x - width*1.2, tickets_recibidos, width,
                         label='Recibidos', color=colors['primary'], alpha=0.85)
            bars2 = ax.bar(x, tickets_cerrados, width,
                         label='Cerrados', color=colors['secondary'], alpha=0.85)
            bars3 = ax.bar(x + width*1.2, pendientes, width,
                         label='Pendientes', color=colors['accent'], alpha=0.85)

            # Títulos y etiquetas
            ax.set_title('Métricas de Tickets por Técnico', 
                       pad=40, fontweight='bold', color=colors['text'])
            ax.set_xlabel('Técnico', labelpad=25, color=colors['text'])
            ax.set_ylabel('Cantidad de Tickets', labelpad=25, color=colors['text'])

            # Configurar eje x
            ax.set_xticks(x)
            ax.set_xticklabels(tecnicos, rotation=45, ha='right')

            # Personalizar grid
            ax.grid(True, linestyle='--', alpha=0.2, color=colors['neutral'])

            # Función mejorada para añadir valores sobre las barras
            def autolabel(bars):
                for bar in bars:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                          f'{int(height)}',
                          ha='center', va='bottom',
                          fontsize=16,
                          fontweight='bold',
                          color=colors['text'])

            autolabel(bars1)
            autolabel(bars2)
            autolabel(bars3)

            # Leyenda mejorada
            ax.legend(loc='upper right',
                    frameon=True,
                    facecolor=colors['background'],
                    edgecolor=colors['neutral'],
                    framealpha=0.9,
                    fontsize=18,
                    bbox_to_anchor=(1, 1))

            # Ajustar límites y márgenes con más espacio
            max_value = max(max(tickets_recibidos), max(tickets_cerrados), max(pendientes))
            ax.set_ylim(0, max_value * 1.2)

            # Guardar segundo gráfico
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight',
                      facecolor=colors['background'], pad_inches=0.7)
            buffer.seek(0)
            images_base64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
            plt.close()

            return JsonResponse({'images': images_base64})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Método no permitido'}, status=405)