# 🦷 Guía de Configuración de Usuarios y Roles para la Demo de AutomaDent

Esta guía detalla los pasos para registrar y configurar usuarios con diferentes roles para poder probar el flujo completo del **Sistema Multiagente AutomaDent** en su bot de Telegram y panel web (Streamlit).

---

## 🔑 Conceptos Clave de Seguridad (RBAC)

El sistema utiliza control de acceso basado en roles (RBAC). Cuando un usuario envía un mensaje al bot de Telegram, el sistema busca su **Telegram Chat ID** en la base de datos de Supabase para determinar qué rol tiene:

| Rol | Tabla de Origen | Permisos Principales |
| :--- | :--- | :--- |
| **`paciente_no_registrado`** | *No existe en la BD* | Registrarse en el sistema, consultar disponibilidad de horarios. |
| **`paciente`** | `pacientes` | Ver disponibilidad, agendar citas, consultar su propia historia clínica. |
| **`odontologo`** | `personal` | Cambiar estado de citas a `asistida`/`no_show`, registrar evoluciones y diagnósticos de citas. |
| **`recepcionista`** | `personal` | Ver disponibilidad, agendar citas, ver historias de cualquier paciente, registrar pagos, exportar reportes a Google Sheets. |
| **`administrador`** | `personal` | Todos los permisos de la recepcionista + visualización del panel financiero total. |

---

## 🛠️ Paso 1: Obtener tu Telegram Chat ID

Para que el sistema te reconozca con un rol específico, necesitas saber tu identificador único de Telegram (**Chat ID**):

1. **Vía Bots de Telegram:**
   - Abre Telegram y busca el bot `@userinfobot` o `@raw_data_bot`.
   - Inicia conversación con ellos (`/start`). Te responderán indicando tu **Id** (un número de 9 o 10 dígitos, por ejemplo: `123456789`).
2. **Vía Consola de Ejecución:**
   - Si ya tienes el bot corriendo (`python main.py`), escríbele cualquier mensaje en Telegram.
   - En la consola de tu terminal verás un log similar a este:
     ```text
     2026-05-22 10:15:30 - main - INFO - 📩 Mensaje recibido de 123456789 | Rol: paciente_no_registrado | Texto: Hola...
     ```
     El número después de "Mensaje recibido de" es tu **Telegram Chat ID**.

---

## 👥 Paso 2: Registrar Usuarios y Asignar Roles

### Opción A: A través del Dashboard Web (Recomendado para Personal)
El panel administrativo permite registrar miembros del equipo médico y administrativo de forma visual:

1. Asegúrate de ejecutar el dashboard:
   ```bash
   streamlit run dashboard.py
   ```
2. Entra al dashboard en tu navegador (usa la contraseña de acceso: `dent123`).
3. Ve a la sección **"👥 Registro del Personal"** en el menú lateral.
4. Despliega la opción **"➕ Registrar Nuevo Miembro del Personal"**.
5. Rellena el formulario:
   - **Nombre y Apellido**
   - **Rol:** Elige entre `odontologo`, `recepcionista` o `administrador`.
   - **Especialidad:** (Solo si es odontólogo, ej: *Ortodoncia*, *Endodoncia* o déjalo como *General*).
   - **Telegram Chat ID / Teléfono:** Pega aquí el **Chat ID** que obtuviste en el Paso 1.
6. Presiona **Guardar Miembro**. ¡Listo! Ahora cuando escribas al bot, este te saludará con tu rol administrativo.

---

### Opción B: Registro de Pacientes (Vía Telegram)
Para simular el flujo de un paciente que ingresa por primera vez:

1. Escríbele al bot de Telegram: `Quiero registrarme` o `Registrarme`.
2. El bot (Agente de Recepción) iniciará un diálogo interactivo solicitando tus datos paso a paso (Nombre, Apellido, Email, Fecha de nacimiento).
3. Una vez finalizado el registro, se creará automáticamente un registro en la tabla `pacientes` asociando tu Telegram Chat ID en la columna `telefono`.
4. El bot te confirmará que tu historia clínica vacía ha sido creada de forma segura.

---

### Opción C: Inserción Directa en Base de Datos (SQL / Supabase)
Si prefieres poblar la base de datos de manera directa desde la consola SQL o el panel de Supabase:

* **Para registrar un Odontólogo:**
  ```sql
  INSERT INTO personal (nombre, apellido, rol, especialidad, telefono)
  VALUES ('Juan', 'Pérez', 'odontologo', 'Ortodoncia', 'TU_CHAT_ID_AQUÍ');
  ```

* **Para registrar un Recepcionista / Administrador:**
  ```sql
  INSERT INTO personal (nombre, apellido, rol, telefono)
  VALUES ('Ana', 'Gómez', 'recepcionista', 'TU_CHAT_ID_AQUÍ');
  ```

* **Para registrar un Paciente:**
  ```sql
  -- 1. Insertar el paciente
  INSERT INTO pacientes (nombre, apellido, telefono, email, fecha_nacimiento)
  VALUES ('Carlos', 'Sánchez', 'TU_CHAT_ID_AQUÍ', 'carlos@email.com', '1995-04-12')
  RETURNING id;
  
  -- 2. Crear su historia clínica (usa el ID retornado en el paso anterior)
  INSERT INTO historias_clinicas (paciente_id)
  VALUES (ID_PACIENTE_RETORNADO);
  ```

---

## 🧪 Paso 3: Probar el flujo completo en la Demo

Una vez que tengas tu cuenta configurada con los distintos roles, puedes probar los siguientes escenarios interactuando con el bot de Telegram:

### 1. Escenario Paciente (Rol: `paciente`)
* **Acción:** Escribe `¿Qué horarios hay disponibles para mañana?` o `Quiero agendar una cita con el doctor Juan Pérez para mañana a las 10:00 AM para una limpieza`.
* **Resultado esperado:** El bot consultará la disponibilidad en Supabase, te mostrará los horarios y, si confirmas, registrará la cita asignándole un ID.

### 2. Escenario Odontólogo (Rol: `odontologo`)
* **Acción 1:** Escribe `Actualizar el estado de la cita #1 a asistida`.
* **Resultado esperado:** El bot cambiará el estado de la cita a `asistida` (requisito para poder registrar una evolución médica).
* **Acción 2:** Escribe `Registrar evolución para la cita #1: Paciente presenta ligera sensibilidad, se realiza profilaxis simple`.
* **Resultado esperado:** El Agente Médico guardará el diagnóstico y tratamiento en la tabla `atenciones_medicas` bajo la historia clínica de ese paciente.
* **Acción de Seguridad:** Si intentas escribir `Quiero cobrar la cita #1` siendo odontólogo, el bot te indicará que no tienes permisos y que es tarea del Agente de Facturación.

### 3. Escenario Recepcionista (Rol: `recepcionista` / `administrador`)
* **Acción 1:** Escribe `Registrar pago de la cita #1 por S/ 150 en efectivo`.
* **Resultado esperado:** El Agente Financiero registrará la transacción en la tabla `pagos` con estado `pagado`.
* **Acción 2:** Escribe `Exportar las citas de hoy a Excel y compartir al correo clinica.demo@gmail.com`.
* **Resultado esperado:** El bot creará un Google Sheet mediante la API, insertará las citas del día y compartirá el acceso al correo provisto (requiere que el archivo `credentials.json` esté configurado).

---

## 📌 Comandos del Sistema para la Ejecución de la Demo

1. **Iniciar el bot de Telegram:**
   ```bash
   python main.py
   ```
2. **Iniciar el Dashboard Web:**
   ```bash
   streamlit run dashboard.py
   ```
3. **Ejecutar notificaciones proactivas de prueba:**
   * Alertas de citas del día a doctores:
     ```bash
     python notifier.py --doctores
     ```
   * Recordatorios de citas de mañana a pacientes:
     ```bash
     python notifier.py --recordatorios
     ```
