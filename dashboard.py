# dashboard.py — Dashboard Web de AutomaDent
# ==============================================================================
# Aplicación web interactiva en Streamlit para el personal de la clínica.
# Permite gestionar citas, ver historias clínicas, reportes financieros
# y registrar el personal asignando su chat_id de Telegram.
#
# Para ejecutar:
#   streamlit run dashboard.py
# ==============================================================================

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from database import supabase

# Configuración de página
st.set_page_config(
    page_title="AutomaDent Dashboard",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos personalizados (CSS Premium)
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #1e293b;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #334155;
    }
    h1, h2, h3 {
        color: #38bdf8;
    }
    .css-1r6g72h {
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
#  FUNCIONES DE DATOS (LOOKUPS EN SUPABASE)
# ==============================================================================

@st.cache_data(ttl=60)
def get_citas():
    """Obtiene el listado de todas las citas registradas en Supabase."""
    citas_query = (
        supabase.table("citas")
        .select("id, fecha_hora, estado, motivo_consulta, paciente_id, odontologo_id")
        .order("fecha_hora", desc=True)
        .execute()
    )
    
    if not citas_query.data:
        return pd.DataFrame()
        
    df = pd.DataFrame(citas_query.data)
    
    # Resolver nombres de pacientes
    pacientes_query = supabase.table("pacientes").select("id, nombre, apellido").execute()
    pac_map = {p["id"]: f"{p['nombre']} {p['apellido']}" for p in (pacientes_query.data or [])}
    df["paciente"] = df["paciente_id"].map(pac_map)
    
    # Resolver nombres de doctores
    doc_query = supabase.table("personal").select("id, nombre, apellido").execute()
    doc_map = {d["id"]: f"Dr(a). {d['nombre']} {d['apellido']}" for d in (doc_query.data or [])}
    df["doctor"] = df["odontologo_id"].map(doc_map)
    
    # Formatear fecha y hora
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
    pagos_query = supabase.table("pagos").select("*").execute()
    if not pagos_query.data:
        return pd.DataFrame()
        
    df = pd.DataFrame(pagos_query.data)
    
    # Resolver detalles de la cita
    citas_df = get_citas()
    if not citas_df.empty:
        df = df.merge(citas_df[["id", "paciente", "doctor", "fecha"]], left_on="cita_id", right_on="id", how="left")
        df.rename(columns={"id_x": "id"}, inplace=True)
        df.drop(columns=["id_y"], inplace=True)
        
    return df


# ==============================================================================
#  INTERFAZ DE USUARIO (DASHBOARD)
# ==============================================================================

# Barra lateral - Navegación
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3467/3467831.png", width=80)
st.sidebar.title("AutomaDent Portal")
st.sidebar.subheader("Clínica Dental Inteligente")

menu = st.sidebar.radio(
    "Navegación",
    ["📅 Citas del Día", "📂 Historias Clínicas", "💰 Reportes Financieros", "👥 Registro del Personal", "👥 Pacientes"]
)

# Login simple (Contraseña maestra para personal)
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("<h2 style='text-align: center;'>🔐 Acceso al Portal Administrativo</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password = st.text_input("Ingresa la Contraseña de la Clínica:", type="password")
        if st.button("Iniciar Sesión"):
            # Para fines del ejercicio usamos una contraseña simple.
            # Puedes definir esto en el archivo .env.
            if password == "dent123":
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta. Contacta al Administrador.")
    st.stop()


# ──────────────────────────────────────────────────────────────────────────────
#  VISTA: CITAS DEL DÍA
# ──────────────────────────────────────────────────────────────────────────────
if menu == "📅 Citas del Día":
    st.title("📅 Panel de Control de Citas")
    
    citas_df = get_citas()
    
    if citas_df.empty:
        st.info("Aún no hay citas registradas en la base de datos.")
    else:
        # Métricas principales
        hoy = datetime.now().date()
        citas_hoy = citas_df[citas_df["fecha"] == hoy]
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Citas Hoy", len(citas_hoy))
        col2.metric("Pendientes/Programadas", len(citas_df[citas_df["estado"] == "programada"]))
        col3.metric("Confirmadas", len(citas_df[citas_df["estado"] == "confirmada"]))
        col4.metric("Atendidas/Asistidas", len(citas_df[citas_df["estado"] == "asistida"]))
        
        st.write("---")
        
        # Filtros
        st.subheader("🔍 Filtros de Búsqueda")
        filtro_col1, filtro_col2, filtro_col3 = st.columns(3)
        
        with filtro_col1:
            filtro_doc = st.selectbox("Filtrar por Doctor:", ["Todos"] + list(citas_df["doctor"].dropna().unique()))
        with filtro_col2:
            filtro_estado = st.selectbox("Filtrar por Estado:", ["Todos"] + list(citas_df["estado"].dropna().unique()))
        with filtro_col3:
            fecha_filtro = st.date_input("Fecha específica:", value=hoy)
            todo_historial = st.checkbox("Mostrar todo el historial (ignorar fecha)")

        # Aplicar filtros
        df_filtrado = citas_df.copy()
        if filtro_doc != "Todos":
            df_filtrado = df_filtrado[df_filtrado["doctor"] == filtro_doc]
        if filtro_estado != "Todos":
            df_filtrado = df_filtrado[df_filtrado["estado"] == filtro_estado]
        if not todo_historial:
            df_filtrado = df_filtrado[df_filtrado["fecha"] == fecha_filtro]
            
        st.subheader(f"📋 Citas Encontradas ({len(df_filtrado)})")
        if df_filtrado.empty:
            st.warning("No se encontraron citas con los filtros seleccionados.")
        else:
            # Mostrar tabla limpia
            st.dataframe(
                df_filtrado[["id", "fecha", "hora", "paciente", "doctor", "estado", "motivo_consulta"]].rename(
                    columns={
                        "id": "Cita ID",
                        "fecha": "Fecha",
                        "hora": "Hora",
                        "paciente": "Paciente",
                        "doctor": "Odontólogo",
                        "estado": "Estado",
                        "motivo_consulta": "Motivo"
                    }
                ),
                use_container_width=True,
                hide_index=True
            )
            
            # Exportar rápido a Excel/CSV local
            csv = df_filtrado.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar Reporte CSV",
                data=csv,
                file_name=f"reporte_citas_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )


# ──────────────────────────────────────────────────────────────────────────────
#  VISTA: HISTORIAS CLÍNICAS (MAESTRO)
# ──────────────────────────────────────────────────────────────────────────────
elif menu == "📂 Historias Clínicas":
    st.title("📂 Historial Clínico Digital")
    
    pacientes_df = get_pacientes()
    
    if pacientes_df.empty:
        st.info("No hay pacientes registrados.")
    else:
        # Buscador interactivo
        opciones_pacientes = {
            row["id"]: f"{row['nombre']} {row['apellido']} (Telf: {row['telefono']})"
            for _, row in pacientes_df.iterrows()
        }
        
        paciente_seleccionado = st.selectbox(
            "Selecciona o busca un paciente para ver su expediente:",
            options=list(opciones_pacientes.keys()),
            format_func=lambda x: opciones_pacientes[x]
        )
        
        if paciente_seleccionado:
            # Detalles del paciente
            paciente_info = pacientes_df[pacientes_df["id"] == paciente_seleccionado].iloc[0]
            
            # Consultar Historia Clínica
            historia_query = (
                supabase.table("historias_clinicas")
                .select("*")
                .eq("paciente_id", paciente_seleccionado)
                .maybe_single()
                .execute()
            )
            
            if not historia_query.data:
                st.warning("⚠️ Este paciente no tiene una historia clínica asociada.")
                if st.button("Crear Historia Clínica ahora"):
                    supabase.table("historias_clinicas").insert({"paciente_id": paciente_seleccionado}).execute()
                    st.success("Historia clínica creada.")
                    st.rerun()
            else:
                historia = historia_query.data
                
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.subheader("👤 Datos Personales")
                    st.markdown(f"**Nombre:** {paciente_info['nombre']} {paciente_info['apellido']}")
                    st.markdown(f"**Teléfono (Telegram ID):** `{paciente_info['telefono']}`")
                    st.markdown(f"**Email:** {paciente_info.get('email') or 'No registrado'}")
                    st.markdown(f"**Fecha Nacimiento:** {paciente_info.get('fecha_nacimiento') or 'No registrada'}")
                    st.markdown(f"**Fecha Registro:** {paciente_info['fecha_registro'][:10]}")
                    
                    st.write("---")
                    
                    # Antecedentes Médicos (Editable)
                    st.subheader("🏥 Antecedentes Médicos")
                    antecedentes = st.text_area(
                        "Modificar antecedentes generales (Alergias, enfermedades crónicas, etc.):",
                        value=historia.get("antecedentes_medicos") or ""
                    )
                    if st.button("Guardar Antecedentes"):
                        supabase.table("historias_clinicas").update({
                            "antecedentes_medicos": antecedentes.strip()
                        }).eq("id", historia["id"]).execute()
                        st.success("✅ Antecedentes actualizados correctamente.")
                        st.rerun()
                
                with col2:
                    st.subheader("📝 Evolución y Atenciones Médicas")
                    
                    # Obtener atenciones médicas vinculadas a esta historia
                    atenciones_query = (
                        supabase.table("atenciones_medicas")
                        .select("*")
                        .eq("historia_id", historia["id"])
                        .order("fecha_atencion", desc=True)
                        .execute()
                    )
                    
                    if not atenciones_query.data:
                        st.info("Aún no se registran atenciones clínicas para este paciente.")
                    else:
                        for evo in atenciones_query.data:
                            fecha_evo = pd.to_datetime(evo["fecha_atencion"]).strftime("%d/%m/%Y %H:%M")
                            with st.expander(f"🩺 Atención del {fecha_evo} — Cita #{evo['cita_id']}"):
                                st.markdown(f"**Diagnóstico:**\n>{evo['diagnostico']}")
                                st.markdown(f"**Tratamiento Realizado:**\n>{evo['tratamiento_realizado']}")
                                if evo.get("observaciones"):
                                    st.markdown(f"**Observaciones:**\n_{evo['observaciones']}_")


# ──────────────────────────────────────────────────────────────────────────────
#  VISTA: REPORTES FINANCIEROS
# ──────────────────────────────────────────────────────────────────────────────
elif menu == "💰 Reportes Financieros":
    st.title("💰 Reportes y Métricas Financieras")
    
    pagos_df = get_pagos()
    
    if pagos_df.empty:
        st.info("Aún no se registran transacciones de pagos.")
    else:
        # Convertir montos a numéricos
        pagos_df["monto"] = pagos_df["monto"].astype(float)
        
        pagado_df = pagos_df[pagos_df["estado_pago"] == "pagado"]
        pendiente_df = pagos_df[pagos_df["estado_pago"] == "pendiente"]
        
        # Tarjetas de recaudación
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Recaudado (S/)", f"S/ {pagado_df['monto'].sum():,.2f}")
        col2.metric("Transacciones Pagadas", len(pagado_df))
        col3.metric("Transacciones Pendientes", len(pendiente_df))
        
        st.write("---")
        
        # Gráficos
        st.subheader("📊 Distribución de Pagos")
        g_col1, g_col2 = st.columns(2)
        
        with g_col1:
            # Gráfico por método de pago
            metodos_df = pagado_df.groupby("metodo_pago")["monto"].sum().reset_index()
            fig_metodos = px.pie(
                metodos_df,
                values="monto",
                names="metodo_pago",
                title="Ingresos por Método de Pago",
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            st.plotly_chart(fig_metodos, use_container_width=True)
            
        with g_col2:
            # Gráfico de ingresos diarios/por fecha
            pagado_df["fecha"] = pd.to_datetime(pagado_df["fecha"]).dt.date
            ingresos_fecha = pagado_df.groupby("fecha")["monto"].sum().reset_index()
            fig_line = px.line(
                ingresos_fecha,
                x="fecha",
                y="monto",
                title="Historial de Recaudación Diaria",
                labels={"monto": "Monto Recaudado (S/)", "fecha": "Fecha"},
                markers=True
            )
            st.plotly_chart(fig_line, use_container_width=True)
            
        # Listado detallado de pagos
        st.subheader("📋 Registro de Transacciones")
        st.dataframe(
            pagos_df[["id", "paciente", "monto", "metodo_pago", "estado_pago", "fecha"]].rename(
                columns={
                    "id": "Pago ID",
                    "paciente": "Paciente",
                    "monto": "Monto (S/)",
                    "metodo_pago": "Método",
                    "estado_pago": "Estado",
                    "fecha": "Fecha de Pago"
                }
            ),
            use_container_width=True,
            hide_index=True
        )


# ──────────────────────────────────────────────────────────────────────────────
#  VISTA: REGISTRO DEL PERSONAL (Clave para vincular Telegram chat_id)
# ──────────────────────────────────────────────────────────────────────────────
elif menu == "👥 Registro del Personal":
    st.title("👥 Equipo Dental & Gestión de Acceso")
    st.write("Aquí puedes registrar nuevos miembros del personal y asignarles su **ID de Telegram (chat_id)** para que el bot los reconozca con su respectivo rol.")
    
    personal_df = get_personal()
    
    # Formulario para registrar personal
    with st.expander("➕ Registrar Nuevo Miembro del Personal"):
        with st.form("registro_personal_form"):
            nombre = st.text_input("Nombre:")
            apellido = st.text_input("Apellido:")
            rol = st.selectbox("Rol:", ["odontologo", "recepcionista", "administrador"])
            especialidad = st.text_input("Especialidad (solo para odontólogos, ej: Ortodoncia):", value="General")
            telegram_chat_id = st.text_input("Telegram Chat ID / Teléfono (Ej: 987654321):")
            
            submit = st.form_submit_button("Guardar Miembro")
            
            if submit:
                if not nombre or not apellido or not telegram_chat_id:
                    st.error("Todos los campos obligatorios (*Nombre*, *Apellido*, *Telegram Chat ID*) deben llenarse.")
                else:
                    # Insertar en Supabase
                    nuevo_registro = {
                        "nombre": nombre.strip().title(),
                        "apellido": apellido.strip().title(),
                        "rol": rol,
                        "especialidad": especialidad.strip() if rol == "odontologo" else None,
                        "telefono": telegram_chat_id.strip()
                    }
                    try:
                        supabase.table("personal").insert(nuevo_registro).execute()
                        st.success(f"✅ ¡{nombre} {apellido} registrado exitosamente con el rol '{rol}'!")
                        st.cache_data.clear() # Limpiar caché para forzar recarga
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
                        
    # Mostrar el equipo actual
    st.subheader("👥 Personal Activo y Cuentas Vinculadas")
    if personal_df.empty:
        st.info("No hay miembros del personal registrados.")
    else:
        st.dataframe(
            personal_df[["id", "nombre", "apellido", "rol", "especialidad", "telefono"]].rename(
                columns={
                    "id": "Personal ID",
                    "nombre": "Nombre",
                    "apellido": "Apellido",
                    "rol": "Rol Asignado",
                    "especialidad": "Especialidad",
                    "telefono": "Telegram Chat ID (Teléfono)"
                }
            ),
            use_container_width=True,
            hide_index=True
        )


# ──────────────────────────────────────────────────────────────────────────────
#  VISTA: PACIENTES
# ──────────────────────────────────────────────────────────────────────────────
elif menu == "👥 Pacientes":
    st.title("👥 Pacientes Registrados")
    st.write("Visualización rápida de los pacientes y sus datos de contacto de Telegram.")
    
    pacientes_df = get_pacientes()
    
    if pacientes_df.empty:
        st.info("No hay pacientes registrados.")
    else:
        st.dataframe(
            pacientes_df[["id", "nombre", "apellido", "telefono", "email", "fecha_nacimiento", "fecha_registro"]].rename(
                columns={
                    "id": "Paciente ID",
                    "nombre": "Nombre",
                    "apellido": "Apellido",
                    "telefono": "Telegram Chat ID",
                    "email": "Email",
                    "fecha_nacimiento": "Fecha Nacimiento",
                    "fecha_registro": "Fecha de Registro"
                }
            ),
            use_container_width=True,
            hide_index=True
        )
