import geopandas as gpd
import pandas as pd
import streamlit as st

# Configuración inicial de la página
st.set_page_config(
    page_title="Certificación Urbanística - La Plata",
    page_icon="🏗️",
    layout="wide",
)

# ---------------------------------------------------------
# ESTILOS CSS (Diseño limpio, profesional y reglas de PDF)
# ---------------------------------------------------------
st.markdown(
    """
    <style>
        /* Encabezado institucional */
        .header-container {
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }
        .header-title {
            font-size: 1.2rem;
            font-weight: bold;
            color: #222;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        /* Títulos en negrita y mayúsculas */
        h1, h2, h3 {
            text-transform: uppercase;
            font-weight: 700 !important;
        }

        /* Reglas estrictas para exportación limpia a PDF / Impresión */
        @media print {
            body {
                background-color: transparent;
                color: #000;
            }
            .stSidebar, button, .css-1dp5vir {
                display: none !important;
            }
            .block-container {
                padding: 0 !important;
                margin: 0 !important;
            }
        }
    </style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# ENCABEZADO INSTITUCIONAL
# ---------------------------------------------------------
st.markdown(
    """
    <div class="header-container">
        <div class="header-title">COMISIÓN DE SUSTENTABILIDAD - CAUBAUNO</div>
    </div>
""",
    unsafe_allow_html=True,
)

st.markdown("<h1>Certificación Técnica Urbanística</h1>", unsafe_allow_html=True)
st.markdown(
    "<p>Herramienta de consulta catastral, zonificación y directrices"
    " bioclimáticas para el Partido de La Plata.</p>",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# CARGA DE DATOS DESDE GITHUB RELEASES (Con caché de Streamlit)
# ---------------------------------------------------------
@st.cache_data
def cargar_datos():
  url_csv = "https://github.com/smatiasflores-hue/ctu-sustentabilidad2026/releases/download/v1.0/datos.csv"
  df = pd.read_csv(
      url_csv,
      sep=";",
      encoding="latin-1",
      low_memory=False,
      on_bad_lines="skip",
  )
  return df


@st.cache_data
def cargar_geojson():
  url_geojson = "https://github.com/smatiasflores-hue/ctu-sustentabilidad2026/releases/download/v1.0/lotes.geojson"
  return gpd.read_file(url_geojson)


# Indicador de carga amigable en pantalla
with st.spinner(
    "Cargando bases de datos catastrales y geoespaciales desde la nube..."
):
  df = cargar_datos()
  gdf = cargar_geojson()

st.success("¡Datos cargados correctamente!")

# ---------------------------------------------------------
# A PARTIR DE AQUÍ PUEDES AGREGAR EL RESTO DE TU LÓGICA DE FILTROS Y MAPA
# ---------------------------------------------------------
# Ejemplo básico para verificar que el DataFrame responde:
if st.checkbox("Mostrar vista previa de los datos"):
  st.dataframe(df.head())
