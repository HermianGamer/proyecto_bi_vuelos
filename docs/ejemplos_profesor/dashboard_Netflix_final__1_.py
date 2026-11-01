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
            'DATABASE=NetflixDW;'
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

    dates = pd.date_range('2023-01-01', '2023-12-31', freq='D')
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

    titulos_pool = ['Stranger Things', 'The Crown', 'Wednesday', 'Squid Game',
                    'Money Heist', 'Ozark', 'Bridgerton', 'Dahmer', 'The Watcher', 'Emily in Paris']
    tipos_pool   = ['MOVIE', 'SHOW']
    generos_pool = ['Drama', 'Action', 'Comedy', 'Documentary', 'Thriller', 'Romance']
    paises_pool  = ['United States', 'United Kingdom', 'South Korea', 'Spain', 'India']
    horas_base   = {'MOVIE': 2_000_000, 'SHOW': 8_000_000}

    tipo_col   = np.random.choice(tipos_pool, n)
    titulo_col = np.random.choice(titulos_pool, n)
    horas_col  = [np.random.randint(horas_base[t], horas_base[t]*5) for t in tipo_col]

    sample_data = {
        'titulo':               titulo_col,
        'tipo':                 tipo_col,
        'genero':               np.random.choice(generos_pool, n),
        'pais':                 np.random.choice(paises_pool, n),
        'cantidad_vistas':      np.random.randint(10_000, 5_000_000, size=n),
        'tiempo_promedio_min':  np.random.uniform(20, 120, size=n).round(2),
        'monto_recaudado_usd':  np.random.uniform(0, 10_000_000, size=n).round(2),
        'fecha':                fechas,
        'anio':                 [2023] * n,
        'mes':                  meses,
        'nombre_mes':           [nombre_mes_map[m] for m in meses],
        'trimestre':            [(m - 1) // 3 + 1 for m in meses],
        'dia_semana':           [dia_map[d] for d in dias],
    }

    df_vistas = pd.DataFrame(sample_data)
    df_vistas['fecha'] = pd.to_datetime(df_vistas['fecha'])

    df_generos = df_vistas.groupby('genero').agg(
        cantidad_vistas=('cantidad_vistas', 'sum'),
        total_registros=('titulo', 'count')
    ).reset_index()

    df_titulos = df_vistas.groupby(['titulo', 'tipo']).agg(
        cantidad_vistas=('cantidad_vistas', 'sum'),
        monto_recaudado_usd=('monto_recaudado_usd', 'sum')
    ).reset_index()

    df_paises = df_vistas.groupby('pais').agg(
        cantidad_vistas=('cantidad_vistas', 'sum'),
        total_titulos=('titulo', 'nunique')
    ).reset_index()

    df_mensual = df_vistas.groupby(['anio', 'mes', 'nombre_mes']).agg(
        cantidad_vistas=('cantidad_vistas', 'sum'),
        total_registros=('titulo', 'count')
    ).reset_index().sort_values(['anio', 'mes'])

    print("✓ Datos de ejemplo generados")
    return df_vistas, df_generos, df_titulos, df_paises, df_mensual


def load_data():
    conn = get_datamart_connection()

    if conn is None:
        print(" No se pudo conectar a ninguna base de datos. Usando datos de ejemplo.")
        return create_sample_data()

    try:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT TOP 1 * FROM FactVistas")
            is_datamart = True
            print("✓ Conectado al Data Mart")
        except:
            is_datamart = False
            print("✓ Conectado a base de datos original")

        if is_datamart:
            df_vistas = pd.read_sql("""
                SELECT
                    dt.titulo, dt.anio_lanzamiento AS tipo,
                    dg.nombre AS genero,
                    dp.nombre AS pais,
                    fv.cantidad_vistas, fv.tiempo_promedio_min, fv.monto_recaudado_usd,
                    ti.fecha, ti.anio, ti.mes, ti.nombre_mes, ti.trimestre, ti.dia_semana
                FROM FactVistas fv
                JOIN DimTitulo  dt ON fv.titulo_id = dt.id
                JOIN DimGenero  dg ON fv.genero_id = dg.id
                JOIN DimPais    dp ON fv.pais_id   = dp.id
                JOIN DimTiempo  ti ON fv.tiempo_id = ti.id
            """, conn)

        df_vistas['fecha'] = pd.to_datetime(df_vistas['fecha'])

        df_generos = df_vistas.groupby('genero').agg(
            cantidad_vistas=('cantidad_vistas', 'sum'),
            total_registros=('titulo', 'count')
        ).reset_index()

        df_titulos = df_vistas.groupby(['titulo', 'tipo']).agg(
            cantidad_vistas=('cantidad_vistas', 'sum'),
            monto_recaudado_usd=('monto_recaudado_usd', 'sum')
        ).reset_index()

        df_paises = df_vistas.groupby('pais').agg(
            cantidad_vistas=('cantidad_vistas', 'sum'),
            total_titulos=('titulo', 'nunique')
        ).reset_index()

        df_mensual = df_vistas.groupby(['anio', 'mes', 'nombre_mes']).agg(
            cantidad_vistas=('cantidad_vistas', 'sum'),
            total_registros=('titulo', 'count')
        ).reset_index().sort_values(['anio', 'mes'])

        conn.close()
        print("✓ Datos cargados exitosamente")
        return df_vistas, df_generos, df_titulos, df_paises, df_mensual

    except Exception as e:
        print(f" Error cargando datos: {e}")
        if conn:
            conn.close()
        print(" Usando datos de ejemplo")
        return create_sample_data()


# ── Carga inicial ─────────────────────────────────────────────────────────────
print(" Iniciando carga de datos...")
df_aten, df_gen, df_tit, df_pais, df_mes = load_data()
df_aten['fecha'] = pd.to_datetime(df_aten['fecha'])

# ── App Dash ──────────────────────────────────────────────────────────────────
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div([
    html.Div([
        html.H1("🎬 Dashboard de Visualizaciones Netflix",
                style={'textAlign':'center','marginBottom':20,'color':'#2c3e50'}),
        html.P("Análisis integral de horas vistas, géneros, títulos y países",
               style={'textAlign':'center','color':'#7f8c8d','marginBottom':40})
    ]),

    # Filtros
    html.Div([
        html.Div([
            html.Label("Tipo de contenido:", style={'fontWeight':'bold'}),
            dcc.Dropdown(
                id='tipo-filter',
                options=[{'label':'Todos','value':'all'}] +
                        [{'label':t,'value':t} for t in sorted(df_aten['tipo'].unique())],
                value='all', clearable=False
            )
        ], style={'width':'24%','display':'inline-block','marginRight':'1%'}),

        html.Div([
            html.Label("Seleccionar País:", style={'fontWeight':'bold'}),
            dcc.Dropdown(
                id='pais-filter',
                options=[{'label':'Todos','value':'all'}] +
                        [{'label':p,'value':p} for p in sorted(df_aten['pais'].unique())],
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
            html.P("Total Registros", style={'color':'#7f8c8d','margin':'0'})
        ], style={'textAlign':'center','padding':'20px','backgroundColor':'white',
                  'borderRadius':'10px','boxShadow':'0 2px 4px rgba(0,0,0,0.1)'}),
        html.Div([
            html.H3(f"{df_aten['cantidad_vistas'].sum()/1_000_000:,.1f}M", style={'color':'#27ae60','margin':'0'}),
            html.P("Vistas Totales", style={'color':'#7f8c8d','margin':'0'})
        ], style={'textAlign':'center','padding':'20px','backgroundColor':'white',
                  'borderRadius':'10px','boxShadow':'0 2px 4px rgba(0,0,0,0.1)'}),
        html.Div([
            html.H3(f"{df_aten['titulo'].nunique()}", style={'color':'#3498db','margin':'0'}),
            html.P("Títulos Únicos", style={'color':'#7f8c8d','margin':'0'})
        ], style={'textAlign':'center','padding':'20px','backgroundColor':'white',
                  'borderRadius':'10px','boxShadow':'0 2px 4px rgba(0,0,0,0.1)'}),
        html.Div([
            html.H3(f"${df_aten['monto_recaudado_usd'].sum()/1_000_000:,.1f}M", style={'color':'#f39c12','margin':'0'}),
            html.P("Recaudación Total USD", style={'color':'#7f8c8d','margin':'0'})
        ], style={'textAlign':'center','padding':'20px','backgroundColor':'white',
                  'borderRadius':'10px','boxShadow':'0 2px 4px rgba(0,0,0,0.1)'})
    ], style={'display':'grid','gridTemplateColumns':'repeat(4, 1fr)','gap':'15px','marginBottom':'20px'}),

    # Gráficos fila 1
    html.Div([
        html.Div([dcc.Graph(id='genero-chart')],
                 style={'width':'48%','display':'inline-block'}),
        html.Div([dcc.Graph(id='titulos-chart')],
                 style={'width':'48%','float':'right','display':'inline-block'})
    ]),

    # Gráficos fila 2
    html.Div([
        html.Div([dcc.Graph(id='evolucion-chart')],
                 style={'width':'65%','display':'inline-block'}),
        html.Div([dcc.Graph(id='paises-chart')],
                 style={'width':'34%','float':'right','display':'inline-block'})
    ], style={'marginTop':'20px'}),

    # Nota
    html.Div([
        html.Div([
            html.H4(" Información del Sistema", style={'color':'#2c3e50'}),
            html.P("Este dashboard muestra análisis de visualizaciones de Netflix."),
            html.P("Si ves datos de ejemplo, verifica la conexión a la base de datos.",
                   style={'color':'#e74c3c','fontWeight':'bold'})
        ], style={'backgroundColor':'#ecf0f1','padding':'15px','borderRadius':'10px','marginTop':'20px'})
    ])
])


@app.callback(
    [Output('genero-chart','figure'),
     Output('titulos-chart','figure'),
     Output('evolucion-chart','figure'),
     Output('paises-chart','figure')],
    [Input('tipo-filter','value'),
     Input('pais-filter','value'),
     Input('date-range','start_date'),
     Input('date-range','end_date'),
     Input('chart-type','value')]
)
def update_charts(tipo_selected, pais_selected, start_date, end_date, chart_type):
    filtered_df = df_aten.copy()

    if tipo_selected != 'all':
        filtered_df = filtered_df[filtered_df['tipo'] == tipo_selected]
    if pais_selected != 'all':
        filtered_df = filtered_df[filtered_df['pais'] == pais_selected]
    if start_date and end_date:
        filtered_df = filtered_df[
            (filtered_df['fecha'] >= pd.to_datetime(start_date)) &
            (filtered_df['fecha'] <= pd.to_datetime(end_date))
        ]

    # 1. Géneros
    genero_data = filtered_df.groupby('genero').agg(
        cantidad_vistas=('cantidad_vistas','sum')
    ).reset_index()
    fig_genero = px.pie(
        genero_data, values='cantidad_vistas', names='genero',
        title='Distribución de Vistas por Género',
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    fig_genero.update_traces(textposition='inside', textinfo='percent+label')

    # 2. Top títulos
    titulos_data = filtered_df.groupby('titulo').agg(
        cantidad_vistas=('cantidad_vistas','sum'),
        monto_recaudado_usd=('monto_recaudado_usd','sum')
    ).reset_index().nlargest(10,'cantidad_vistas')

    if chart_type == 'bar':
        fig_titulos = px.bar(titulos_data, x='cantidad_vistas', y='titulo',
                             orientation='h', title='Top 10 Títulos por Cantidad de Vistas',
                             color='cantidad_vistas', color_continuous_scale='Reds')
    elif chart_type == 'line':
        fig_titulos = px.line(titulos_data, x='titulo', y='cantidad_vistas',
                              title='Top 10 Títulos por Cantidad de Vistas', markers=True)
    else:
        fig_titulos = px.area(titulos_data, x='titulo', y='cantidad_vistas',
                              title='Top 10 Títulos por Cantidad de Vistas')
    fig_titulos.update_layout(yaxis={'categoryorder':'total ascending'})

    # 3. Evolución temporal
    temporal_data = filtered_df.groupby('fecha').agg(
        cantidad_vistas=('cantidad_vistas','sum'),
        titulo=('titulo','count')
    ).reset_index().sort_values('fecha')

    fig_evolucion = make_subplots(specs=[[{"secondary_y": True}]])
    fig_evolucion.add_trace(
        go.Scatter(x=temporal_data['fecha'], y=temporal_data['cantidad_vistas'],
                   name="Vistas", line=dict(color='#e74c3c', width=3)),
        secondary_y=False)
    fig_evolucion.add_trace(
        go.Bar(x=temporal_data['fecha'], y=temporal_data['titulo'],
               name="Registros", opacity=0.3, marker_color='#3498db'),
        secondary_y=True)
    fig_evolucion.update_layout(title_text="Evolución de Vistas",
                                xaxis_title="Fecha")
    fig_evolucion.update_yaxes(title_text="Cantidad de Vistas", secondary_y=False)
    fig_evolucion.update_yaxes(title_text="Número de Registros", secondary_y=True)

    # 4. Países
    pais_data = filtered_df.groupby('pais').agg(
        cantidad_vistas=('cantidad_vistas','sum'),
        titulos=('titulo','nunique')
    ).reset_index().nlargest(8,'cantidad_vistas')

    fig_paises = px.scatter(
        pais_data, x='titulos', y='cantidad_vistas',
        size='cantidad_vistas', color='pais', hover_name='pais',
        title='Vistas por País de Producción', size_max=40,
        labels={'titulos':'Títulos Únicos','cantidad_vistas':'Cantidad de Vistas'}
    )

    return fig_genero, fig_titulos, fig_evolucion, fig_paises


if __name__ == '__main__':
    print(" Iniciando servidor Dash...")
    print(" Accede al dashboard en: http://localhost:8050")
    app.run(debug=True, port=8050)
