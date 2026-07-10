# src/dashboard/app.py — Dashboard Web de AutomaDent (Streamlit)
# ==============================================================================
# Migrado de dashboard/app.py.
# Usa el cliente Supabase de src.utils.database y la contraseña desde config.
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

from src.utils.database import supabase
from src.utils.config import DASHBOARD_PASSWORD

# ─── Configuración de página ──────────────────────────────────────────────────
st.set_page_config(
    page_title="AutomaDent Dashboard",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Estilos CSS Premium ──────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stMetric {
        background-color: #1e293b;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #334155;
    }
    h1, h2, h3 { color: #38bdf8; }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
#  FUNCIONES DE DATOS (LOOKUPS EN SUPABASE)
# ==============================================================================

@st.cache_data(ttl=60)
def get_citas():
    """Obtiene el listado de todas las citas registradas en Supabase."""
    res = (
        supabase.table("citas")
        .select("id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id")
        .order("fecha_hora", desc=True)
        .execute()
    )
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    pacs = supabase.table("pacientes").select("id, nombre, apellido").execute()
    docs = supabase.table("personal").select("id, nombre, apellido").execute()
    pac_map = {p["id"]: f"{p['nombre']} {p['apellido']}" for p in (pacs.data or [])}
    doc_map = {d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}" for d in (docs.data or [])}
    df["paciente"] = df["paciente_id"].map(pac_map)
    df["doctor"] = df["odontologo_id"].map(doc_map)
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
    df["fecha"] = df["fecha_hora"].dt.date
    df["hora"] = df["fecha_hora"].dt.strftime("%H:%M")
    return df


@st.cache_data(ttl=60)
def get_pacientes():
    """Obtiene los pacientes registrados."""
    res = supabase.table("pacientes").select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


@st.cache_data(ttl=60)
def get_personal():
    """Obtiene el personal registrado."""
    res = supabase.table("personal").select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


@st.cache_data(ttl=60)
def get_pagos():
    """Obtiene el registro financiero de pagos."""
    res = supabase.table("pagos").select("*").execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    citas_df = get_citas()
    if not citas_df.empty:
        df = df.merge(citas_df[["id", "paciente", "doctor", "fecha"]], left_on="cita_id", right_on="id", how="left")
        df.rename(columns={"id_x": "id"}, inplace=True)
        df.drop(columns=["id_y"], inplace=True)
    return df


# ==============================================================================
#  INTERFAZ DE USUARIO
# ==============================================================================

st.sidebar.image("https://www.svgrepo.com/show/51998/dentist.svg", width=80)
st.sidebar.title("AutomaDent Portal")
st.sidebar.subheader("Clínica Dental Inteligente")

menu = st.sidebar.radio(
    "Navegación",
    ["📅 Citas del Día", "📂 Historias Clínicas", "💰 Reportes Financieros",
     "👥 Registro del Personal", "👥 Pacientes"],
)

# ─── Login simple ─────────────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Portal Administrativo</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password = st.text_input("Ingresa la Contraseña de la Clínica:", type="password")
        if st.button("Iniciar Sesión"):
            if password == DASHBOARD_PASSWORD:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta.")
    st.stop()


# ── VISTA: CITAS DEL DÍA ──────────────────────────────────────────────────────
if menu == "📅 Citas del Día":
    st.title("📅 Panel de Control de Citas")
    citas_df = get_citas()
    if citas_df.empty:
        st.info("Aún no hay citas registradas.")
    else:
        hoy = datetime.now().date()
        citas_hoy = citas_df[citas_df["fecha"] == hoy]
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Citas Hoy", len(citas_hoy))
        col2.metric("Programadas", len(citas_df[citas_df["estado"] == "programada"]))
        col3.metric("Confirmadas", len(citas_df[citas_df["estado"] == "confirmada"]))
        col4.metric("Atendidas", len(citas_df[citas_df["estado"] == "asistida"]))
        st.write("---")
        st.subheader("🔍 Filtros")
        f1, f2, f3 = st.columns(3)
        with f1:
            filtro_doc = st.selectbox("Doctor:", ["Todos"] + list(citas_df["doctor"].dropna().unique()))
        with f2:
            filtro_estado = st.selectbox("Estado:", ["Todos"] + list(citas_df["estado"].dropna().unique()))
        with f3:
            fecha_filtro = st.date_input("Fecha:", value=hoy)
            todo_historial = st.checkbox("Mostrar todo el historial")

        df_f = citas_df.copy()
        if filtro_doc != "Todos":
            df_f = df_f[df_f["doctor"] == filtro_doc]
        if filtro_estado != "Todos":
            df_f = df_f[df_f["estado"] == filtro_estado]
        if not todo_historial:
            df_f = df_f[df_f["fecha"] == fecha_filtro]

        st.subheader(f"📋 Citas ({len(df_f)})")
        if df_f.empty:
            st.warning("No hay citas con esos filtros.")
        else:
            st.dataframe(df_f[["id", "fecha", "hora", "paciente", "doctor", "estado", "motivo_consulta"]].rename(
                columns={"id": "Cita ID", "fecha": "Fecha", "hora": "Hora", "paciente": "Paciente",
                         "doctor": "Odontólogo", "estado": "Estado", "motivo_consulta": "Motivo"}
            ), use_container_width=True, hide_index=True)
            st.download_button("📥 Descargar CSV", df_f.to_csv(index=False).encode("utf-8"),
                               f"citas_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")


# ── VISTA: HISTORIAS CLÍNICAS ─────────────────────────────────────────────────
elif menu == "📂 Historias Clínicas":
    st.title("📂 Historial Clínico Digital")
    pacientes_df = get_pacientes()
    if pacientes_df.empty:
        st.info("No hay pacientes registrados.")
    else:
        opciones = {row["id"]: f"{row['nombre']} {row['apellido']} (Tel: {row['telefono']})"
                    for _, row in pacientes_df.iterrows()}
        pac_sel = st.selectbox("Selecciona un paciente:", list(opciones.keys()),
                                format_func=lambda x: opciones[x])
        if pac_sel:
            info = pacientes_df[pacientes_df["id"] == pac_sel].iloc[0]
            historia = supabase.table("historias_clinicas").select("*").eq("paciente_id", pac_sel).maybe_single().execute()
            if not historia.data:
                st.warning("⚠️ Sin historia clínica.")
                if st.button("Crear Historia Clínica"):
                    supabase.table("historias_clinicas").insert({"paciente_id": pac_sel}).execute()
                    st.success("Historia clínica creada.")
                    st.rerun()
            else:
                h = historia.data
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.subheader("👤 Datos Personales")
                    st.markdown(f"**Nombre:** {info['nombre']} {info['apellido']}")
                    st.markdown(f"**Teléfono (Chat ID):** `{info['telefono']}`")
                    st.markdown(f"**Email:** {info.get('email') or 'No registrado'}")
                    st.markdown(f"**Nacimiento:** {info.get('fecha_nacimiento') or 'No registrada'}")
                    st.write("---")
                    st.subheader("🏥 Antecedentes Médicos")
                    antecedentes = st.text_area("Modificar antecedentes:", value=h.get("antecedentes_medicos") or "")
                    if st.button("Guardar Antecedentes"):
                        supabase.table("historias_clinicas").update(
                            {"antecedentes_medicos": antecedentes.strip()}
                        ).eq("id", h["id"]).execute()
                        st.success("✅ Antecedentes actualizados.")
                        st.rerun()
                with col2:
                    st.subheader("📝 Evolución Clínica")
                    atenciones = supabase.table("atenciones_medicas").select("*").eq(
                        "historia_id", h["id"]
                    ).order("fecha_atencion", desc=True).execute()
                    if not atenciones.data:
                        st.info("Sin atenciones registradas.")
                    else:
                        for evo in atenciones.data:
                            fecha_evo = pd.to_datetime(evo["fecha_atencion"]).strftime("%d/%m/%Y %H:%M")
                            with st.expander(f"🩺 Atención del {fecha_evo} — Cita #{evo['cita_id']}"):
                                st.markdown(f"**Diagnóstico:**\n>{evo['diagnostico']}")
                                st.markdown(f"**Tratamiento:**\n>{evo['tratamiento_realizado']}")
                                if evo.get("observaciones"):
                                    st.markdown(f"**Observaciones:**\n_{evo['observaciones']}_")


# ── VISTA: REPORTES FINANCIEROS ───────────────────────────────────────────────
elif menu == "💰 Reportes Financieros":
    st.title("💰 Reportes Financieros")
    pagos_df = get_pagos()
    if pagos_df.empty:
        st.info("Sin transacciones registradas.")
    else:
        pagos_df["monto"] = pagos_df["monto"].astype(float)
        pagado_df = pagos_df[pagos_df["estado_pago"] == "pagado"]
        pendiente_df = pagos_df[pagos_df["estado_pago"] == "pendiente"]
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Recaudado (S/)", f"S/ {pagado_df['monto'].sum():,.2f}")
        col2.metric("Transacciones Pagadas", len(pagado_df))
        col3.metric("Pendientes", len(pendiente_df))
        st.write("---")
        g1, g2 = st.columns(2)
        with g1:
            metodos = pagado_df.groupby("metodo_pago")["monto"].sum().reset_index()
            st.plotly_chart(px.pie(metodos, values="monto", names="metodo_pago",
                                   title="Ingresos por Método de Pago",
                                   color_discrete_sequence=px.colors.qualitative.Pastel),
                            use_container_width=True)
        with g2:
            pagado_df["fecha"] = pd.to_datetime(pagado_df["fecha"]).dt.date
            ingresos = pagado_df.groupby("fecha")["monto"].sum().reset_index()
            st.plotly_chart(px.line(ingresos, x="fecha", y="monto",
                                    title="Historial de Recaudación Diaria", markers=True),
                            use_container_width=True)
        st.subheader("📋 Registro de Transacciones")
        st.dataframe(pagos_df[["id", "paciente", "monto", "metodo_pago", "estado_pago", "fecha"]].rename(
            columns={"id": "Pago ID", "paciente": "Paciente", "monto": "Monto (S/)",
                     "metodo_pago": "Método", "estado_pago": "Estado", "fecha": "Fecha"}
        ), use_container_width=True, hide_index=True)


# ── VISTA: REGISTRO DEL PERSONAL ──────────────────────────────────────────────
elif menu == "👥 Registro del Personal":
    st.title("👥 Equipo Dental & Gestión de Acceso")
    personal_df = get_personal()
    with st.expander("➕ Registrar Nuevo Miembro"):
        with st.form("reg_personal"):
            nombre = st.text_input("Nombre:")
            apellido = st.text_input("Apellido:")
            rol = st.selectbox("Rol:", ["odontologo", "recepcionista", "administrador"])
            especialidad = st.text_input("Especialidad:", value="General")
            chat_id = st.text_input("Telegram Chat ID:")
            if st.form_submit_button("Guardar"):
                if not nombre or not apellido or not chat_id:
                    st.error("Nombre, Apellido y Chat ID son obligatorios.")
                else:
                    try:
                        supabase.table("personal").insert({
                            "nombre": nombre.strip().title(),
                            "apellido": apellido.strip().title(),
                            "rol": rol,
                            "especialidad": especialidad.strip() if rol == "odontologo" else None,
                            "telefono": chat_id.strip(),
                        }).execute()
                        st.success(f"✅ {nombre} {apellido} registrado.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    if personal_df.empty:
        st.info("No hay personal registrado.")
    else:
        st.dataframe(
            personal_df[["id", "nombre", "apellido", "rol", "especialidad", "telefono"]].rename(
                columns={"id": "ID", "nombre": "Nombre", "apellido": "Apellido",
                         "rol": "Rol", "especialidad": "Especialidad", "telefono": "Chat ID"}
            ), use_container_width=True, hide_index=True
        )


# ── VISTA: PACIENTES ──────────────────────────────────────────────────────────
elif menu == "👥 Pacientes":
    st.title("👥 Pacientes Registrados")
    pacientes_df = get_pacientes()
    if pacientes_df.empty:
        st.info("No hay pacientes registrados.")
    else:
        st.dataframe(
            pacientes_df[["id", "nombre", "apellido", "telefono", "email", "fecha_nacimiento", "fecha_registro"]].rename(
                columns={"id": "ID", "nombre": "Nombre", "apellido": "Apellido",
                         "telefono": "Chat ID", "email": "Email",
                         "fecha_nacimiento": "Nacimiento", "fecha_registro": "Registro"}
            ), use_container_width=True, hide_index=True
        )
