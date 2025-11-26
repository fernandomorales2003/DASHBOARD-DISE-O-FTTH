import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import folium
import requests

from streamlit_folium import st_folium
from branca.element import Element

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
    # Posiciones acumuladas
    x_olt = 0
    x_nap = d_olt_nap
    x_cto = d_olt_nap + d_nap_cto
    x_ont = d_olt_nap + d_nap_cto + d_cto_ont

    x_vals = [x_olt, x_nap, x_cto, x_ont]
    y_vals = [0, 0, 0, 0]
    labels = ["OLT", "NAP", "CTO", "ONT"]

    fig = go.Figure()

    # Línea entre nodos
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=y_vals,
        mode="lines+markers+text",
        text=labels,
        textposition="top center",
        marker=dict(size=14),
        line=dict(width=3)
    ))

    # Agregar anotaciones de distancias
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

# -------- COLUMNA IZQUIERDA: MAPA LÓGICO --------
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

    # Mostrar mapa lógico
    fig_mapa = crear_mapa_ftth(d_olt_nap, d_nap_cto, d_cto_ont)
    st.plotly_chart(fig_mapa, use_container_width=True)

    # Tabla resumen de tramos
    st.markdown("#### Resumen de tramos")
    df_tramos = pd.DataFrame({
        "Tramo": ["OLT → NAP", "NAP → CTO", "CTO → ONT"],
        "Distancia (km)": [d_olt_nap, d_nap_cto, d_cto_ont]
    })
    st.dataframe(df_tramos, use_container_width=True, hide_index=True)

# -------- COLUMNA DERECHA: PRESUPUESTO ÓPTICO --------
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
        st.write("")  # Relleno

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
def obtener_ruta_osrm(lat1, lon1, lat2, lon2):
    """
    Pide a OSRM una ruta por calles entre dos puntos.
    Devuelve una lista de [lat, lon] que se puede usar en folium.PolyLine.
    Si falla, devuelve la línea recta entre los dos puntos.
    """
    try:
        url = (
            f"https://router.project-osrm.org/route/v1/driving/"
            f"{lon1},{lat1};{lon2},{lat2}"
        )
        params = {"overview": "full", "geometries": "geojson"}
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()

        coords = data["routes"][0]["geometry"]["coordinates"]  # [ [lon,lat], ... ]
        # Convertimos a [lat, lon] que es lo que usa Folium
        ruta = [[lat, lon] for lon, lat in coords]
        return ruta

    except Exception:
        # Fallback: línea recta
        return [[lat1, lon1], [lat2, lon2]]


# =========================
# MÓDULO 2 — DISEÑO FTTH EN MAPA (FOLIUM)
# =========================

st.markdown("---")
st.header("Módulo de Diseño FTTH en Mapa — HUB / NODO / NAP / BOTELLA")

st.markdown(
    """
### Parte 2 — Diseño visual sobre mapa

En este módulo podés diseñar de forma visual la red FTTH:

1. Elegís el tipo de elemento (**HUB**, **NODO**, **NAP** o **BOTELLA**).
2. Le ponés un nombre.
3. Hacés clic en el mapa para indicar la ubicación.
4. Lo agregás al diseño y se dibuja con una **forma distinta** según el tipo.

Luego se trazan las líneas de fibra:

- HUB → NODO
- NODO → NAPs
"""
)

# Centro por defecto (Mendoza)
DEFAULT_LAT = -32.8894
DEFAULT_LON = -68.8458

# Estado para guardar los elementos
if "ftth_elementos" not in st.session_state:
    st.session_state.ftth_elementos = []  # lista de dicts {tipo, nombre, lat, lon}

if "last_click" not in st.session_state:
    st.session_state.last_click = None

col_form, col_mapa = st.columns([0.9, 1.1])

# -------- FORMULARIO LADO IZQUIERDO --------
with col_form:
    st.subheader("1. Definir elemento a colocar")

    tipo = st.selectbox("Tipo de elemento", ["HUB", "NODO", "NAP", "BOTELLA"])
    nombre = st.text_input("Nombre / Identificación", value=f"{tipo}_1")

    st.markdown("#### Último punto clickeado en el mapa")
    if st.session_state.last_click is None:
        st.info("Hacé clic en el mapa para elegir la posición.")
        lat_click = None
        lon_click = None
    else:
        lat_click = st.session_state.last_click.get("lat")
        lon_click = st.session_state.last_click.get("lon")
        if lat_click is not None and lon_click is not None:
            st.code(f"Lat: {lat_click:.6f}  |  Lon: {lon_click:.6f}")
        else:
            st.info("Hacé clic en el mapa para elegir la posición.")
            lat_click = None
            lon_click = None

    if st.button("➕ Agregar elemento en la posición clickeada"):
        if nombre.strip() == "":
            st.warning("Por favor ingresá un nombre para el elemento.")
        elif lat_click is None or lon_click is None:
            st.warning("Primero hacé clic en el mapa para elegir la posición.")
        else:
            st.session_state.ftth_elementos.append(
                {
                    "tipo": tipo,
                    "nombre": nombre.strip(),
                    "lat": lat_click,
                    "lon": lon_click
                }
            )
            st.success(f"{tipo} '{nombre}' agregado al diseño.")

    if st.button("🗑️ Limpiar diseño completo"):
        st.session_state.ftth_elementos = []
        st.warning("Se han eliminado todos los elementos del diseño.")

# -------- MAPA LADO DERECHO --------
with col_mapa:
    st.subheader("2. Mapa interactivo — Hacé clic para ubicar elementos")

    # Crear mapa base
    center_lat = DEFAULT_LAT
    center_lon = DEFAULT_LON

    # Si ya hay elementos, centramos en el promedio
    if st.session_state.ftth_elementos:
        df_tmp = pd.DataFrame(st.session_state.ftth_elementos)
        center_lat = df_tmp["lat"].mean()
        center_lon = df_tmp["lon"].mean()

    # Mapa oscuro
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="CartoDB dark_matter"
    )

    # Cambiar puntero a crosshair
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

    # Agregar elementos existentes con distintas formas
    for elem in st.session_state.ftth_elementos:
        e_lat = elem["lat"]
        e_lon = elem["lon"]
        e_tipo = elem["tipo"]
        e_nombre = elem["nombre"]

        # Definimos forma y color según tipo
        if e_tipo == "HUB":
            # ROMBO (cuadrado girado 45°)
            marker = folium.RegularPolygonMarker(
                location=[e_lat, e_lon],
                number_of_sides=4,
                radius=12,
                rotation=45,
                color="blue",
                weight=2,
                fill=True,
                fill_color="blue",
                fill_opacity=0.7,
                popup=f"HUB: {e_nombre}"
            )
        elif e_tipo == "NODO":
            # Círculo
            marker = folium.CircleMarker(
                location=[e_lat, e_lon],
                radius=10,
                color="red",
                fill=True,
                fill_color="red",
                fill_opacity=0.7,
                popup=f"NODO: {e_nombre}"
            )
        elif e_tipo == "NAP":
            # TRIÁNGULO
            marker = folium.RegularPolygonMarker(
                location=[e_lat, e_lon],
                number_of_sides=3,
                radius=10,
                rotation=0,
                color="green",
                weight=2,
                fill=True,
                fill_color="green",
                fill_opacity=0.7,
                popup=f"NAP: {e_nombre}"
            )
        else:
            # BOTELLA → RECTÁNGULO / CUADRADO
            marker = folium.RegularPolygonMarker(
                location=[e_lat, e_lon],
                number_of_sides=4,
                radius=10,
                rotation=0,
                color="purple",
                weight=2,
                fill=True,
                fill_color="purple",
                fill_opacity=0.7,
                popup=f"BOTELLA: {e_nombre}"
            )

        marker.add_to(m)

    # Trazar líneas de fibra: HUB → NODO → NAPs siguiendo calles
    df_elem = pd.DataFrame(st.session_state.ftth_elementos)
    if not df_elem.empty:
        hubs = df_elem[df_elem["tipo"] == "HUB"]
        nodos = df_elem[df_elem["tipo"] == "NODO"]
        naps = df_elem[df_elem["tipo"] == "NAP"]

        if not hubs.empty and not nodos.empty:
            hub = hubs.iloc[0]
            nodo = nodos.iloc[0]

            # Ruta HUB → NODO por calles
            ruta_hub_nodo = obtener_ruta_osrm(
                hub["lat"], hub["lon"],
                nodo["lat"], nodo["lon"]
            )
            folium.PolyLine(
                locations=ruta_hub_nodo,
                color="deepskyblue",
                weight=4,
                tooltip="Fibra HUB → NODO"
            ).add_to(m)

            # Rutas NODO → NAPs por calles
            for _, nap in naps.iterrows():
                ruta_nodo_nap = obtener_ruta_osrm(
                    nodo["lat"], nodo["lon"],
                    nap["lat"], nap["lon"]
                )
                folium.PolyLine(
                    locations=ruta_nodo_nap,
                    color="deepskyblue",
                    weight=3,
                    tooltip=f"Fibra NODO → NAP {nap['nombre']}"
                ).add_to(m)

    # Mostrar mapa y capturar clic
    mapa_data = st_folium(m, width="100%", height=500)

    # Guardar último clic normalizando lon/lng
    if mapa_data and mapa_data.get("last_clicked") is not None:
        raw_click = mapa_data["last_clicked"]
        lat = raw_click.get("lat")
        lon = raw_click.get("lng") or raw_click.get("lon")
        if lat is not None and lon is not None:
            st.session_state.last_click = {"lat": lat, "lon": lon}



# -------- TABLA RESUMEN --------
st.subheader("3. Resumen de elementos del diseño")

if not st.session_state.ftth_elementos:
    st.info("No hay elementos cargados todavía. Usá el mapa para empezar a diseñar.")
else:
    df_resumen = pd.DataFrame(st.session_state.ftth_elementos)
    st.dataframe(
        df_resumen[["tipo", "nombre", "lat", "lon"]],
        use_container_width=True,
        hide_index=True
    )
