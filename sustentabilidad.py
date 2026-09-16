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
# ESTILOS CSS (Diseño institucional y formato de impresión)
# ---------------------------------------------------------
st.markdown(
    """
    <style>
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
        h1, h2, h3 {
            text-transform: uppercase;
            font-weight: 700 !important;
        }
        @media print {
            body { background-color: transparent; color: #000; }
            .stSidebar, button { display: none !important; }
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
# CARGA DE DATOS DESDE GITHUB RELEASES (Con caché)
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


with st.spinner("Cargando bases de datos catastrales desde la nube..."):
  df = cargar_datos()
  gdf = cargar_geojson()

st.success("¡Datos cargados correctamente!")

# ---------------------------------------------------------
# BUSCADOR Y FILTROS INTERACTIVOS
# ---------------------------------------------------------
st.markdown("---")
st.markdown("### 🔍 Buscador Catastral y Urbanístico")

# Creamos columnas para organizar los filtros de búsqueda
col1, col2 = st.columns([2, 1])

with col1:
  # Buscador general por texto (partida, nomenclatura, dirección, etc.)
  termino_busqueda = st.text_input(
      "Ingrese Nomenclatura, Partida o Calle a buscar:", ""
  )

with col2:
  # Opciones adicionales de filtrado rápido si el DataFrame tiene columnas clave
  # (Adaptable según los nombres de columnas de tu CSV)
  limite_resultados = st.selectbox(
      "Resultados máximos a mostrar", [10, 25, 50, 100], index=0
  )

# Lógica de filtrado dinámico
if termino_busqueda:
  # Filtramos buscando en todas las columnas de tipo texto del DataFrame
  mask = df.astype(str).apply(
      lambda x: x.str.contains(termino_busqueda, case=False, na=False)
  ).any(axis=1)
  df_filtrado = df[mask].head(limite_resultados)
else:
  df_filtrado = df.head(limite_resultados)

# ---------------------------------------------------------
# VISUALIZACIÓN DE RESULTADOS
# ---------------------------------------------------------
if not df_filtrado.empty:
  st.write(f"Se encontraron **{len(df_filtrado)}** registros coincidentes:")
  st.dataframe(df_filtrado, use_container_width=True)
else:
  st.warning(
      "No se encontraron registros que coincidan con la búsqueda ingresada."
  )

# Opción para ver la tabla completa colapsada
with st.expander("Ver tabla completa de datos cargados"):
  st.dataframe(df, use_container_width=True)
