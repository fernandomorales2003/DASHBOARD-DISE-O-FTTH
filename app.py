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
