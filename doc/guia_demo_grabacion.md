# 🦷 Guía de Demo Multi-Rol — AutomaDent Bot Telegram

> Guión paso a paso para grabar la demostración del Sistema Multiagente AutomaDent.
> Esta guía utiliza **dos cuentas de Telegram diferentes**:
> 1. **Tú como Paciente** (simulando al cliente final).
> 2. **Tu Compañero como Odontólogo** (simulando al especialista y administrador).

---

## ⚙️ Preparación Previa (antes de grabar)

1. **Asegúrate de que los contenedores estén corriendo** en el Droplet:
   ```bash
   docker ps
   ```
   Deben estar activos: `automadent-bot`, `mcp-server`, `dashboard-agentdent`

2. **Registro de identidades en la Base de Datos**:
   *   **Odontólogo (Compañero)**: Su `telegram_chat_id` debe estar en la tabla `personal` con `rol: 'odontologo'` y asignado a su nombre (ej. Pablo Asmad).
   *   **Paciente (Tú)**: Si ya estás registrado en `pacientes`, mantén tu registro. Si no, iniciarás la demo registrándote desde tu celular.

3. **Dashboard Web**:
   *   Abre el Dashboard en el navegador: `http://TU_IP_DROPLET:8502`
   *   Contraseña: `dent123`

---

## 🎬 Flujo de la Demo (Dos Roles)

### 📌 Escena 1 — Inicio de sesión del Odontólogo (Celular del Compañero)
**Acción:** Tu compañero inicia conversación con el bot escribiendo:
```
/start
```
**Resultado esperado:** El bot lo reconoce inmediatamente sin contraseñas:
> 🔑 **Sesión Administrativa Iniciada**
> Bienvenido(a) al bot interno de AutomaDent.
> Rol detectado: **ODONTOLOGO**

---

### 📌 Escena 2 — Inicio del Paciente y Registro (Tu Celular)
**Acción:** Tú (como paciente) abres el bot y escribes:
```
Quiero registrarme como paciente, mi nombre es [Tu Nombre Completo]
```
**Resultado esperado:** El bot de Recepción te da la bienvenida, crea tu historia clínica y te asigna tu `chat_id` como paciente en Supabase.
> 👤 **Registro Exitoso**
> Bienvenido a AutomaDent, [Tu Nombre]. Hemos creado tu ficha clínica.

---

### 📌 Escena 3 — El Paciente Consulta Disponibilidad y Agenda (Tu Celular)
**Acción:** Tú escribes al bot:
```
¿Qué horarios hay disponibles para mañana?
```
*(El bot te muestra los slots disponibles)*
**Acción:** Eliges uno y escribes:
```
Agendar una cita para mañana a las 10:00 AM con el odontólogo [Nombre de tu Compañero]
```
**Resultado esperado:**
*   **En tu pantalla (Paciente)**:
    > ✅ ¡Cita agendada exitosamente! Cita #X con el Dr. [Nombre de tu Compañero].
*   **En la pantalla de tu compañero (Odontólogo)**: Recibe una notificación automática al instante:
    > 🔔 **Nueva Cita Asignada**
    > Tienes una nueva cita programada con el paciente [Tu Nombre] para mañana a las 10:00 AM.

---

### 📌 Escena 4 — Odontólogo consulta sus citas (Celular del Compañero)
**Acción:** Tu compañero escribe al bot:
```
dame la lista de mis citas
```
**Resultado esperado:** El bot le muestra una lista organizada de **sus** citas asignadas para hoy/mañana. El filtro automático asegura que no vea citas de otros odontólogos.

---

### 📌 Escena 5 — Odontólogo atiende la cita y registra evolución (Celular del Compañero)
**Acción:** Al finalizar la consulta médica simulada, tu compañero escribe:
```
Registrar evolución para la cita #X: diagnóstico caries leve, tratamiento profilaxis, observaciones paciente con buena higiene
```
**Resultado esperado:**
*   **En la pantalla de tu compañero (Odontólogo)**:
    > ✅ Evolución médica guardada correctamente para la cita #X. El estado de la cita se cambió a asistida.
*   **En tu pantalla (Paciente)**: Recibes una notificación automática de que tu consulta terminó:
    > 🦷 **Tu Consulta ha Finalizado**
    > El Dr. [Nombre de tu Compañero] ha registrado tu evolución. 
    > 💰 Costo total: S/ [Monto]. Para realizar tu pago por transferencia, envía el comprobante a esta cuenta: [Datos de Cuenta].

---

### 📌 Escena 6 — Flujo de Pago y Cierre de la Cita (Ambos Celulares)
**Acción:** Tú (Paciente) escribes en tu chat:
```
Ya realicé el pago por transferencia de la cita #X, aquí está el comprobante
```
**Acción:** Tu compañero (Odontólogo) valida y registra el pago en su chat administrativo escribiendo:
```
Registrar pago de la cita #X por S/ [Monto] en transferencia
```
**Resultado esperado:** El bot de Facturación responde a tu compañero confirmando el registro de la transacción y se actualiza el estado de pago en la base de datos.

---

### 📌 Escena 7 — Dashboard Web (Pantalla de PC)
**Acción:** Muestra el Dashboard en el navegador para que se aprecie el flujo completo consolidado:
1.  **📅 Citas del Día**: La cita de la demo ahora figura como `asistida`.
2.  **💰 Reportes Financieros**: El monto de tu cita figura sumado a los ingresos diarios.
3.  **📂 Historias Clínicas**: La evolución registrada por tu compañero aparece adjuntada a tu ficha personal en tiempo real.

---

## ✅ Checklist Antes de Grabar

- [ ] Supabase configurado con los chat_ids reales de ambos dispositivos.
- [ ] Droplet en ejecución sin errores (`docker compose logs -f`).
- [ ] Tu compañero tiene preparado el guión en su celular y tú en el tuyo.
- [ ] Dashboard cargado en la computadora.

---

## 🚨 Comandos de Soporte en Servidor

Si necesitas monitorear la comunicación en tiempo real durante la preparación:
```bash
# Ver el envío de notificaciones cruzadas
docker logs -f mcp-server

# Ver el procesamiento de los agentes en el bot
docker logs -f automadent-bot
```
