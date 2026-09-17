from io import BytesIO
import re
from docx import Document
from docx.shared import Inches
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium
import folium

# Configuración de la página en modo ancho y reducción del padding superior
st.set_page_config(
    page_title="Certificado Técnico Urbanístico",
    page_icon="📄",
    layout="wide",
)

# Estilos CSS avanzados: Control de espacios y flujo natural para evitar hojas vacías
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.0rem !important;
            padding-bottom: 2rem !important;
        }
        html, body, [class*="css"] {
            font-family: 'Arial', Helvetica, sans-serif !important;
            color: #2c3e50;
        }
        h1 {
            font-size: 26px !important;
            font-weight: 800 !important;
            text-transform: uppercase !important;
            color: #0d3b66 !important;
            margin-top: -5px !important;
            margin-bottom: 2px !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 18px !important;
            font-weight: 700 !important;
            color: #1f77b4;
            white-space: normal !important;
            overflow: visible !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 12px !important;
            font-weight: 600 !important;
            color: #555555;
            white-space: normal !important;
            text-transform: uppercase;
        }
        h2 {
            font-size: 16px !important;
            font-weight: 700 !important;
            text-transform: uppercase;
            margin-top: 15px !important;
            margin-bottom: 6px !important;
            border-bottom: 2px solid #1f77b4;
            padding-bottom: 2px;
            color: #0d3b66;
            break-after: avoid;
        }
        h3 {
            font-size: 14px !important;
            font-weight: 700 !important;
            text-transform: uppercase;
            margin-top: 10px !important;
            margin-bottom: 4px !important;
            color: #333333;
        }
        p, li, span {
            font-size: 13px !important;
            font-weight: 400 !important;
            line-height: 1.3;
        }
        .contenido-sangria {
            margin-left: 15px;
        }
        iframe {
            width: 100% !important;
            height: 280px !important;
            max-height: 280px !important;
            border-radius: 4px;
        }
        @media print {
            .stSidebar { display: none !important; }
            header { display: none !important; }
            button { display: none !important; }
            .stButton { display: none !important; }
            .stSelectbox { display: none !important; }
            .stWarning { display: none !important; }
            [data-testid="stDataFrame"] { display: none !important; }
            body { background: white; color: black; }
            * { overflow: visible !important; text-overflow: unset !important; white-space: normal !important; }
            div { page-break-inside: avoid; }
            iframe { width: 100% !important; height: 280px !important; max-height: 280px !important; page-break-inside: avoid; }
        }
    </style>
""",
    unsafe_allow_html=True,
)


# Función para obtener la calle cercana mediante OpenStreetMap (Nominatim)
@st.cache_data(ttl=3600)
def obtener_calle_cercana(lat, lon):
  try:
    url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}"
    headers = {"User-Agent": "CertificadoTecnicoUrbanistico/1.0"}
    response = requests.get(url, headers=headers, timeout=3)
    if response.status_code == 200:
      data = response.json()
      address = data.get("address", {})
      calle = (
          address.get("road")
          or address.get("pedestrian")
          or address.get("suburb")
          or "Calle no identificada"
      )
      return calle
  except Exception:
    pass
  return "No disponible"


# Función auxiliar para extraer el número y letra de parcela desde un valor CCA
def extraer_parcela_de_cca(cca_str):
  try:
    segmento_par = cca_str[35:] if len(cca_str) >= 35 else cca_str
    match_par = re.search(r"(\d+)([A-Za-z]*)", segmento_par)
    if match_par:
      num_p = match_par.group(1).lstrip("0").rstrip("0")
      if not num_p:
        num_p = match_par.group(1).lstrip("0")
      letra_p = match_par.group(2).upper()
      return f"{num_p}{letra_p}" if letra_p else (num_p if num_p else "-")
  except Exception:
    pass
  return "-"


# Función para calcular la orientación cardinal relativa entre dos geometrías
def obtener_orientacion(geom_principal, geom_lindero):
  c_prin = geom_principal.centroid
  c_lind = geom_lindero.centroid
  dx = c_lind.x - c_prin.x
  dy = c_lind.y - c_prin.y

  dir_y = "Norte" if dy > 0 else "Sur"
  dir_x = "Este" if dx > 0 else "Oeste"

  if abs(dx) < 0.00001:
    return "Norte" if dy > 0 else "Sur"
  if abs(dy) < 0.00001:
    return "Este" if dx > 0 else "Oeste"

  if abs(dy) > abs(dx) * 2:
    return "Norte" if dy > 0 else "Sur"
  elif abs(dx) > abs(dy) * 2:
    return "Este" if dx > 0 else "Oeste"
  else:
    return f"{dir_y}-{dir_x}"


# Función para determinar si el lote es esquina o entre medianeras
def determinar_tipo_ubicacion(geom_parcela, linderos_vecinos):
  num_linderos = len(linderos_vecinos)
  if num_linderos <= 2:
    return "Esquina"
  else:
    return "Entre Medianeras"


# Función para extraer y ordenar los vértices de la parcela principal
def obtener_vertices_parcela(geom_parcela):
  try:
    geom_tipo = geom_parcela.geom_type
    if geom_tipo == "Polygon":
      coords = list(geom_parcela.exterior.coords)
    elif geom_tipo == "MultiPolygon":
      coords = list(geom_parcela.geoms[0].exterior.coords)
    else:
      return []
    if coords[0] == coords[-1]:
      coords = coords[:-1]
    return coords
  except Exception:
    return []


# Función avanzada: Genera el croquis con las medidas escritas en cada lado correspondiente
def generar_imagen_croquis_con_medidas(
    gdf_parcela, linderos_vecinos, medidas_lados
):
  fig, ax = plt.subplots(figsize=(4, 4))
  plt.box(False)
  ax.set_xticks([])
  ax.set_yticks([])

  if not linderos_vecinos.empty:
    linderos_vecinos.plot(
        ax=ax,
        facecolor="none",
        edgecolor="#555555",
        linewidth=0.7,
        linestyle="-",
    )
    col_id = (
        linderos_vecinos.columns[0]
        if "CCA" not in linderos_vecinos.columns
        else "CCA"
    )
    for _, row_l in linderos_vecinos.iterrows():
      cca_l = str(row_l.get(col_id, ""))
      parc_txt = extraer_parcela_de_cca(cca_l)
      if parc_txt and parc_txt != "-":
        centroid = row_l.geometry.centroid
        ax.text(
            centroid.x,
            centroid.y,
            parc_txt,
            fontsize=7,
            ha="center",
            va="center",
            color="#333333",
        )

  if not gdf_parcela.empty:
    gdf_parcela.plot(
        ax=ax, facecolor="none", edgecolor="#000000", linewidth=1.8
    )
    geom_prin = gdf_parcela.geometry.iloc[0]
    c_prin = geom_prin.centroid
    parc_prin = extraer_parcela_de_cca(
        str(gdf_parcela.iloc[0].get(gdf_parcela.columns[0], ""))
    )
    ax.text(
        c_prin.x,
        c_prin.y,
        parc_prin,
        fontsize=9,
        ha="center",
        va="center",
        color="#000000",
        weight="bold",
    )

    vertices = obtener_vertices_parcela(geom_prin)
    if vertices and len(medidas_lados) == len(vertices):
      num_v = len(vertices)
      for i in range(num_v):
        p1 = vertices[i]
        p2 = vertices[(i + 1) % num_v]

        mx = (p1[0] + p2[0]) / 2.0
        my = (p1[1] + p2[1]) / 2.0

        medida_texto = medidas_lados[i]
        if medida_texto and medida_texto.strip() != "":
          ax.text(
              mx,
              my,
              medida_texto.strip(),
              fontsize=8,
              ha="center",
              va="center",
              color="#000000",
              weight="bold",
              bbox=dict(
                  boxstyle="round,pad=0.1",
                  facecolor="white",
                  edgecolor="none",
                  alpha=0.8,
              ),
          )

    minx, miny, maxx, maxy = gdf_parcela.total_bounds
    margen_x = (maxx - minx) * 0.25 if maxx != minx else 0.0001
    margen_y = (maxy - miny) * 0.25 if maxy != miny else 0.0001
    ax.set_xlim(minx - margen_x, maxx + margen_x)
    ax.set_ylim(miny - margen_y, maxy + margen_y)

  plt.tight_layout()
  img_buffer = BytesIO()
  plt.savefig(
      img_buffer, format="png", dpi=300, bbox_inches="tight", transparent=True
  )
  plt.close(fig)
  img_buffer.seek(0)
  return img_buffer


# Función de Zonificación
def generar_imagen_zonificacion(
    gdf_parcela, linderos_vecinos, df_csv_datos, col_match
):
  fig, ax = plt.subplots(figsize=(4, 4))
  plt.box(False)
  ax.set_xticks([])
  ax.set_yticks([])

  if not linderos_vecinos.empty:
    linderos_vecinos.plot(
        ax=ax,
        facecolor="none",
        edgecolor="#555555",
        linewidth=0.7,
        linestyle="-",
    )
    for _, row_l in linderos_vecinos.iterrows():
      cca_l = str(row_l.get(col_match, "")) if col_match else ""
      match_csv = df_csv_datos[df_csv_datos["CCA"].astype(str) == cca_l]
      zona_txt = (
          str(match_csv.iloc[0].get("designacio", "N/D"))
          if not match_csv.empty
          else "N/D"
      )
      centroid = row_l.geometry.centroid
      zona_corto = zona_txt[:10] + "..." if len(zona_txt) > 10 else zona_txt
      ax.text(
          centroid.x,
          centroid.y,
          zona_corto,
          fontsize=6,
          ha="center",
          va="center",
          color="#333333",
          weight="bold",
      )

  if not gdf_parcela.empty:
    gdf_parcela.plot(
        ax=ax, facecolor="none", edgecolor="#000000", linewidth=2.0
    )
    c_prin = gdf_parcela.geometry.iloc[0].centroid
    match_prin = df_csv_datos[
        df_csv_datos["CCA"].astype(str)
        == str(gdf_parcela.iloc[0].get(col_match, ""))
    ]
    zona_prin = (
        str(match_prin.iloc[0].get("designacio", "N/D"))
        if not match_prin.empty
        else "N/D"
    )
    ax.text(
        c_prin.x,
        c_prin.y,
        zona_prin,
        fontsize=7,
        ha="center",
        va="center",
        color="#000000",
        weight="bold",
    )

    minx, miny, maxx, maxy = gdf_parcela.total_bounds
    margen_x = (maxx - minx) * 0.4 if maxx != minx else 0.0001
    margen_y = (maxy - miny) * 0.4 if maxy != miny else 0.0001
    ax.set_xlim(minx - margen_x, maxx + margen_x)
    ax.set_ylim(miny - margen_y, maxy + margen_y)

  plt.tight_layout()
  img_buffer = BytesIO()
  plt.savefig(
      img_buffer, format="png", dpi=300, bbox_inches="tight", transparent=True
  )
  plt.close(fig)
  img_buffer.seek(0)
  return img_buffer


# Función para generar el documento Word basado en la plantilla exacta
def generar_documento_word(contexto_datos):
  try:
    doc = Document("informe_sustentabilidad.docx")
  except Exception as e:
    doc = Document()
    doc.add_heading("Error: No se encontró informe_sustentabilidad.docx", 0)
    doc.add_paragraph(f"Detalle técnico: {e}")

  reemplazos = {
      "{{PART}}": str(contexto_datos.get("partido", "")),
      "{{PDA}}": str(contexto_datos.get("pda", "")),
      "{{Circ}}": str(contexto_datos.get("circunscripcion", "")),
      "{{Secc}}": str(contexto_datos.get("seccion", "")),
      "{{Manz}}": str(contexto_datos.get("manzana", "")),
      "{{PARC}}": str(contexto_datos.get("parcela", "")),
      "{{Inscripcion_Dominio}}": str(
          contexto_datos.get("inscripcion_dominio", "N/D")
      ),
      "{{CALL}}": str(contexto_datos.get("calle", "")),
      "{{ARA}}": str(contexto_datos.get("area", "")),
      "{{SUP}}": str(contexto_datos.get("superficie", "S/D")),
      "{{LOLI}}": str(contexto_datos.get("linderos_texto", "")),
      "{{PROP}}": str(contexto_datos.get("propietario", "No indicado")),
      "{{AGUA}}": str(contexto_datos.get("agua", "")),
      "{{GAS}}": str(contexto_datos.get("gas", "")),
      "{{CLOA}}": str(contexto_datos.get("cloaca", "")),
      "{{ELEC}}": str(contexto_datos.get("electricidad", "")),
      "{{ALUM}}": str(contexto_datos.get("alumbrado", "")),
      "{{PAV}}": str(contexto_datos.get("pavimento", "")),
      "{{ORDM}}": str(contexto_datos.get("ordenanza", "")),
      "{{ZONA}}": str(contexto_datos.get("zona", "")),
      "{{ud}}": str(contexto_datos.get("usos_admitidos", "")),
      "{{PROF}}": str(contexto_datos.get("profesional", "No indicado")),
  }

  for p in doc.paragraphs:
    for clave, valor in reemplazos.items():
      if clave in p.text:
        p.text = p.text.replace(clave, valor)

  img_croquis = contexto_datos.get("imagen_croquis", None)
  img_zonificacion = contexto_datos.get("imagen_zonificacion", None)

  for tabla in doc.tables:
    for fila in tabla.rows:
      for celda in fila.cells:
        if "{{MAPO}}" in celda.text and img_croquis is not None:
          celda.text = ""
          p = celda.paragraphs[0]
          run = p.add_run()
          run.add_picture(img_croquis, width=Inches(2.2))
        elif "{{MAZO}}" in celda.text and img_zonificacion is not None:
          celda.text = ""
          p = celda.paragraphs[0]
          run = p.add_run()
          run.add_picture(img_zonificacion, width=Inches(2.2))
        else:
          for clave, valor in reemplazos.items():
            if clave in celda.text:
              celda.text = celda.text.replace(clave, valor)

  buffer = BytesIO()
  doc.save(buffer)
  buffer.seek(0)
  return buffer


# Encabezado superior izquierdo compacto
st.markdown(
    "<p style='font-size:12px; font-weight:800; color:#333;"
    " text-transform:uppercase; letter-spacing:1px; margin-bottom:0px;'>COMISIÓN"
    " DE SUSTENTABILIDAD - <strong>CAUBAUNO</strong></p>",
    unsafe_allow_html=True,
)
st.title("CERTIFICADO TÉCNICO URBANÍSTICO - LA PLATA")
st.markdown(
    "<p style='font-size:12px; color:#666; margin-top:-2px; margin-bottom:8px;'>"
    "SISTEMA DE CONSULTA Y GESTIÓN DE PARCELAS (MÁS DE 400.000"
    " REGISTROS).</p>",
    unsafe_allow_html=True,
)


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


try:
  df = cargar_datos()

  if "busqueda_activa" not in st.session_state:
    st.session_state.busqueda_activa = False
  if "partida_buscada" not in st.session_state:
    st.session_state.partida_buscada = ""

  st.sidebar.header("🔍 Consulta por Partida")
  st.sidebar.markdown("**Estructura:** `055` + `[ 6 dígitos de Partida ]`")

  col1, col2 = st.sidebar.columns([1, 2])
  with col1:
    st.text_input("Partido", value="055", disabled=True)
  with col2:
    partida_input = st.text_input(
        "Nº Partida", max_chars=6, placeholder="Ej: 47562"
    )

  consultar = st.sidebar.button("Consultar Parcela")

  st.sidebar.markdown("---")
  st.sidebar.header("📋 Datos del Expediente")
  propietario_input = st.sidebar.text_input(
      "Propietario(s)", placeholder="Apellidos y Nombres"
  )
  profesional_input = st.sidebar.text_input(
      "Profesional a cargo", placeholder="Arquitecto / Maestro Mayor de Obras"
  )
  inscripcion_input = st.sidebar.text_input(
      "Inscripción al Dominio", placeholder="Matrícula / Folio / Año"
  )

  if consultar:
    if partida_input:
      st.session_state.busqueda_activa = True
      st.session_state.partida_buscada = partida_input
    else:
      st.sidebar.warning("Por favor ingrese un número de partida.")

  df_filtrado = pd.DataFrame()

  if st.session_state.busqueda_activa and st.session_state.partida_buscada:
    partida_limpia = st.session_state.partida_buscada.strip().zfill(6)
    pda_completo = f"055{partida_limpia}"

    df["PDA_limpio"] = (
        df["PDA"].astype(str).str.split(".").str[0].str.zfill(9)
    )
    df_filtrado = df[df["PDA_limpio"] == pda_completo]

    if not df_filtrado.empty:
      st.sidebar.success(
          f"¡Se encontraron {len(df_filtrado)} registro(s) para {pda_completo}!"
      )

      st.markdown('<div id="seccion-ficha"></div>', unsafe_allow_html=True)

      if len(df_filtrado) > 1:
        st.warning(
            f"⚠️ Se encontraron {len(df_filtrado)} registros coincidentes para"
            " esta partida. Seleccione cuál desea visualizar en la ficha:"
        )
        opciones = {
            f"Fila {idx} - CCA: {row.get('CCA', 'N/D')} (Zona: {row.get('designacio', 'N/D')})": idx
            for idx, row in df_filtrado.iterrows()
        }
        seleccion_str = st.selectbox(
            "Seleccionar registro a consultar:", list(opciones.keys())
        )
        indice_seleccionado = opciones[seleccion_str]
        row = df_filtrado.loc[indice_seleccionado]
      else:
        row = df_filtrado.iloc[0]

      cca_val = str(row.get("CCA", ""))
      partido_val = cca_val[0:3] if len(cca_val) >= 3 else "055"
      circunscripcion_val = cca_val[3:5] if len(cca_val) >= 5 else "-"

      seccion_val = "-"
      for char in cca_val[5:12]:
        if char.isalpha():
          seccion_val = char
          break
      if seccion_val == "-" and len(cca_val) >= 7:
        seccion_val = cca_val[6].strip("0" if cca_val[6] != "0" else "-")

      try:
        segmento_mza = cca_val[28:35] if len(cca_val) >= 35 else cca_val
        nums = re.findall(r"\d+", segmento_mza)
        if nums:
          candidatos = [n for n in nums if len(n) >= 3]
          val_bruto = candidatos[0] if candidatos else nums[0]
          manzana_val = val_bruto.lstrip("0").rstrip("0")
          if not manzana_val:
            manzana_val = val_bruto.lstrip("0")
        else:
          manzana_val = "N/D"
      except Exception:
        manzana_val = "N/D"

      parcela_val = extraer_parcela_de_cca(cca_val)

      df_cca_match = df[df["CCA"].astype(str) == cca_val]

      dec_ma_list = (
          df_cca_match["dec_ma"].dropna().astype(str).unique().tolist()
          if "dec_ma" in df.columns
          else [str(row.get("dec_ma", "N/D"))]
      )
      obs2_list = (
          df_cca_match["observacio_2"].dropna().astype(str).unique().tolist()
          if "observacio_2" in df.columns
          else [str(row.get("observacio_2", "N/D"))]
      )

      try:
        gdf_temp = cargar_geojson()
        col_m_temp = None
        for c in ["CCA", "cca", "PDA", "pda", "Partida"]:
          if c in gdf_temp.columns:
            col_m_temp = c
            break
        gdf_p_temp = gdf_temp[gdf_temp[col_m_temp].astype(str) == cca_val]
        geom_p_temp = gdf_p_temp.geometry.iloc[0] if not gdf_p_temp.empty else None
        vertices_temp = (
            obtener_vertices_parcela(geom_p_temp) if geom_p_temp else []
        )
        num_lados_detectados = len(vertices_temp) if vertices_temp else 4
      except Exception:
        num_lados_detectados = 4

      # ====================================================
      # 1. DATOS
      # ====================================================
      st.header("1. DATOS")

      with st.container():
        st.markdown('<div class="contenido-sangria">', unsafe_allow_html=True)

        col_mapa, col_datos = st.columns([1, 2], gap="large")

        calle_detectada = "Calculando..."
        linderos_vecinos = gpd.GeoDataFrame()
        gdf_parcela = gpd.GeoDataFrame()
        geom_principal = None
        orientacion_lm = "No determinada"
        tipo_ubicacion = "Entre Medianeras"
        linderos_texto_acumulado = ""
        col_match = None

        with col_mapa:
          st.subheader("Ubicación del Lote")
          try:
            gdf = cargar_geojson()
            for c in ["CCA", "cca", "PDA", "pda", "Partida"]:
              if c in gdf.columns:
                col_match = c
                break

            if col_match:
              gdf_parcela = gdf[gdf[col_match].astype(str) == cca_val]
              if not gdf_parcela.empty:
                if gdf_parcela.crs != "EPSG:4326":
                  gdf_parcela = gdf_parcela.to_crs("EPSG:4326")

                geom_principal = gdf_parcela.geometry.iloc[0]
                centroid = geom_principal.centroid
                lat, lon = centroid.y, centroid.x

                calle_detectada = obtener_calle_cercana(lat, lon)

                minx, miny, maxx, maxy = geom_principal.bounds
                if (centroid.x - minx) > (centroid.y - miny):
                  orientacion_lm = "Sudoeste (Frente a Calle)"
                else:
                  orientacion_lm = "Noroeste (Frente a Calle)"

                try:
                  linderos_cercanos = gdf[
                      gdf.geometry.intersects(geom_principal)
                  ]
                  linderos_vecinos = linderos_cercanos[
                      linderos_cercanos[col_match].astype(str) != cca_val
                  ]
                except Exception:
                  linderos_vecinos = gpd.GeoDataFrame()

                tipo_ubicacion = determinar_tipo_ubicacion(
                    geom_principal, linderos_vecinos
                )

                m = folium.Map(
                    location=[lat, lon],
                    zoom_start=19,
                    tiles="OpenStreetMap",
                    zoom_control=False,
                    dragging=False,
                    scrollWheelZoom=False,
                )

                if not linderos_vecinos.empty:
                  if linderos_vecinos.crs != "EPSG:4326":
                    linderos_vecinos = linderos_vecinos.to_crs("EPSG:4326")

                  folium.GeoJson(
                      linderos_vecinos,
                      style_function=lambda x: {
                          "fillColor": "#d3d3d3",
                          "color": "#808080",
                          "weight": 1,
                          "fillOpacity": 0.3,
                      },
                      tooltip="Lote Lindero",
                  ).add_to(m)

                  for _, row_l in linderos_vecinos.iterrows():
                    cca_l = str(row_l.get(col_match, ""))
                    parc_txt = extraer_parcela_de_cca(cca_l)
                    if parc_txt and parc_txt != "-":
                      c_l = row_l.geometry.centroid
                      folium.Marker(
                          location=[c_l.y, c_l.x],
                          icon=folium.DivIcon(
                              html=(
                                  f"<div style='font-size: 10px; font-weight:"
                                  f" bold; color: #444444; text-align: center;"
                                  f" text-shadow: 1px 1px 0px #ffffff;'>{parc_txt}</div>"
                              )
                          ),
                      ).add_to(m)

                folium.GeoJson(
                    gdf_parcela,
                    style_function=lambda x: {
                        "fillColor": "#1f77b4",
                        "color": "#0d3b66",
                        "weight": 2.5,
                        "fillOpacity": 0.7,
                    },
                    tooltip=(
                        f"Parcela Seleccionada | Calle: {calle_detectada} |"
                        f" Manzana: {manzana_val} | Parcela: {parcela_val}"
                    ),
                ).add_to(m)

                folium.Marker(
                    location=[centroid.y, centroid.x],
                    icon=folium.DivIcon(
                        html=(
                            f"<div style='font-size: 11px; font-weight: 800;"
                            f" color: #0d3b66; text-align: center; text-shadow:"
                            f" 1px 1px 0px #ffffff;'>{parcela_val}</div>"
                        )
                    ),
                ).add_to(m)

                st_folium(m, width=320, height=280)
                st.metric(label="Calle Referencia", value=calle_detectada)

              else:
                st.info(
                    "No se encontró un polígono geométrico asociado al CCA"
                    f" `{cca_val}`."
                )
            else:
              st.warning("El archivo `lotes.geojson` no posee columna de enlace.")
          except Exception as map_error:
            st.info(f"Cargue el archivo `lotes.geojson`. (Error: {map_error})")

          # Listado de Lotes Linderos
          st.markdown("<br>", unsafe_allow_html=True)
          st.subheader("Lotes Linderos")
          lista_linderos_str = []
          if not linderos_vecinos.empty and geom_principal is not None:
            for _, row_lindero in linderos_vecinos.iterrows():
              cca_lindero = str(row_lindero.get(col_match, ""))
              num_letra_parcela = extraer_parcela_de_cca(cca_lindero)
              if num_letra_parcela and num_letra_parcela != "-":
                geom_lindero = row_lindero.geometry
                orientacion = obtener_orientacion(geom_principal, geom_lindero)
                texto_lindero = (
                    f"Parcela {num_letra_parcela} (Al {orientacion})"
                )
                lista_linderos_str.append(texto_lindero)
                st.markdown(
                    f"<p style='margin: 0px 0px 4px 0px; font-size:12px;'"
                    f" color:#555;'>• {texto_lindero}</p>",
                    unsafe_allow_html=True,
                )
            linderos_texto_acumulado = "; ".join(lista_linderos_str)
          else:
            st.markdown(
                "<p style='font-size:12px; color:#666;'>No se detectaron lotes"
                " linderos cercanos.</p>",
                unsafe_allow_html=True,
            )

        with col_datos:
          st.subheader("a. Datos Catastrales")
          c_cat1, c_cat2, c_cat3 = st.columns(3)
          with c_cat1:
            st.metric(label="PDA", value=pda_completo)
            st.metric(label="Sección", value=seccion_val)
          with c_cat2:
            st.metric(label="Partido", value=partido_val)
            st.metric(label="Manzana", value=manzana_val)
          with c_cat3:
            st.metric(label="Circunscripción", value=circunscripcion_val)
            st.metric(label="Parcela", value=parcela_val)

          st.markdown("")

          st.subheader("b. Parámetros Urbanísticos")
          st.metric(
              label="Descripción del Área",
              value=str(row.get("descripcio", "N/D")),
          )
          st.metric(
              label="Descripción Secundaria",
              value=str(row.get("descripcio_2", "N/D")),
          )

          c_urb1, c_urb2, c_urb3, c_urb4 = st.columns(4)
          with c_urb1:
            st.metric(label="Zona", value=str(row.get("designacio", "N/D")))
          with c_urb2:
            st.metric(label="FOS", value=str(row.get("fos", "N/D")))
          with c_urb3:
            st.metric(label="FOT", value=str(row.get("fota", "N/D")))
          with c_urb4:
            st.metric(
                label="Altura Máx.", value=str(row.get("hmax", "N/D"))
            )

          st.subheader("c. Ordenanzas Territoriales")
          if dec_ma_list:
            for item in dec_ma_list:
              st.markdown(f"- {item}")
          else:
            st.markdown("- N/D")

          st.subheader("d. Ordenanzas Municipales")
          if obs2_list:
            for item in obs2_list:
              st.markdown(f"- {item}")
          else:
            st.markdown("- N/D")

          # ====================================================
          # INGRESO DINÁMICO DE MEDIDAS POR LADO (ARISTAS)
          # ====================================================
          st.subheader("📏 Carga de Medidas por Lado (Aristas)")
          st.markdown(
              f"<p style='font-size:12px; color:#555;'>Se detectaron"
              f" <b>{num_lados_detectados} lados</b> en el polígono. Ingrese"
              " las medidas para que aparezcan impresas:</p>",
              unsafe_allow_html=True,
          )

          medidas_ingresadas = []
          cols_medidas = st.columns(min(num_lados_detectados, 4))
          for i in range(num_lados_detectados):
            col_idx = i % 4
            with cols_medidas[col_idx]:
              val_m = st.text_input(
                  f"Lado {i+1}",
                  value="",
                  placeholder=f"Ej: {10+i*2}",
                  key=f"lado_{i}",
              )
              medidas_ingresadas.append(val_m)

          # ====================================================
          # VISTA PREVIA DE CONTROL (Segundo Mapa en Pantalla)
          # ====================================================
          st.markdown("<br>", unsafe_allow_html=True)
          st.subheader("👁️ Vista Previa de Control (Croquis con Medidas)")
          try:
            if not gdf_parcela.empty:
              img_prev = generar_imagen_croquis_con_medidas(
                  gdf_parcela, linderos_vecinos, medidas_ingresadas
              )
              st.image(
                  img_prev,
                  caption=(
                      "Vista previa exacta del croquis que se imprimirá en el"
                      " Word"
                  ),
                  width=350,
              )
          except Exception as prev_err:
            st.info(f"No se pudo generar la vista previa: {prev_err}")

          # Infraestructura
          st.subheader("f. Infraestructura y Servicios")
          c_inf_col1, c_inf_col2, c_inf_col3 = st.columns(3)
          with c_inf_col1:
            chk_agua = st.checkbox("Agua corriente", value=True)
            chk_gas = st.checkbox("Gas natural", value=True)
          with c_inf_col2:
            chk_cloaca = st.checkbox("Cloaca", value=True)
            chk_electricidad = st.checkbox("Electricidad", value=True)
          with c_inf_col3:
            chk_alumbrado = st.checkbox("Alumbrado público", value=True)
            chk_pavimento = st.checkbox("Pavimento", value=True)

        st.markdown("</div>", unsafe_allow_html=True)

      # ----------------------------------------------------
      # BOTÓN DE DESCARGA DE WORD OFICIAL (.DOCX)
      # ----------------------------------------------------
      st.markdown("---")
      st.subheader("📥 Generación de Documento Oficial")

      ordenanza_str = (
          " / ".join(obs2_list) if obs2_list else "Normativa general aplicable"
      )

      buffer_imagen_mapa = None
      buffer_imagen_zonificacion = None
      try:
        if not gdf_parcela.empty:
          buffer_imagen_mapa = generar_imagen_croquis_con_medidas(
              gdf_parcela, linderos_vecinos, medidas_ingresadas
          )
          buffer_imagen_zonificacion = generar_imagen_zonificacion(
              gdf_parcela, linderos_vecinos, df, col_match
          )
      except Exception:
        pass

      datos_para_docx = {
          "partido": partido_val,
          "pda": pda_completo,
          "circunscripcion": circunscripcion_val,
          "seccion": seccion_val,
          "manzana": manzana_val,
          "parcela": parcela_val,
          "inscripcion_dominio": (
              inscripcion_input if inscripcion_input else "S/D"
          ),
          "calle": calle_detectada,
          "area": str(row.get("descripcio", "N/D")),
          "superficie": "S/D (según título)",
          "linderos_texto": (
              linderos_texto_acumulado
              if linderos_texto_acumulado
              else "Sin linderos registrados"
          ),
          "propietario": (
              propietario_input if propietario_input else "No indicado"
          ),
          "profesional": (
              profesional_input if profesional_input else "No indicado"
          ),
          "agua": "SÍ" if chk_agua else "NO",
          "gas": "SÍ" if chk_gas else "NO",
          "cloaca": "SÍ" if chk_cloaca else "NO",
          "electricidad": "SÍ" if chk_electricidad else "NO",
          "alumbrado": "SÍ" if chk_alumbrado else "NO",
          "pavimento": "SÍ" if chk_pavimento else "NO",
          "ordenanza": ordenanza_str,
          "zona": str(row.get("designacio", "N/D")),
          "usos_admitidos": (
              "Usos residenciales, comerciales y de servicios compatibles"
              " según zonificación "
              + str(row.get("designacio", ""))
          ),
          "imagen_croquis": buffer_imagen_mapa,
          "imagen_zonificacion": buffer_imagen_zonificacion,
      }

      archivo_docx = generar_documento_word(datos_para_docx)

      col_v1, col_btn_dw, col_v2 = st.columns([1, 2, 1])
      with col_btn_dw:
        st.download_button(
            label="📄 Descargar Certificado en Word (.docx)",
            data=archivo_docx,
            file_name=f"Certificado_Urbanistico_{pda_completo}.docx",
            mime=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            use_container_width=True,
            type="primary",
        )

    else:
      st.sidebar.error("No se encontró ninguna parcela con ese número.")
  else:
    st.info(
        "👈 Ingrese los 6 dígitos de la Partida en la barra lateral y presione"
        ' "Consultar Parcela" para ver los datos de la parcela.'
    )

  if not df_filtrado.empty:
    st.dataframe(df_filtrado, use_container_width=True)

except Exception as e:
  st.error(
      f"Ocurrió un error al leer el archivo 'datos.csv'. Detalle técnico: {e}"
  )
