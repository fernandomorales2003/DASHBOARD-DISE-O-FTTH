import pydeck as pdk
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(
    page_title="Módulo Ingeniería FTTH — Mapa + Presupuesto Óptico",
    layout="wide"
)

# =========================
# FUNCIONES AUXILIARES
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
# UI PRINCIPAL
# =========================

st.title("Módulo Ingeniería FTTH — Mapa + Presupuesto Óptico")

st.markdown(
    """
Este módulo integra en una sola vista:

- Un **mapa lógico FTTH** (OLT → NAP → CTO → ONT).
- El **presupuesto óptico completo** del enlace hasta el cliente.

Ideal para usar en capacitaciones y como MVP para una versión SaaS.
"""
)

col_izq, col_der = st.columns([1.1, 1])

# =========================
# COLUMNA IZQUIERDA: MAPA
# =========================
with col_izq:
    st.subheader("1. Configuración del enlace y mapa FTTH")

    st.markdown("### Distancias por tramo (km)")
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
    st.markdown("### Resumen de tramos")
    df_tramos = pd.DataFrame({
        "Tramo": ["OLT → NAP", "NAP → CTO", "CTO → ONT"],
        "Distancia (km)": [d_olt_nap, d_nap_cto, d_cto_ont]
    })
    st.dataframe(df_tramos, use_container_width=True, hide_index=True)


# =========================
# COLUMNA DERECHA: PRESUPUESTO
# =========================
with col_der:
    st.subheader("2. Presupuesto óptico del enlace")

    st.markdown("### Parámetros generales")
    c1, c2 = st.columns(2)
    with c1:
        pot_olt_dbm = st.number_input("Potencia OLT (dBm)", value=3.0, step=0.5)
    with c2:
        sens_ont_dbm = st.number_input("Sensibilidad mínima ONT (dBm)", value=-27.0, step=0.5)

    st.markdown("### Fibra óptica")
    c3, c4 = st.columns(2)
    with c3:
        atenuacion_db_km = st.number_input("Atenuación fibra (dB/km)", value=0.21, step=0.01)
    with c4:
        st.write("")  # relleno

    st.markdown("### Empalmes y conectores")
    c5, c6 = st.columns(2)
    with c5:
        n_empalmes = st.number_input("Cantidad de empalmes", min_value=0, value=8, step=1)
        n_conectores = st.number_input("Cantidad de conectores", min_value=0, value=6, step=1)
    with c6:
        perd_empalme_db = st.number_input("Pérdida por empalme (dB)", value=0.05, step=0.01)
        perd_conector_db = st.number_input("Pérdida por conector (dB)", value=0.25, step=0.01)

    st.markdown("### Splitters (PON)")
    # Valores de ejemplo típicos, los podés ajustar luego
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
    st.markdown("### Resultados del presupuesto óptico")

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

    # Detalle de pérdidas
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

import pydeck as pdk  # agregalo arriba junto con el resto de imports
import math

# =========================================================
# SEGUNDA PARTE: DISEÑO FTTH EN MAPA (HUB, NODO, NAPs)
# =========================================================

st.markdown("---")
st.header("Módulo de Diseño FTTH en Mapa (HUB → NODO → NAPs)")

st.markdown(
    """
En este módulo podés **diseñar la red FTTH de forma manual**:
- Colocar un **HUB**.
- Definir un **NODO**.
- Agregar varias **NAPs**.
- Visualizar el tendido de **fibra entre HUB → NODO → NAPs** sobre un mapa.

Ideal para mostrar el flujo de diseño durante la capacitación.
"""
)

# Centro por defecto (ej: Mendoza)
DEFAULT_LAT = -32.8894
DEFAULT_LON = -68.8458

# Estado para guardar los elementos
if "ftth_elementos" not in st.session_state:
    st.session_state.ftth_elementos = []  # lista de dicts {tipo, nombre, lat, lon}


# -----------------------------
# Formularios de alta de nodos
# -----------------------------
col_form, col_mapa = st.columns([0.9, 1.1])

with col_form:
    st.subheader("1. Agregar elementos de la red")

    tipo = st.selectbox("Tipo de elemento", ["HUB", "NODO", "NAP"])
    nombre = st.text_input("Nombre / Identificación", value=f"{tipo}_1")

    c_lat, c_lon = st.columns(2)
    with c_lat:
        lat = st.number_input(
            "Latitud",
            value=DEFAULT_LAT,
            format="%.6f"
        )
    with c_lon:
        lon = st.number_input(
            "Longitud",
            value=DEFAULT_LON,
            format="%.6f"
        )

    if st.button("➕ Agregar al diseño"):
        if nombre.strip() == "":
            st.warning("Por favor ingresá un nombre para el elemento.")
        else:
            st.session_state.ftth_elementos.append(
                {
                    "tipo": tipo,
                    "nombre": nombre.strip(),
                    "lat": lat,
                    "lon": lon
                }
            )
            st.success(f"{tipo} '{nombre}' agregado al diseño.")

    # Opción para limpiar todo
    if st.button("🗑️ Limpiar diseño completo"):
        st.session_state.ftth_elementos = []
        st.warning("Se han eliminado todos los elementos del diseño.")


# -----------------------------
# Construcción de DataFrames
# -----------------------------
df_elem = pd.DataFrame(st.session_state.ftth_elementos)

with col_mapa:
    st.subheader("2. Visualización en mapa")

    if df_elem.empty:
        st.info("Todavía no hay elementos cargados. Agregá un HUB, NODO o NAP para comenzar.")
    else:
        # Asignar color y tamaño según tipo
        def color_por_tipo(t):
            if t == "HUB":
                return [0, 0, 255]      # azul
            elif t == "NODO":
                return [255, 0, 0]      # rojo
            else:
                return [0, 200, 0]      # verde para NAP

        def size_por_tipo(t):
            if t == "HUB":
                return 16
            elif t == "NODO":
                return 14
            else:
                return 12

        df_elem["color"] = df_elem["tipo"].apply(color_por_tipo)
        df_elem["size"] = df_elem["tipo"].apply(size_por_tipo)

        # Centro del mapa = promedio
        center_lat = df_elem["lat"].mean()
        center_lon = df_elem["lon"].mean()

        # -----------------------------
        # Construir capas de puntos
        # -----------------------------
        scatter_layer = pdk.Layer(
            "ScatterplotLayer",
            data=df_elem,
            get_position='[lon, lat]',
            get_color="color",
            get_radius="size * 5",
            pickable=True
        )

        text_layer = pdk.Layer(
            "TextLayer",
            data=df_elem,
            get_position='[lon, lat]',
            get_text="nombre",
            get_size=12,
            get_color=[255, 255, 255],
            get_text_anchor='"top"',
            get_alignment_baseline='"bottom"'
        )

        # -----------------------------
        # Construir líneas HUB → NODO → NAP
        # -----------------------------
        hubs = df_elem[df_elem["tipo"] == "HUB"]
        nodos = df_elem[df_elem["tipo"] == "NODO"]
        naps = df_elem[df_elem["tipo"] == "NAP"]

        line_data = []

        # Para simplificar: tomamos el primer HUB y el primer NODO si existen
        if not hubs.empty and not nodos.empty:
            hub = hubs.iloc[0]
            nodo = nodos.iloc[0]
            line_data.append({
                "from_lon": hub["lon"],
                "from_lat": hub["lat"],
                "to_lon": nodo["lon"],
                "to_lat": nodo["lat"],
                "tipo": "HUB → NODO"
            })

            # NODO → cada NAP
            for _, nap in naps.iterrows():
                line_data.append({
                    "from_lon": nodo["lon"],
                    "from_lat": nodo["lat"],
                    "to_lon": nap["lon"],
                    "to_lat": nap["lat"],
                    "tipo": "NODO → NAP"
                })

        df_lineas = pd.DataFrame(line_data)

        line_layer = None
        if not df_lineas.empty:
            line_layer = pdk.Layer(
                "LineLayer",
                data=df_lineas,
                get_source_position='[from_lon, from_lat]',
                get_target_position='[to_lon, to_lat]',
                get_color=[255, 255, 0],
                get_width=3
            )

        # -----------------------------
        # Render del mapa
        # -----------------------------
        layers = [scatter_layer, text_layer]
        if line_layer is not None:
            layers.append(line_layer)

        view_state = pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=14,
            pitch=0
        )

        r = pdk.Deck(
            map_style="mapbox://styles/mapbox/light-v9",
            initial_view_state=view_state,
            layers=layers,
            tooltip={
                "html": "<b>{tipo}</b><br/>{nombre}<br/>Lat: {lat}<br/>Lon: {lon}",
                "style": {"color": "white"}
            }
        )

        st.pydeck_chart(r, use_container_width=True)

# -----------------------------
# Tabla de elementos
# -----------------------------
st.subheader("3. Resumen de elementos del diseño")

if df_elem.empty:
    st.info("No hay elementos cargados todavía.")
else:
    st.dataframe(
        df_elem[["tipo", "nombre", "lat", "lon"]],
        use_container_width=True,
        hide_index=True
    )

