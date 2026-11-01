# -*- coding: utf-8 -*-
"""
Dashboard de Atenciones Veterinarias
"""
import dash
from dash import dcc, html, Input, Output, callback
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pyodbc
import pandas as pd
import datetime
import warnings
import numpy as np

warnings.filterwarnings('ignore')

def get_datamart_connection():
    try:
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost;'
            'DATABASE=VeterinariaDataMart;'
            'UID=sa;'
            'PWD=1234567890',
            timeout=30
        )
        print("✓ Conexión a la base de datos exitosa")
        return conn
    except pyodbc.Error as e:
        print(f" Error de conexión: {e}")



def create_sample_data():
    """Crear datos de ejemplo para demostración"""
    print(" Generando datos de ejemplo...")

    np.random.seed(42)
    n = 500  # variable única — todos los arrays usan este valor

    dates = pd.date_range('2024-01-01', '2024-12-31', freq='D')
    fechas = np.random.choice(dates, n)
    meses  = pd.DatetimeIndex(fechas).month
    dias   = pd.DatetimeIndex(fechas).day_name()

    nombre_mes_map = {
        1:'Enero', 2:'Febrero', 3:'Marzo', 4:'Abril', 5:'Mayo', 6:'Junio',
        7:'Julio', 8:'Agosto', 9:'Septiembre', 10:'Octubre', 11:'Noviembre', 12:'Diciembre'
    }
    dia_map = {
        'Monday':'Lunes', 'Tuesday':'Martes', 'Wednesday':'Miércoles',
        'Thursday':'Jueves', 'Friday':'Viernes', 'Saturday':'Sábado', 'Sunday':'Domingo'
    }

    servicios    = ['Consulta', 'Vacunación', 'Cirugía', 'Desparasitación', 'Urgencia']
    precios_map  = {'Consulta':50, 'Vacunación':30, 'Cirugía':200, 'Desparasitación':25, 'Urgencia':100}
    servicio_col = np.random.choice(servicios, n)
    precio_col   = [precios_map[s] for s in servicio_col]

    sample_data = {
        'mascota':         np.random.choice(['Max','Luna','Bella','Rocky','Charlie'], n),
        'especie':         np.random.choice(['Perro','Gato','Conejo'], n),
        'raza':            np.random.choice(['Labrador','Siamés','Bulldog','Persa','Holandés'], n),
        'veterinario':     np.random.choice(['Dr. García','Dra. Martínez','Dr. López','Dra. Rodríguez'], n),
        'especialidad':    np.random.choice(['Cirugía','Dermatología','Cardiología','Oftalmología'], n),
        'servicio':        servicio_col,
        'precio_unitario': precio_col,
        'cantidad':        np.ones(n, dtype=int),
        'monto_total':     precio_col,
        'fecha':           fechas,
        'anio':            [2024] * n,
        'mes':             meses,
        'nombre_mes':      [nombre_mes_map[m] for m in meses],
        'trimestre':       [(m - 1) // 3 + 1 for m in meses],
        'dia_semana':      [dia_map[d] for d in dias],
    }

    df_atenciones = pd.DataFrame(sample_data)
    df_atenciones['fecha'] = pd.to_datetime(df_atenciones['fecha'])

    df_especies = df_atenciones.groupby('especie').agg(
        ingresos_totales=('monto_total','sum'),
        promedio_por_atencion=('monto_total','mean'),
        total_atenciones=('mascota','count')
    ).reset_index()

    df_veterinarios = df_atenciones.groupby(['veterinario','especialidad']).agg(
        ingresos_generados=('monto_total','sum'),
        total_atenciones=('mascota','count')
    ).reset_index()

    df_servicios = df_atenciones.groupby(['servicio','precio_unitario']).agg(
        total_veces_solicitado=('cantidad','sum'),
        ingresos_totales=('monto_total','sum')
    ).reset_index()

    df_mensual = df_atenciones.groupby(['anio','mes','nombre_mes']).agg(
        ingresos_mensuales=('monto_total','sum'),
        total_atenciones=('mascota','count')
    ).reset_index().sort_values(['anio','mes'])

    print("✓ Datos de ejemplo generados")
    return df_atenciones, df_especies, df_veterinarios, df_servicios, df_mensual


def load_data():
    conn = get_datamart_connection()

    if conn is None:
        print(" No se pudo conectar a ninguna base de datos. Usando datos de ejemplo.")
        return create_sample_data()

    try:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT TOP 1 * FROM FactAtenciones")
            is_datamart = True
            print("✓ Conectado al Data Mart")
        except:
            is_datamart = False
            print("✓ Conectado a base de datos original")

        if is_datamart:
            df_atenciones = pd.read_sql("""
                SELECT
                    m.nombre AS mascota, m.especie, m.raza,
                    v.nombre AS veterinario, v.especialidad,
                    s.nombre AS servicio, s.precio_unitario,
                    fa.cantidad, fa.monto_total,
                    t.fecha, t.anio, t.mes, t.nombre_mes, t.trimestre, t.dia_semana
                FROM FactAtenciones fa
                JOIN DimMascota m    ON fa.mascota_id    = m.id
                JOIN DimVeterinario v ON fa.veterinario_id = v.id
                JOIN DimServicio s   ON fa.servicio_id   = s.id
                JOIN DimTiempo t     ON fa.tiempo_id     = t.id
            """, conn)


        df_atenciones['fecha'] = pd.to_datetime(df_atenciones['fecha'])

        df_especies = df_atenciones.groupby('especie').agg(
            ingresos_totales=('monto_total','sum'),
            promedio_por_atencion=('monto_total','mean'),
            total_atenciones=('mascota','count')
        ).reset_index()

        df_veterinarios = df_atenciones.groupby(['veterinario','especialidad']).agg(
            ingresos_generados=('monto_total','sum'),
            total_atenciones=('mascota','count')
        ).reset_index()

        df_servicios = df_atenciones.groupby(['servicio','precio_unitario']).agg(
            total_veces_solicitado=('cantidad','sum'),
            ingresos_totales=('monto_total','sum')
        ).reset_index()

        df_mensual = df_atenciones.groupby(['anio','mes','nombre_mes']).agg(
            ingresos_mensuales=('monto_total','sum'),
            total_atenciones=('mascota','count')
        ).reset_index().sort_values(['anio','mes'])

        conn.close()
        print("✓ Datos cargados exitosamente")
        return df_atenciones, df_especies, df_veterinarios, df_servicios, df_mensual

    except Exception as e:
        print(f" Error cargando datos: {e}")
        if conn:
            conn.close()
        print(" Usando datos de ejemplo")
        return create_sample_data()


# ── Carga inicial ─────────────────────────────────────────────────────────────
print(" Iniciando carga de datos...")
df_aten, df_esp, df_vet, df_serv, df_mes = load_data()
df_aten['fecha'] = pd.to_datetime(df_aten['fecha'])

# ── App Dash ──────────────────────────────────────────────────────────────────
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div([
    html.Div([
        html.H1("🐾 Dashboard de Atenciones Veterinarias",
                style={'textAlign':'center','marginBottom':20,'color':'#2c3e50'}),
        html.P("Análisis integral de atenciones, servicios y rendimiento",
               style={'textAlign':'center','color':'#7f8c8d','marginBottom':40})
    ]),

    # Filtros
    html.Div([
        html.Div([
            html.Label("Seleccionar Especie:", style={'fontWeight':'bold'}),
            dcc.Dropdown(
                id='especie-filter',
                options=[{'label':'Todas','value':'all'}] +
                        [{'label':e,'value':e} for e in sorted(df_aten['especie'].unique())],
                value='all', clearable=False
            )
        ], style={'width':'24%','display':'inline-block','marginRight':'1%'}),

        html.Div([
            html.Label("Seleccionar Veterinario:", style={'fontWeight':'bold'}),
            dcc.Dropdown(
                id='veterinario-filter',
                options=[{'label':'Todos','value':'all'}] +
                        [{'label':v,'value':v} for v in sorted(df_aten['veterinario'].unique())],
                value='all', clearable=False
            )
        ], style={'width':'24%','display':'inline-block','marginRight':'1%'}),

        html.Div([
            html.Label("Rango de Fechas:", style={'fontWeight':'bold'}),
            dcc.DatePickerRange(
                id='date-range',
                start_date=df_aten['fecha'].min(),
                end_date=df_aten['fecha'].max(),
                display_format='YYYY-MM-DD'
            )
        ], style={'width':'24%','display':'inline-block','marginRight':'1%'}),

        html.Div([
            html.Label("Tipo de Gráfico:", style={'fontWeight':'bold'}),
            dcc.RadioItems(
                id='chart-type',
                options=[
                    {'label':'Barras','value':'bar'},
                    {'label':'Líneas','value':'line'},
                    {'label':'Área','value':'area'}
                ],
                value='bar', inline=True
            )
        ], style={'width':'24%','display':'inline-block'})
    ], style={'backgroundColor':'#f8f9fa','padding':'15px','borderRadius':'10px','marginBottom':'20px'}),

    # Métricas
    html.Div([
        html.Div([
            html.H3(f"{len(df_aten):,}", style={'color':'#e74c3c','margin':'0'}),
            html.P("Total Atenciones", style={'color':'#7f8c8d','margin':'0'})
        ], style={'textAlign':'center','padding':'20px','backgroundColor':'white',
                  'borderRadius':'10px','boxShadow':'0 2px 4px rgba(0,0,0,0.1)'}),
        html.Div([
            html.H3(f"${df_aten['monto_total'].sum():,.2f}", style={'color':'#27ae60','margin':'0'}),
            html.P("Ingresos Totales", style={'color':'#7f8c8d','margin':'0'})
        ], style={'textAlign':'center','padding':'20px','backgroundColor':'white',
                  'borderRadius':'10px','boxShadow':'0 2px 4px rgba(0,0,0,0.1)'}),
        html.Div([
            html.H3(f"{df_aten['mascota'].nunique()}", style={'color':'#3498db','margin':'0'}),
            html.P("Mascotas Únicas", style={'color':'#7f8c8d','margin':'0'})
        ], style={'textAlign':'center','padding':'20px','backgroundColor':'white',
                  'borderRadius':'10px','boxShadow':'0 2px 4px rgba(0,0,0,0.1)'}),
        html.Div([
            html.H3(f"${df_aten['monto_total'].mean():.2f}", style={'color':'#f39c12','margin':'0'}),
            html.P("Ticket Promedio", style={'color':'#7f8c8d','margin':'0'})
        ], style={'textAlign':'center','padding':'20px','backgroundColor':'white',
                  'borderRadius':'10px','boxShadow':'0 2px 4px rgba(0,0,0,0.1)'})
    ], style={'display':'grid','gridTemplateColumns':'repeat(4, 1fr)','gap':'15px','marginBottom':'20px'}),

    # Gráficos fila 1
    html.Div([
        html.Div([dcc.Graph(id='especies-chart')],
                 style={'width':'48%','display':'inline-block'}),
        html.Div([dcc.Graph(id='servicios-chart')],
                 style={'width':'48%','float':'right','display':'inline-block'})
    ]),

    # Gráficos fila 2
    html.Div([
        html.Div([dcc.Graph(id='evolucion-chart')],
                 style={'width':'65%','display':'inline-block'}),
        html.Div([dcc.Graph(id='veterinarios-chart')],
                 style={'width':'34%','float':'right','display':'inline-block'})
    ], style={'marginTop':'20px'}),

    # Nota
    html.Div([
        html.Div([
            html.H4(" Información del Sistema", style={'color':'#2c3e50'}),
            html.P("Este dashboard muestra análisis de atenciones veterinarias."),
            html.P("Si ves datos de ejemplo, verifica la conexión a la base de datos.",
                   style={'color':'#e74c3c','fontWeight':'bold'})
        ], style={'backgroundColor':'#ecf0f1','padding':'15px','borderRadius':'10px','marginTop':'20px'})
    ])
])


@app.callback(
    [Output('especies-chart','figure'),
     Output('servicios-chart','figure'),
     Output('evolucion-chart','figure'),
     Output('veterinarios-chart','figure')],
    [Input('especie-filter','value'),
     Input('veterinario-filter','value'),
     Input('date-range','start_date'),
     Input('date-range','end_date'),
     Input('chart-type','value')]
)
def update_charts(especie_selected, veterinario_selected, start_date, end_date, chart_type):
    filtered_df = df_aten.copy()

    if especie_selected != 'all':
        filtered_df = filtered_df[filtered_df['especie'] == especie_selected]
    if veterinario_selected != 'all':
        filtered_df = filtered_df[filtered_df['veterinario'] == veterinario_selected]
    if start_date and end_date:
        filtered_df = filtered_df[
            (filtered_df['fecha'] >= pd.to_datetime(start_date)) &
            (filtered_df['fecha'] <= pd.to_datetime(end_date))
        ]

    # 1. Especies
    especies_data = filtered_df.groupby('especie').agg(
        monto_total=('monto_total','sum')
    ).reset_index()
    fig_especies = px.pie(
        especies_data, values='monto_total', names='especie',
        title='Distribución de Ingresos por Especie',
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    fig_especies.update_traces(textposition='inside', textinfo='percent+label')

    # 2. Servicios
    servicios_data = filtered_df.groupby('servicio').agg(
        monto_total=('monto_total','sum'),
        cantidad=('cantidad','sum')
    ).reset_index().nlargest(10,'monto_total')

    if chart_type == 'bar':
        fig_servicios = px.bar(servicios_data, x='monto_total', y='servicio',
                               orientation='h', title='Top 10 Servicios por Ingresos',
                               color='monto_total', color_continuous_scale='Viridis')
    elif chart_type == 'line':
        fig_servicios = px.line(servicios_data, x='servicio', y='monto_total',
                                title='Top 10 Servicios por Ingresos', markers=True)
    else:
        fig_servicios = px.area(servicios_data, x='servicio', y='monto_total',
                                title='Top 10 Servicios por Ingresos')
    fig_servicios.update_layout(yaxis={'categoryorder':'total ascending'})

    # 3. Evolución temporal
    temporal_data = filtered_df.groupby('fecha').agg(
        monto_total=('monto_total','sum'),
        mascota=('mascota','count')
    ).reset_index().sort_values('fecha')

    fig_evolucion = make_subplots(specs=[[{"secondary_y": True}]])
    fig_evolucion.add_trace(
        go.Scatter(x=temporal_data['fecha'], y=temporal_data['monto_total'],
                   name="Ingresos", line=dict(color='#e74c3c', width=3)),
        secondary_y=False)
    fig_evolucion.add_trace(
        go.Bar(x=temporal_data['fecha'], y=temporal_data['mascota'],
               name="Atenciones", opacity=0.3, marker_color='#3498db'),
        secondary_y=True)
    fig_evolucion.update_layout(title_text="Evolución de Ingresos y Atenciones",
                                xaxis_title="Fecha")
    fig_evolucion.update_yaxes(title_text="Ingresos ($)", secondary_y=False)
    fig_evolucion.update_yaxes(title_text="Número de Atenciones", secondary_y=True)

    # 4. Veterinarios
    vet_data = filtered_df.groupby(['veterinario','especialidad']).agg(
        monto_total=('monto_total','sum'),
        mascota=('mascota','count')
    ).reset_index().nlargest(8,'monto_total')

    fig_veterinarios = px.scatter(
        vet_data, x='mascota', y='monto_total',
        size='monto_total', color='especialidad', hover_name='veterinario',
        title='Rendimiento de Veterinarios', size_max=40,
        labels={'mascota':'Número de Atenciones','monto_total':'Ingresos Generados ($)'}
    )

    return fig_especies, fig_servicios, fig_evolucion, fig_veterinarios


if __name__ == '__main__':
    print(" Iniciando servidor Dash...")
    print(" Accede al dashboard en: http://localhost:8050")
    app.run(debug=True, port=8050)
