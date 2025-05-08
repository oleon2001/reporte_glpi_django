import pandas as pd
import plotly.express as px
import random
import io
import plotly.io as pio

# --- 1. Generación de Datos de Ejemplo ---
# Creamos una lista de técnicos y períodos.
tecnicos = ['Juan Pérez', 'María García', 'Carlos Rodríguez', 'Ana López']
periodos = pd.to_datetime(['2024-01-01', '2024-04-01', '2024-07-01', '2024-10-01', '2025-01-01'])
periodos_str = periodos.strftime('%Y-%m') # Formatear periodos como Año-Mes para el eje X

data = []
# Generamos datos de cumplimiento aleatorios para cada técnico y período.
# Simulamos una tendencia general con alguna variación.
base_compliance = 85
for tecnico in tecnicos:
    current_compliance = base_compliance + random.uniform(-5, 5)
    for i, periodo_str in enumerate(periodos_str):
        # Añadimos una ligera tendencia ascendente/descendente aleatoria y ruido
        compliance = current_compliance + random.uniform(-3, 3) + i * random.uniform(-0.5, 1.5)
        compliance = max(70, min(100, compliance)) # Aseguramos que esté entre 70 y 100
        data.append({'Tecnico': tecnico, 'Periodo': periodo_str, 'Cumplimiento (%)': round(compliance, 1)})
        current_compliance = compliance # La siguiente base es la actual

df = pd.DataFrame(data)

# Ordenamos por período para que el gráfico de línea tenga sentido
df['Periodo_dt'] = pd.to_datetime(df['Periodo'] + '-01') # Convertir a datetime para ordenar
df = df.sort_values(by='Periodo_dt')


# --- 2. Creación del Gráfico de Tendencia con Plotly ---
# Usamos plotly.express para una creación rápida y fácil.
# x='Periodo': Define el eje X con los períodos.
# y='Cumplimiento (%)': Define el eje Y con los porcentajes de cumplimiento.
# color='Tecnico': Asigna un color diferente a la línea de cada técnico.
# markers=True: Muestra marcadores en cada punto de datos.
# title: Título del gráfico.
# labels: Etiquetas personalizadas para los ejes y la leyenda.
fig = px.line(df,
              x='Periodo',
              y='Cumplimiento (%)',
              color='Tecnico',
              markers=True, # Muestra puntos en los datos
              title='Tendencia de Cumplimiento por Técnico y Período',
              labels={
                  'Periodo': 'Período (Año-Mes)',
                  'Cumplimiento (%)': 'Porcentaje de Cumplimiento (%)',
                  'Tecnico': 'Técnico'
              },
              template='plotly_white' # Un tema limpio para el gráfico
             )

# --- 3. Personalización Adicional (Opcional) ---
# Ajustar el rango del eje Y si es necesario
fig.update_yaxes(range=[min(70, df['Cumplimiento (%)'].min() - 5), 105]) # Rango Y desde un poco menos del mínimo hasta 105
fig.update_layout(
    hovermode="x unified", # Muestra información de todas las líneas al pasar el ratón sobre un punto del eje X
    xaxis_title='Período',
    yaxis_title='Cumplimiento (%)',
    legend_title_text='Técnicos'
)


# --- 4. Guardar como HTML ---
# Guardamos la figura como un archivo HTML interactivo.
# Puedes abrir este archivo en tu navegador.
html_file_path = 'tendencia_cumplimiento.html'
fig.write_html(html_file_path)

print(f"Gráfico guardado como '{html_file_path}'")

# Opcional: Mostrar el gráfico directamente si se ejecuta en un entorno compatible
# fig.show()

# Opcional: Generar el HTML como string para otros usos
# html_output = pio.to_html(fig, full_html=False, include_plotlyjs='cdn')
# print("\n--- HTML del Gráfico ---")
# print(html_output) # Esto se podría incrustar en una página web

