from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('tecnicos/', views.obtener_tecnicos, name='obtener_tecnicos'),
    path('generar-reporte/', views.generar_reporte, name='generar_reporte'),
    path('tickets-reabiertos/', views.tickets_reabiertos, name='tickets_reabiertos'),
    path('obtener-grupos/', views.obtener_grupos, name='obtener_grupos'),
    path('obtener-tecnicos-por-grupo/', views.obtener_tecnicos_por_grupo, name='obtener_tecnicos_por_grupo'),
    path('obtener-subgrupos/', views.obtener_subgrupos, name='obtener_subgrupos'),
    path('obtener-tecnicos-por-subgrupo/', views.obtener_tecnicos_por_subgrupo, name='obtener_tecnicos_por_subgrupo'),
    path('generar-grafica/', views.generar_grafica, name='generar_grafica'),
    path('generar-grafica-tendencia/', views.generar_grafica_tendencia, name='generar_grafica_tendencia'), # Nueva URL
]
