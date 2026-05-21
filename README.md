# 🦷 AutomaDent — Sistema Multiagente para Clínica Dental

Sistema Multiagente (SMA) con arquitectura **Hub-and-Spoke** para automatizar la operación de una clínica dental mediante un bot de Telegram y un Dashboard Administrativo Web.

## 🏗️ Arquitectura del Sistema

```
                        📱 Telegram Bot (main.py)
                                  │
                                  ▼
      🧠 Agente Supervisor (Clasifica y valida roles en Supabase)
                                  │
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
    📋 Recepción            🩺 Asist. Médico        💰 Facturación
(Registro, Citas,           (Diagnósticos y         (Cobros y Pagos)
 Google Sheets)              Evoluciones)
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  ▼
                     ☁️ Supabase / 📊 Google Sheets
                                  ▲
                                  │
                   💻 Dashboard Streamlit (dashboard.py)
                    (Citas, Historias Clínicas, Finanzas)
```

## 📂 Estructura del Código

- `database.py`: Cliente de base de datos Supabase centralizado (singleton).
- `tools.py`: 8 herramientas CRUD con control de acceso basado en roles (RBAC) e integración nativa con Google Sheets.
- `agents.py`: Cerebro del SMA con LangGraph.
- `main.py`: Integración del bot de Telegram con ruteo de seguridad por `chat_id`.
- `notifier.py`: Envío de recordatorios automáticos de citas (Cron).
- `dashboard.py`: Aplicación Streamlit para la visualización administrativa.
- `credentials.json`: Credenciales de la Cuenta de Servicio de Google (excluida de git).

## ⚙️ Configuración de Roles y Seguridad (RBAC)

Para evitar que los pacientes accedan a diagnósticos médicos o reportes de facturación, el bot de Telegram identifica el rol del usuario utilizando su `chat_id` único:

1. **Pacientes**: Su `chat_id` debe registrarse en la tabla `pacientes` (columna `telefono`). Solo pueden ver su propio historial y agendar sus citas.
2. **Personal (Doctores, Recepcionistas, Administradores)**: Su `chat_id` debe registrarse en la tabla `personal` (columna `telefono`) junto a su rol respectivo (`rol_personal`: 'odontologo', 'recepcionista', 'administrador').
   - *Odontólogo*: Puede registrar diagnósticos y evoluciones de citas.
   - *Recepcionista / Administrador*: Puede cobrar citas, registrar pagos y exportar reportes de citas a Excel (Google Sheets).

> [!TIP]
> Puedes vincular y registrar fácilmente los `chat_id` de Telegram de tu personal clínico en la sección **Registro del Personal** dentro del Dashboard de Streamlit.

## 🚀 Instalación y Uso

### 1. Preparar Entorno Virtual e Instalar Dependencias
```bash
# Crear entorno virtual
python -m venv venv
venv\Scripts\activate

# Instalar librerías
pip install -r requirements.txt
```

### 2. Configurar Archivo `.env`
Crea un archivo `.env` en la raíz del proyecto:
```env
TELEGRAM_BOT_TOKEN=tu_token_de_telegram
GEMINI_API_KEY=tu_api_key_de_gemini
SUPABASE_SERVICE_KEY=tu_service_key_de_supabase
SUPABASE_URL=https://tu-proyecto.supabase.co
```

### 3. Configurar Credenciales de Google Sheets
Coloca tu archivo de credenciales de Google Cloud (`credentials.json`) en la raíz del proyecto para habilitar la exportación automática de citas.

---

### 💻 Ejecutar Dashboard de Streamlit
El dashboard administrativo se abre en tu navegador local para ver todas las citas, expedientes clínicos de pacientes y estados de cobro:
```bash
streamlit run dashboard.py
```
> **Contraseña de acceso por defecto**: `dent123`

### 🤖 Ejecutar Bot de Telegram
Arranca el bot de Telegram en modo interactivo:
```bash
python main.py
```

### ⏰ Ejecutar Recordatorios Automáticos (Cron)
```bash
# Ambos reportes (citas de hoy para doctores y recordatorios de mañana para pacientes)
python notifier.py
```
