import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from branca.element import Element
from fastkml import kml
import zipfile

st.set_page_config(
    page_title="Módulo Ingeniería FTTH — Mapa + Presupuesto + Diseño",
    layout="wide"
)

# =========================
# FUNCIONES AUXILIARES — MÓDULO 1
# =========================

def calcular_presupuesto(dist_total_km,
                         pot_olt_dbm,
                         sens_ont_dbm,
                         atenuacion_db_km,
                         n_empalmes,
                         n_conectores,
                         perd_empalme_db,
                         perd_conector_db,
                         perd_splitter_nap_db,
                         perd_splitter_cto_db):
    """
    Calcula el presupuesto óptico y devuelve un dict con todos los resultados.
    """
    perd_fibra = dist_total_km * atenuacion_db_km
    perd_empalmes_total = n_empalmes * perd_empalme_db
    perd_conectores_total = n_conectores * perd_conector_db
    perd_splitters_total = perd_splitter_nap_db + perd_splitter_cto_db

    perd_total = perd_fibra + perd_empalmes_total + perd_conectores_total + perd_splitters_total
    pot_ont = pot_olt_dbm - perd_total
    margen = pot_ont - sens_ont_dbm

    # Clasificación del enlace
    if margen >= 3:
        estado = "OK"
        color = "green"
        comentario = "El enlace tiene buen margen de ingeniería."
    elif 0 <= margen < 3:
        estado = "AL LÍMITE"
        color = "orange"
        comentario = "El enlace está operativo pero con poco margen. Se recomienda revisar diseño."
    else:
        estado = "FUERA DE RANGO"
        color = "red"
        comentario = "El enlace no cumple con la sensibilidad de la ONT. Revisar diseño / pérdidas."

    return {
        "perd_fibra": perd_fibra,
        "perd_empalmes": perd_empalmes_total,
        "perd_conectores": perd_conectores_total,
        "perd_splitters": perd_splitters_total,
        "perd_total": perd_total,
        "pot_ont": pot_ont,
        "margen": margen,
        "estado": estado,
        "color": color,
        "comentario": comentario
    }


def crear_mapa_ftth(d_olt_nap, d_nap_cto, d_cto_ont):
    """
    Crea un mapa lógico horizontal OLT → NAP → CTO → ONT usando Plotly.
    Las distancias se expresan en km y se acumulan sobre el eje X.
    """
    x_olt = 0
    x_nap = d_olt_nap
    x_cto = d_olt_nap + d_nap_cto
    x_ont = d_olt_nap + d_nap_cto + d_cto_ont

    x_vals = [x_olt, x_nap, x_cto, x_ont]
    y_vals = [0, 0, 0, 0]
    labels = ["OLT", "NAP", "CTO", "ONT"]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=x_vals,
        y=y_vals,
        mode="lines+markers+text",
        text=labels,
        textposition="top center",
        marker=dict(size=14),
        line=dict(width=3)
    ))

    fig.add_annotation(
        x=(x_olt + x_nap) / 2,
        y=-0.05,
        text=f"{d_olt_nap:.2f} km",
        showarrow=False,
        font=dict(size=10)
    )
    fig.add_annotation(
        x=(x_nap + x_cto) / 2,
        y=-0.05,
        text=f"{d_nap_cto:.2f} km",
        showarrow=False,
        font=dict(size=10)
    )
    fig.add_annotation(
        x=(x_cto + x_ont) / 2,
        y=-0.05,
        text=f"{d_cto_ont:.2f} km",
        showarrow=False,
        font=dict(size=10)
    )

    fig.update_layout(
        title="Mapa lógico FTTH — OLT → NAP → CTO → ONT",
        xaxis_title="Distancia acumulada (km)",
        yaxis_visible=False,
        yaxis_showticklabels=False,
        margin=dict(l=20, r=20, t=50, b=20),
        height=350
    )

    return fig


# =========================
# FUNCIONES AUXILIARES — MÓDULO 2 (KMZ)
# =========================

def parsear_kmz_ftth(file_obj):
    """
    Parsea un KMZ con estructura:

    FTTH-DISEÑO/
      NODO
      CABLES_TRONCALES
      CABLES_DERIVACIONES
      CAJAS_HUB
      CAJAS_NAP

    Devuelve un dict con:
    {
      "nodo": [ {name, lat, lon}, ... ],
      "cables_troncales": [ [ [lat,lon], ... ], ... ],
      "cables_derivaciones": [ [ [lat,lon], ... ], ... ],
      "cajas_hub": [ {name, lat, lon}, ... ],
      "cajas_nap": [ {name, lat, lon}, ... ]
    }
    """
    data = {
        "nodo": [],
        "cables_troncales": [],
        "cables_derivaciones": [],
        "cajas_hub": [],
        "cajas_nap": []
    }

    # KMZ = ZIP → buscamos el primer .kml adentro
    with zipfile.ZipFile(file_obj) as zf:
        kml_name = None
        for info in zf.infolist():
            if info.filename.lower().endswith(".kml"):
                kml_name = info.filename
                break

        if kml_name is None:
            raise ValueError("El KMZ no contiene ningún archivo .kml")

        kml_bytes = zf.read(kml_name)

    # Parsear KML
    k_obj = kml.KML()
    k_obj.from_string(kml_bytes)

    from fastkml.kml import Folder, Placemark

    def walk_features(features, path=""):
        for f in features:
            fname = getattr(f, "name", "") or ""
            new_path = f"{path}/{fname}" if path else fname

            if isinstance(f, Folder):
                walk_features(f.features(), new_path)
            elif isinstance(f, Placemark):
                geom = f.geometry
                if geom is None:
                    continue

                path_upper = new_path.upper()

                # Puntos
                if geom.geom_type == "Point":
                    lon, lat = list(geom.coords)[0]  # (lon,lat)
                    punto = {
                        "name": fname,
                        "lat": lat,
                        "lon": lon
                    }
                    if "NODO" in path_upper:
                        data["nodo"].append(punto)
                    elif "CAJAS_HUB" in path_upper:
                        data["cajas_hub"].append(punto)
                    elif "CAJAS_NAP" in path_upper:
                        data["cajas_nap"].append(punto)

                # Líneas
                elif geom.geom_type in ("LineString", "MultiLineString"):
                    lineas = []
                    if geom.geom_type == "LineString":
                        lineas = [geom.coords]
                    else:
                        for g in geom.geoms:
                            lineas.append(g.coords)

                    for linea in lineas:
                        coords_latlon = [[lat, lon] for lon, lat in linea]
                        if "CABLES_TRONCALES" in path_upper:
                            data["cables_troncales"].append(coords_latlon)
                        elif "CABLES_DERIVACIONES" in path_upper:
                            data["cables_derivaciones"].append(coords_latlon)

    # Recorrer raíz
    for f in k_obj.features():
        walk_features(f.features(), f.name or "")

    return data


# =========================
# MÓDULO 1 — MAPA LÓGICO + PRESUPUESTO ÓPTICO
# =========================

st.title("Módulo Ingeniería FTTH — Mapa + Presupuesto Óptico + Diseño")

st.markdown(
    """
### Parte 1 — Mapa lógico + Presupuesto óptico

Esta primera sección integra:

- Un **mapa lógico FTTH** (OLT → NAP → CTO → ONT).
- El **presupuesto óptico completo** del enlace hasta el cliente.
"""
)

col_izq, col_der = st.columns([1.1, 1])

with col_izq:
    st.subheader("1. Configuración del enlace y mapa FTTH")

    st.markdown("#### Distancias por tramo (km)")
    c1, c2, c3 = st.columns(3)
    with c1:
        d_olt_nap = st.number_input("OLT → NAP", min_value=0.0, value=3.0, step=0.1)
    with c2:
        d_nap_cto = st.number_input("NAP → CTO", min_value=0.0, value=0.8, step=0.1)
    with c3:
        d_cto_ont = st.number_input("CTO → ONT", min_value=0.0, value=0.15, step=0.05)

    dist_total = d_olt_nap + d_nap_cto + d_cto_ont
    st.markdown(f"**Distancia total del enlace:** `{dist_total:.2f} km`")

    fig_mapa = crear_mapa_ftth(d_olt_nap, d_nap_cto, d_cto_ont)
    st.plotly_chart(fig_mapa, use_container_width=True)

    st.markdown("#### Resumen de tramos")
    df_tramos = pd.DataFrame({
        "Tramo": ["OLT → NAP", "NAP → CTO", "CTO → ONT"],
        "Distancia (km)": [d_olt_nap, d_nap_cto, d_cto_ont]
    })
    st.dataframe(df_tramos, use_container_width=True, hide_index=True)

with col_der:
    st.subheader("2. Presupuesto óptico del enlace")

    st.markdown("#### Parámetros generales")
    c1, c2 = st.columns(2)
    with c1:
        pot_olt_dbm = st.number_input("Potencia OLT (dBm)", value=3.0, step=0.5)
    with c2:
        sens_ont_dbm = st.number_input("Sensibilidad mínima ONT (dBm)", value=-27.0, step=0.5)

    st.markdown("#### Fibra óptica")
    c3, c4 = st.columns(2)
    with c3:
        atenuacion_db_km = st.number_input("Atenuación fibra (dB/km)", value=0.21, step=0.01)
    with c4:
        st.write("")

    st.markdown("#### Empalmes y conectores")
    c5, c6 = st.columns(2)
    with c5:
        n_empalmes = st.number_input("Cantidad de empalmes", min_value=0, value=8, step=1)
        n_conectores = st.number_input("Cantidad de conectores", min_value=0, value=6, step=1)
    with c6:
        perd_empalme_db = st.number_input("Pérdida por empalme (dB)", value=0.05, step=0.01)
        perd_conector_db = st.number_input("Pérdida por conector (dB)", value=0.25, step=0.01)

    st.markdown("#### Splitters (PON)")
    opciones_splitter = {
        "Sin splitter": 0.0,
        "1:2 (≈ 3,5 dB)": 3.5,
        "1:4 (≈ 7,2 dB)": 7.2,
        "1:8 (≈ 10,5 dB)": 10.5,
        "1:16 (≈ 13,5 dB)": 13.5,
        "1:32 (≈ 17 dB)": 17.0,
        "1:64 (≈ 20,5 dB)": 20.5
    }

    c7, c8 = st.columns(2)
    with c7:
        splitter_nap = st.selectbox("Splitter en NAP", list(opciones_splitter.keys()), index=2)
    with c8:
        splitter_cto = st.selectbox("Splitter en CTO", list(opciones_splitter.keys()), index=0)

    perd_splitter_nap_db = opciones_splitter[splitter_nap]
    perd_splitter_cto_db = opciones_splitter[splitter_cto]

    st.markdown("---")
    st.markdown("#### Resultados del presupuesto óptico")

    resultados = calcular_presupuesto(
        dist_total_km=dist_total,
        pot_olt_dbm=pot_olt_dbm,
        sens_ont_dbm=sens_ont_dbm,
        atenuacion_db_km=atenuacion_db_km,
        n_empalmes=n_empalmes,
        n_conectores=n_conectores,
        perd_empalme_db=perd_empalme_db,
        perd_conector_db=perd_conector_db,
        perd_splitter_nap_db=perd_splitter_nap_db,
        perd_splitter_cto_db=perd_splitter_cto_db
    )

    c9, c10 = st.columns(2)
    with c9:
        st.metric("Pérdida total (dB)", f"{resultados['perd_total']:.2f}")
        st.metric("Potencia estimada en ONT (dBm)", f"{resultados['pot_ont']:.2f}")
    with c10:
        st.metric("Margen disponible (dB)", f"{resultados['margen']:.2f}")
        st.markdown(
            f"<div style='padding:0.5rem 1rem; border-radius:8px; "
            f"background-color:{resultados['color']}; color:white; text-align:center; font-weight:bold;'>"
            f"ESTADO: {resultados['estado']}</div>",
            unsafe_allow_html=True
        )

    st.markdown("#### Detalle de pérdidas")
    df_perdidas = pd.DataFrame({
        "Concepto": [
            "Fibra",
            "Empalmes",
            "Conectores",
            "Splitters NAP",
            "Splitters CTO"
        ],
        "Pérdida (dB)": [
            resultados["perd_fibra"],
            resultados["perd_empalmes"],
            resultados["perd_conectores"],
            perd_splitter_nap_db,
            perd_splitter_cto_db
        ]
    })
    st.dataframe(df_perdidas, use_container_width=True, hide_index=True)

    st.info(resultados["comentario"])


# =========================
# MÓDULO 2 — VISUALIZACIÓN DE FTTH DESDE KMZ
# =========================

st.markdown("---")
st.header("Módulo 2 — Visualización de diseño FTTH desde archivo KMZ")

st.markdown(
    """
Subí un archivo **KMZ** con la siguiente estructura de carpetas:

`FTTH-DISEÑO/`
- `NODO`
- `CABLES_TRONCALES`
- `CABLES_DERIVACIONES`
- `CAJAS_HUB`
- `CAJAS_NAP`

El sistema dibuja automáticamente:

- NODO
- Cables troncales
- Cables de derivación
- Cajas HUB
- Cajas NAP
"""
)

# Estado para guardar el último diseño cargado
if "kmz_data" not in st.session_state:
    st.session_state.kmz_data = None

col_kmz, col_mapa = st.columns([0.9, 1.1])

with col_kmz:
    st.subheader("1. Cargar archivo KMZ")

    kmz_file = st.file_uploader("Seleccioná un archivo KMZ", type=["kmz"])

    if kmz_file is not None:
        try:
            st.session_state.kmz_data = parsear_kmz_ftth(kmz_file)
            st.success("KMZ cargado y procesado correctamente.")
        except Exception as e:
            st.session_state.kmz_data = None
            st.error(f"Error al procesar el KMZ: {e}")

    if st.button("🗑️ Limpiar diseño cargado"):
        st.session_state.kmz_data = None
        st.warning("Se limpió el diseño cargado.")

with col_mapa:
    st.subheader("2. Mapa FTTH desde KMZ")

    if not st.session_state.kmz_data:
        st.info("Subí un KMZ válido para visualizar el diseño.")
    else:
        data = st.session_state.kmz_data

        # Calculamos un centro aproximado (promedio de todos los puntos)
        latitudes = []
        longitudes = []

        for p in data["nodo"] + data["cajas_hub"] + data["cajas_nap"]:
            latitudes.append(p["lat"])
            longitudes.append(p["lon"])

        for linea in data["cables_troncales"] + data["cables_derivaciones"]:
            for lat, lon in linea:
                latitudes.append(lat)
                longitudes.append(lon)

        if latitudes and longitudes:
            center_lat = sum(latitudes) / len(latitudes)
            center_lon = sum(longitudes) / len(longitudes)
        else:
            center_lat = -32.8894
            center_lon = -68.8458

        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=14,
            tiles="CartoDB dark_matter"
        )

        # Cursor tipo mira
        css = """
        <style>
        .leaflet-container {
            cursor: crosshair !important;
        }
        .leaflet-interactive {
            cursor: crosshair !important;
        }
        </style>
        """
        m.get_root().header.add_child(Element(css))

        # --- NODO (punto) ---
        for nodo in data["nodo"]:
            folium.CircleMarker(
                location=[nodo["lat"], nodo["lon"]],
                radius=9,
                color="red",
                fill=True,
                fill_color="red",
                fill_opacity=0.9,
                popup=f"NODO: {nodo['name']}"
            ).add_to(m)

        # --- CABLES TRONCALES (líneas gruesas) ---
        for linea in data["cables_troncales"]:
            folium.PolyLine(
                locations=linea,
                color="deepskyblue",
                weight=5,
                opacity=0.9,
                tooltip="CABLE TRONCAL"
            ).add_to(m)

        # --- CABLES DERIVACIONES (líneas más finas) ---
        for linea in data["cables_derivaciones"]:
            folium.PolyLine(
                locations=linea,
                color="orange",
                weight=3,
                opacity=0.8,
                tooltip="CABLE DERIVACIÓN"
            ).add_to(m)

        # --- CAJAS HUB (rombos azules) ---
        for hub in data["cajas_hub"]:
            folium.RegularPolygonMarker(
                location=[hub["lat"], hub["lon"]],
                number_of_sides=4,
                radius=10,
                rotation=45,
                color="blue",
                weight=2,
                fill=True,
                fill_color="blue",
                fill_opacity=0.9,
                popup=f"CAJA HUB: {hub['name']}"
            ).add_to(m)

        # --- CAJAS NAP (triángulos verdes) ---
        for nap in data["cajas_nap"]:
            folium.RegularPolygonMarker(
                location=[nap["lat"], nap["lon"]],
                number_of_sides=3,
                radius=9,
                rotation=0,
                color="lime",
                weight=2,
                fill=True,
                fill_color="lime",
                fill_opacity=0.9,
                popup=f"CAJA NAP: {nap['name']}"
            ).add_to(m)

        st_folium(m, width="100%", height=550, key="mapa_kmz")

# -------- RESUMEN TABULAR --------
st.subheader("3. Resumen de elementos del diseño (KMZ)")

if not st.session_state.kmz_data:
    st.info("Subí un KMZ para ver el resumen de elementos.")
else:
    data = st.session_state.kmz_data

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**NODO**")
        if data["nodo"]:
            df_nodo = pd.DataFrame(data["nodo"])
            st.dataframe(df_nodo, use_container_width=True, hide_index=True)
        else:
            st.write("Sin NODO definido.")

    with col2:
        st.markdown("**Cajas HUB**")
        if data["cajas_hub"]:
            df_hub = pd.DataFrame(data["cajas_hub"])
            st.dataframe(df_hub, use_container_width=True, hide_index=True)
        else:
            st.write("Sin cajas HUB.")

    with col3:
        st.markdown("**Cajas NAP**")
        if data["cajas_nap"]:
            df_nap = pd.DataFrame(data["cajas_nap"])
            st.dataframe(df_nap, use_container_width=True, hide_index=True)
        else:
            st.write("Sin cajas NAP.")
