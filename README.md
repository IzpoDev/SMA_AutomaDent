# 🦷 AutomaDent — Sistema Multiagente para Clínica Dental

Sistema Multiagente (SMA) con arquitectura **Hub-and-Spoke** para automatizar la operación de una clínica dental mediante un bot de Telegram.

## 🏗️ Arquitectura

```
📱 Telegram Bot (main.py)
    │
    ▼
🧠 Agente Supervisor ──► Clasifica la intención del mensaje
    │
    ├──► 📋 Agente Recepción     → Registro, citas, disponibilidad
    ├──► 🩺 Agente Asist. Médico → Cierre clínico, evoluciones
    └──► 💰 Agente Facturación   → Pagos y cobros
    
⏰ Notificador (notifier.py) → Alertas proactivas vía Cron
```

## 📁 Estructura de Archivos

| Archivo | Descripción |
|---|---|
| `database.py` | Cliente Supabase centralizado (singleton) |
| `tools.py` | 7 herramientas CRUD con seguridad por `chat_id` |
| `agents.py` | Grafo LangGraph con 4 agentes + system prompts |
| `main.py` | Bot de Telegram (Polling) |
| `notifier.py` | Alertas proactivas (Cron standalone) |
| `schema.sql` | Esquema SQL de referencia (ya desplegado en Supabase) |

## 🛠️ Tecnologías

- **Python** 3.13.7
- **LangChain** + **LangGraph** — Orquestación multiagente
- **Google Gemini** (gemini-2.0-flash) — LLM
- **Supabase** (PostgreSQL) — Base de datos
- **python-telegram-bot** — Integración con Telegram
- **httpx** — Cliente HTTP async para notificaciones

## ⚡ Instalación

```bash
# 1. Clonar el repositorio
git clone <tu-repo-url>
cd Proyecto-Automa-Dent

# 2. Crear entorno virtual
python -m venv venv

# 3. Activar entorno virtual
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 4. Instalar dependencias
pip install -r requirements.txt
```

## ⚙️ Configuración

Crear un archivo `.env` en la raíz del proyecto:

```env
TELEGRAM_BOT_TOKEN=tu_token_de_telegram
GEMINI_API_KEY=tu_api_key_de_gemini
SUPABASE_SERVICE_KEY=tu_service_key_de_supabase
SUPABASE_URL=https://tu-proyecto.supabase.co
```

## 🚀 Ejecución

### Bot de Telegram (principal)
```bash
python main.py
```

### Notificador proactivo (Cron)
```bash
# Ambas alertas
python notifier.py

# Solo alertas a doctores (citas del día)
python notifier.py --doctores

# Solo recordatorios a pacientes (citas de mañana)
python notifier.py --recordatorios
```

### Cron (Linux)
```bash
# Alertas a doctores — todos los días a las 7:00 AM
0 7 * * * cd /ruta/proyecto && python notifier.py --doctores

# Recordatorios a pacientes — todos los días a las 7:00 PM
0 19 * * * cd /ruta/proyecto && python notifier.py --recordatorios
```

## 🗄️ Base de Datos

6 tablas en Supabase (PostgreSQL):

- **pacientes** — Clientes de la clínica (`telefono` = chat_id de Telegram)
- **personal** — Odontólogos, recepcionistas, administradores
- **citas** — Reservas (flujo: programada → confirmada → asistida)
- **historias_clinicas** — Expediente maestro (1:1 con pacientes)
- **atenciones_medicas** — Evoluciones por cita asistida
- **pagos** — Registro financiero (1:1 con citas)

## 🤖 Agentes

| Agente | Rol | Herramientas |
|---|---|---|
| **Supervisor** | Router de intenciones | Ninguna (solo clasifica) |
| **Recepción** | Onboarding & Booking | `crear_paciente_y_historia`, `consultar_disponibilidad_agenda`, `agendar_cita`, `consultar_historial_paciente` |
| **Asist. Médico** | Cierre clínico | `actualizar_estado_cita`, `registrar_evolucion_medica` |
| **Facturación** | Cobros & Recibos | `registrar_pago` |
| **Notificador** | Alertas proactivas | `alertar_doctores_citas_dia`, `recordar_pacientes_citas` |

## 📜 Licencia

Proyecto académico — Uso educativo.
