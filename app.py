import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from branca.element import Element
import zipfile
import xml.etree.ElementTree as ET
import math

st.set_page_config(
    page_title="Módulo Ingeniería FTTH — Mapa + Presupuesto + Diseño",
    layout="wide"
)

# =========================
# ESTILOS GLOBALES (UX / UI)
# =========================
# Fondo claro por defecto, solo limpiamos fondo de gráficos Plotly

st.markdown(
    """
<style>
.js-plotly-plot .plotly {
    background-color: rgba(0, 0, 0, 0) !important;
}
</style>
""",
    unsafe_allow_html=True
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
        line=dict(width=3, color="#4FB4CA")
    ))

    # Anotaciones de distancia
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
        height=350,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)"
    )

    return fig


# =========================
# FUNCIONES GEO — DISTANCIAS
# =========================

def distancia_haversine_km(lat1, lon1, lat2, lon2):
    """
    Distancia en km entre dos puntos (lat/lon) usando Haversine.
    """
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def longitud_total_km(coords):
    """
    Longitud total (km) de una polilínea dada por lista de [lat, lon].
    """
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for i in range(len(coords) - 1):
        lat1, lon1 = coords[i]
        lat2, lon2 = coords[i + 1]
        total += distancia_haversine_km(lat1, lon1, lat2, lon2)
    return total


def nap_mas_cercana(lat, lon, cajas_nap):
    """
    Devuelve (NAP_más_cercana, distancia_km) dado un punto y la lista de cajas NAP.
    Si no hay NAP, devuelve (None, None).
    """
    if not cajas_nap:
        return None, None

    min_dist = None
    mejor = None
    for nap in cajas_nap:
        d = distancia_haversine_km(lat, lon, nap["lat"], nap["lon"])
        if (min_dist is None) or (d < min_dist):
            min_dist = d
            mejor = nap
    return mejor, min_dist


# =========================
# FUNCIONES AUXILIARES — MÓDULO 2 (KMZ vía XML)
# =========================

def parsear_kmz_ftth(file_obj):
    """
    Parser de KMZ FTTH usando xml.etree (sin fastkml).

    Estructura esperada (por nombre de carpetas), nombres flexibles:

    FTTH-DISEÑO/
      NODO / NODOS
      CABLES TRONCALES / TRONCAL
      CABLES DERIVACIONES / DERIV
      CABLES PRECONECTORIZADOS / PRECO
      CAJAS HUB / HUB
      CAJAS NAP / NAP
      FOSC / BOTELLA (botellas de fibra óptica)
    """
    data = {
        "nodo": [],
        "cables_troncales": [],      # lista de dicts {name, coords}
        "cables_derivaciones": [],   # lista de dicts {name, coords}
        "cables_preconect": [],      # lista de dicts {name, coords}
        "cajas_hub": [],
        "cajas_nap": [],
        "botellas": []               # lista de dicts {name, lat, lon}
    }

    # 1) Abrir KMZ (zip) y encontrar el primer .kml
    with zipfile.ZipFile(file_obj) as zf:
        kml_name = None
        for info in zf.infolist():
            if info.filename.lower().endswith(".kml"):
                kml_name = info.filename
                break

        if kml_name is None:
            raise ValueError("El KMZ no contiene ningún archivo .kml")

        kml_bytes = zf.read(kml_name)

    # 2) Parsear XML del KML
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    root = ET.fromstring(kml_bytes)

    document = root.find("k:Document", ns)
    if document is None:
        document = root

    def get_text(elem):
        return elem.text.strip() if elem is not None and elem.text else ""

    def parse_coordinates(text_coords):
        """
        Convierte string de KML coordinates en lista de [lat, lon].
        Formato típico: "lon,lat,alt lon,lat,alt ..."
        """
        coords = []
        if not text_coords:
            return coords
        for token in text_coords.strip().split():
            parts = token.split(",")
            if len(parts) >= 2:
                try:
                    lon = float(parts[0])
                    lat = float(parts[1])
                    coords.append([lat, lon])
                except ValueError:
                    continue
        return coords

    def walk_folder(folder_elem, path=""):
        """
        Recorre recursivamente carpetas (<Folder>) y procesa <Placemark>.
        path acumula los nombres de carpeta para clasificar: NODO, CAJAS HUB, FOSC, etc.
        """
        name_elem = folder_elem.find("k:name", ns)
        folder_name = get_text(name_elem)
        new_path = f"{path}/{folder_name}" if path else folder_name

        # Procesar todos los Placemark dentro de esta carpeta
        for pm in folder_elem.findall("k:Placemark", ns):
            pm_name = get_text(pm.find("k:name", ns))
            pm_path = f"{new_path}/{pm_name}" if new_path else pm_name
            p = pm_path.upper()

            # ----- PUNTO -----
            point = pm.find(".//k:Point", ns)
            if point is not None:
                coords_elem = point.find("k:coordinates", ns)
                coords_list = parse_coordinates(get_text(coords_elem))
                if coords_list:
                    lat, lon = coords_list[0]
                    punto = {"name": pm_name, "lat": lat, "lon": lon}

                    # Cajas NAP
                    if "CAJAS NAP" in p or p.endswith("/NAP") or "/NAP/" in p:
                        data["cajas_nap"].append(punto)
                    # Cajas HUB
                    elif "CAJAS HUB" in p or p.endswith("/HUB") or "/HUB/" in p:
                        data["cajas_hub"].append(punto)
                    # FOSC / Botellas
                    elif "FOSC" in p or "BOTELLA" in p:
                        data["botellas"].append(punto)
                    # Nodo
                    elif "/NODO" in p or p.startswith("NODO") or " NODO" in p or p.endswith("/NODOS"):
                        data["nodo"].append(punto)
                    else:
                        # fallback: nodo genérico
                        data["nodo"].append(punto)
                continue  # si era punto, no miramos línea

            # ----- LÍNEA (LineString) -----
            line = pm.find(".//k:LineString", ns)
            if line is not None:
                coords_elem = line.find("k:coordinates", ns)
                coords_list = parse_coordinates(get_text(coords_elem))
                if coords_list:
                    # Clasificación flexible + fallback
                    if "CABLES TRONCALES" in p or "TRONCAL" in p:
                        data["cables_troncales"].append({
                            "name": pm_name,
                            "coords": coords_list
                        })
                    elif "CABLES DERIVACIONES" in p or "DERIV" in p:
                        data["cables_derivaciones"].append({
                            "name": pm_name,
                            "coords": coords_list
                        })
                    elif "CABLES PRECONECTORIZADOS" in p or "PRECO" in p:
                        data["cables_preconect"].append({
                            "name": pm_name,
                            "coords": coords_list
                        })
                    else:
                        # Si no matchea nada, al menos lo dibujamos como troncal
                        data["cables_troncales"].append({
                            "name": pm_name,
                            "coords": coords_list
                        })

        # Recorrer carpetas hijas
        for subfolder in folder_elem.findall("k:Folder", ns):
            walk_folder(subfolder, new_path)

    # 3) Iniciar recorrido desde Document
    for folder in document.findall("k:Folder", ns):
        walk_folder(folder, "")

    return data


# =========================
# ESTADO KMZ
# =========================

if "kmz_data" not in st.session_state:
    st.session_state.kmz_data = None

# =========================
# TÍTULO GENERAL + TABS
# =========================

st.title("Módulo Ingeniería FTTH — Mapa + Presupuesto + Diseño")

tab1, tab2, tab3 = st.tabs([
    "Ingeniería & Presupuesto óptico",
    "Mapa FTTH (KMZ)",
    "Estadísticas & Resumen"
])

# =========================
# TAB 1 — INGENIERÍA & PRESUPUESTO
# =========================

with tab1:
    st.markdown(
        """
### Configuración del enlace y presupuesto óptico

Ajustá los parámetros del enlace y visualizá el mapa lógico junto con el presupuesto óptico completo hasta el cliente.
"""
    )

    col_izq, col_der = st.columns([1.1, 1])

    with col_izq:
        st.subheader("Mapa lógico FTTH")

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
        st.subheader("Presupuesto óptico del enlace")

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
# TAB 2 — MAPA FTTH (KMZ)
# =========================

with tab2:
    st.markdown(
        """
### Mapa FTTH desde archivo KMZ

Subí un diseño FTTH en formato **KMZ** y visualizá el NODO, troncales, derivaciones,
cables preconectorizados, HUB, NAP y FOSC sobre el mapa.
"""
    )

    col_kmz, col_mapa = st.columns([0.3, 0.7])

    # --------- PANEL IZQUIERDO: CARGA KMZ ---------
    with col_kmz:
        st.subheader("Carga de diseño (KMZ)")

        kmz_file = st.file_uploader("Seleccioná un archivo KMZ", type=["kmz"], key="kmz_uploader")

        if kmz_file is not None:
            try:
                st.session_state.kmz_data = parsear_kmz_ftth(kmz_file)
                st.success("KMZ cargado y procesado correctamente.")
            except Exception as e:
                st.session_state.kmz_data = None
                st.error(f"Error al procesar el KMZ: {e}")

        if st.button("🗑️ Limpiar diseño cargado", key="btn_clear_kmz"):
            st.session_state.kmz_data = None
            st.warning("Se limpió el diseño cargado.")

    # --------- PANEL DERECHO: MAPA FTTH ---------
    with col_mapa:
        st.subheader("Panel de red FTTH")

        if not st.session_state.kmz_data:
            st.info("Subí un KMZ válido para visualizar el diseño.")
        else:
            data = st.session_state.kmz_data

            # Totales para panel
            total_troncal_m = 0.0
            total_deriv_m = 0.0
            total_precon_m = 0.0  # por si lo queremos usar después

            # Buckets de precon por rango de distancia
            buckets_precon = [
                ("0 a 50 m - CABLE DE 50", 0, 50),
                ("51 a 100 m - CABLE DE 100", 51, 100),
                ("101 a 150 m - CABLE DE 150", 101, 150),
                ("151 a 200 m - CABLE DE 200", 151, 200),
                ("201 a 250 m - CABLE DE 250", 201, 250),
                ("251 a 300 m - CABLE DE 300", 251, 300),
            ]
            precon_counts = {label: 0 for (label, _, _) in buckets_precon}
            precon_mayor_300 = 0

            # Longitudes
            for cable in data["cables_troncales"]:
                total_troncal_m += longitud_total_km(cable["coords"]) * 1000.0

            for cable in data["cables_derivaciones"]:
                total_deriv_m += longitud_total_km(cable["coords"]) * 1000.0

            for cable in data["cables_preconect"]:
                long_m = longitud_total_km(cable["coords"]) * 1000.0
                total_precon_m += long_m

                asignado = False
                for label, lo, hi in buckets_precon:
                    if lo <= long_m <= hi:
                        precon_counts[label] += 1
                        asignado = True
                        break
                if not asignado and long_m > 300:
                    precon_mayor_300 += 1

            cant_nodo = len(data["nodo"])
            cant_hub = len(data["cajas_hub"])
            cant_nap = len(data["cajas_nap"])
            cant_fosc = len(data["botellas"])
            cant_precon = len(data["cables_preconect"])

            # -------- MÉTRICAS SUPERIORES --------
            r1c1, r1c2, r1c3 = st.columns(3)
            with r1c1:
                st.metric("Cable troncal (m)", f"{total_troncal_m:.0f}")
            with r1c2:
                st.metric("Cable derivación (m)", f"{total_deriv_m:.0f}")
            with r1c3:
                st.metric("Cables preconectorizados", cant_precon)

            r2c1, r2c2, r2c3, r2c4 = st.columns(4)
            with r2c1:
                st.metric("Nodos", cant_nodo)
            with r2c2:
                st.metric("Cajas HUB", cant_hub)
            with r2c3:
                st.metric("Cajas NAP", cant_nap)
            with r2c4:
                st.metric("FOSC / Botellas", cant_fosc)

            # -------- CENTRO DEL MAPA (GENERAL) --------
            latitudes = []
            longitudes = []

            for p in data["nodo"] + data["cajas_hub"] + data["cajas_nap"] + data["botellas"]:
                latitudes.append(p["lat"])
                longitudes.append(p["lon"])

            for cable in data["cables_troncales"] + data["cables_derivaciones"]:
                for lat, lon in cable["coords"]:
                    latitudes.append(lat)
                    longitudes.append(lon)

            for cable in data["cables_preconect"]:
                for lat, lon in cable["coords"]:
                    latitudes.append(lat)
                    longitudes.append(lon)

            if latitudes and longitudes:
                center_lat = sum(latitudes) / len(latitudes)
                center_lon = sum(longitudes) / len(longitudes)
            else:
                center_lat = -32.8894
                center_lon = -68.8458

            # -------- CREACIÓN DEL MAPA --------
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

            # FeatureGroups generales
            fg_nodo = folium.FeatureGroup(name="Nodos", show=True)
            fg_hub = folium.FeatureGroup(name="Cajas HUB", show=True)
            fg_nap = folium.FeatureGroup(name="Cajas NAP", show=True)
            fg_fosc = folium.FeatureGroup(name="FOSC / Botellas", show=True)
            fg_precon = folium.FeatureGroup(name="Cables preconectorizados (todos)", show=True)

            fg_nodo.add_to(m)
            fg_hub.add_to(m)
            fg_nap.add_to(m)
            fg_fosc.add_to(m)
            fg_precon.add_to(m)

            # ----- NODOS -----
            for nodo in data["nodo"]:
                folium.CircleMarker(
                    location=[nodo["lat"], nodo["lon"]],
                    radius=9,
                    color="#f97316",
                    fill=True,
                    fill_color="#f97316",
                    fill_opacity=0.9,
                    popup=f"NODO: {nodo['name']}"
                ).add_to(fg_nodo)

            # ----- CABLES TRONCALES (cada cable con su propia capa) -----
            for cable in data["cables_troncales"]:
                fg_troncal = folium.FeatureGroup(
                    name=f"Troncal - {cable['name']}",
                    show=True
                )
                fg_troncal.add_to(m)

                folium.PolyLine(
                    locations=cable["coords"],
                    color="#3b82f6",
                    weight=5,
                    opacity=0.9,
                    tooltip=f"Troncal: {cable['name']}",
                    popup=f"Cable troncal: {cable['name']}"
                ).add_to(fg_troncal)

            # ----- CABLES DERIVACIÓN (cada cable con su propia capa) -----
            for cable in data["cables_derivaciones"]:
                fg_deriv = folium.FeatureGroup(
                    name=f"Derivación - {cable['name']}",
                    show=True
                )
                fg_deriv.add_to(m)

                folium.PolyLine(
                    locations=cable["coords"],
                    color="#f59e0b",
                    weight=3,
                    opacity=0.8,
                    tooltip=f"Derivación: {cable['name']}",
                    popup=f"Cable derivación: {cable['name']}"
                ).add_to(fg_deriv)

            # ----- CABLES PRECONECTORIZADOS (todos juntos en una capa) -----
            for cable in data["cables_preconect"]:
                folium.PolyLine(
                    locations=cable["coords"],
                    color="#a855f7",
                    weight=2,
                    opacity=0.9,
                    dash_array="4,4",
                    tooltip=f"Precon: {cable['name']}",
                    popup=f"Cable preconectorizado: {cable['name']}"
                ).add_to(fg_precon)

            # ----- CAJAS HUB -----
            for hub in data["cajas_hub"]:
                folium.RegularPolygonMarker(
                    location=[hub["lat"], hub["lon"]],
                    number_of_sides=4,
                    radius=10,
                    rotation=45,
                    color="#38bdf8",
                    weight=2,
                    fill=True,
                    fill_color="#38bdf8",
                    fill_opacity=0.9,
                    popup=f"CAJA HUB: {hub['name']}"
                ).add_to(fg_hub)

            # ----- CAJAS NAP -----
            for nap in data["cajas_nap"]:
                folium.RegularPolygonMarker(
                    location=[nap["lat"], nap["lon"]],
                    number_of_sides=3,
                    radius=9,
                    rotation=0,
                    color="#22c55e",
                    weight=2,
                    fill=True,
                    fill_color="#22c55e",
                    fill_opacity=0.9,
                    popup=f"CAJA NAP: {nap['name']}"
                ).add_to(fg_nap)

            # ----- FOSC / BOTELLAS -----
            for bot in data["botellas"]:
                folium.RegularPolygonMarker(
                    location=[bot["lat"], bot["lon"]],
                    number_of_sides=4,
                    radius=8,
                    rotation=0,
                    color="#e11d48",
                    weight=2,
                    fill=True,
                    fill_color="#e11d48",
                    fill_opacity=0.9,
                    popup=f"FOSC / BOTELLA: {bot['name']}"
                ).add_to(fg_fosc)

            # Control de capas (colapsado → solo el ícono, adentro todas las capas)
            folium.LayerControl(collapsed=True).add_to(m)

            st_folium(m, width="100%", height=650, key="mapa_kmz")

            # --------- DISTRIBUCIÓN PRECON EN EXPANDER ---------
            if cant_precon > 0:
                with st.expander("Distribución de cables preconectorizados por longitud"):
                    filas_precon_panel = []
                    for label, lo, hi in buckets_precon:
                        filas_precon_panel.append({
                            "Rango": label,
                            "Cantidad de cables": precon_counts[label]
                        })
                    if precon_mayor_300 > 0:
                        filas_precon_panel.append({
                            "Rango": "Mayor a 300 m",
                            "Cantidad de cables": precon_mayor_300
                        })

                    df_precon_panel = pd.DataFrame(filas_precon_panel)
                    st.dataframe(df_precon_panel, use_container_width=True, hide_index=True)
            else:
                with st.expander("Distribución de cables preconectorizados por longitud"):
                    st.info("No se encontraron cables preconectorizados en el diseño.")




# =========================
# TAB 3 — ESTADÍSTICAS & RESUMEN
# =========================

with tab3:
    st.markdown(
        """
### Resumen y estadísticas del diseño

Vista ejecutiva con totales de elementos y longitudes, más gráficos para entender la composición de la red.
"""
    )

    if not st.session_state.kmz_data:
        st.info("Subí un KMZ en la pestaña **Mapa FTTH (KMZ)** para ver el resumen y las estadísticas.")
    else:
        data = st.session_state.kmz_data

        # Totales
        total_troncal_m = 0.0
        total_deriv_m = 0.0
        total_precon_m = 0.0

        for cable in data["cables_troncales"]:
            total_troncal_m += longitud_total_km(cable["coords"]) * 1000.0
        for cable in data["cables_derivaciones"]:
            total_deriv_m += longitud_total_km(cable["coords"]) * 1000.0
        for cable in data["cables_preconect"]:
            total_precon_m += longitud_total_km(cable["coords"]) * 1000.0

        cant_nodo = len(data["nodo"])
        cant_hub = len(data["cajas_hub"])
        cant_nap = len(data["cajas_nap"])
        cant_fosc = len(data["botellas"])

        # ---- Tabla de resumen única ----
        st.markdown("### Resumen general por tipo de elemento")

        filas_resumen = [
            {"Elemento": "Nodos", "Cantidad": cant_nodo, "Longitud total (m)": ""},
            {"Elemento": "Cajas HUB", "Cantidad": cant_hub, "Longitud total (m)": ""},
            {"Elemento": "Cajas NAP", "Cantidad": cant_nap, "Longitud total (m)": ""},
            {"Elemento": "FOSC / Botellas", "Cantidad": cant_fosc, "Longitud total (m)": ""},
            {
                "Elemento": "Cables troncales",
                "Cantidad": len(data["cables_troncales"]),
                "Longitud total (m)": round(total_troncal_m, 1)
            },
            {
                "Elemento": "Cables derivación",
                "Cantidad": len(data["cables_derivaciones"]),
                "Longitud total (m)": round(total_deriv_m, 1)
            },
            {
                "Elemento": "Cables preconectorizados",
                "Cantidad": len(data["cables_preconect"]),
                "Longitud total (m)": round(total_precon_m, 1)
            },
        ]

        df_resumen = pd.DataFrame(filas_resumen)
        st.dataframe(df_resumen, use_container_width=True, hide_index=True)

        # ---- Detalle por tipo en expanders ----
        st.markdown("### Detalle por tipo (opcional)")

        with st.expander("Detalle de nodos"):
            if data["nodo"]:
                df_nodo = pd.DataFrame(data["nodo"])
                st.dataframe(df_nodo[["name"]], use_container_width=True, hide_index=True)
            else:
                st.write("Sin NODO definido.")

        with st.expander("Detalle de cajas HUB"):
            if data["cajas_hub"]:
                df_hub = pd.DataFrame(data["cajas_hub"])
                st.dataframe(df_hub[["name"]], use_container_width=True, hide_index=True)
            else:
                st.write("Sin cajas HUB.")

        with st.expander("Detalle de cajas NAP"):
            if data["cajas_nap"]:
                df_nap = pd.DataFrame(data["cajas_nap"])
                st.dataframe(df_nap[["name"]], use_container_width=True, hide_index=True)
            else:
                st.write("Sin cajas NAP.")

        with st.expander("Detalle de FOSC / Botellas"):
            if data["botellas"]:
                df_bot = pd.DataFrame(data["botellas"])
                st.dataframe(df_bot[["name"]], use_container_width=True, hide_index=True)
            else:
                st.write("Sin FOSC / Botellas definidas.")

        with st.expander("Detalle de cables troncales"):
            if data["cables_troncales"]:
                filas_tron = []
                for cable in data["cables_troncales"]:
                    long_m = longitud_total_km(cable["coords"]) * 1000.0
                    filas_tron.append({
                        "Cable": cable["name"],
                        "Longitud (m)": round(long_m, 1)
                    })
                df_tron = pd.DataFrame(filas_tron)
                st.dataframe(df_tron, use_container_width=True, hide_index=True)
            else:
                st.write("No hay cables troncales.")

        with st.expander("Detalle de cables de derivación"):
            if data["cables_derivaciones"]:
                filas_der = []
                for cable in data["cables_derivaciones"]:
                    long_m = longitud_total_km(cable["coords"]) * 1000.0
                    filas_der.append({
                        "Cable": cable["name"],
                        "Longitud (m)": round(long_m, 1)
                    })
                df_der = pd.DataFrame(filas_der)
                st.dataframe(df_der, use_container_width=True, hide_index=True)
            else:
                st.write("No hay cables de derivación.")

        with st.expander("Detalle de cables preconectorizados"):
            if not data["cables_preconect"]:
                st.write("No se encontraron CABLES PRECONECTORIZADOS en el KMZ.")
            else:
                filas_precon = []
                for cable in data["cables_preconect"]:
                    nombre_cable = cable["name"]
                    coords = cable["coords"]
                    long_km = longitud_total_km(coords)
                    long_m = long_km * 1000.0

                    # Tomamos el último punto como extremo hacia NAP
                    lat_fin, lon_fin = coords[-1]
                    nap_dest, dist_km = nap_mas_cercana(lat_fin, lon_fin, data["cajas_nap"])

                    if nap_dest is not None:
                        nombre_nap = nap_dest["name"]
                    else:
                        nombre_nap = "Sin NAP cercana"

                    filas_precon.append({
                        "Cable": nombre_cable,
                        "NAP destino": nombre_nap,
                        "Longitud (m)": round(long_m, 1)
                    })

                df_precon = pd.DataFrame(filas_precon)
                st.dataframe(df_precon, use_container_width=True, hide_index=True)

        # =========================
        # GRÁFICOS (MÓDULO 3)
        # =========================
        st.markdown("---")
        st.header("Estadísticas del diseño")

        st.markdown("#### Longitud total de cable por tipo (m)")

        fig_cables = go.Figure(
            data=[
                go.Bar(
                    x=["Troncal", "Derivación", "Preconectorizado"],
                    y=[total_troncal_m, total_deriv_m, total_precon_m],
                    marker_color=["#3b82f6", "#f59e0b", "#a855f7"]
                )
            ]
        )
        fig_cables.update_layout(
            xaxis_title="Tipo de cable",
            yaxis_title="Longitud (m)",
            height=350,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_cables, use_container_width=True)

        st.markdown("#### Cantidad de elementos por tipo")

        fig_elems = go.Figure(
            data=[
                go.Bar(
                    x=["Nodos", "Cajas HUB", "Cajas NAP", "FOSC / Botellas"],
                    y=[cant_nodo, cant_hub, cant_nap, cant_fosc],
                    marker_color=["#f97316", "#38bdf8", "#22c55e", "#e11d48"]
                )
            ]
        )
        fig_elems.update_layout(
            xaxis_title="Tipo de elemento",
            yaxis_title="Cantidad",
            height=350,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_elems, use_container_width=True)
