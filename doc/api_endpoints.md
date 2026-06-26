# 📡 Documentación de Endpoints — AutomaDent API REST

**Base URL (desarrollo):** `http://localhost:8000`  
**Documentación interactiva (Swagger):** `http://localhost:8000/docs`  
**Versión:** 1.0.0

---

## 🌐 Contexto de Consumo Web (Frontend)

Para consumir esta API desde una aplicación web (Angular, React, Vue, etc.), ten en cuenta lo siguiente:

1. **CORS Habilitado:** La API (FastAPI) ya tiene configurado `CORSMiddleware` para permitir peticiones desde cualquier origen (`*`) durante el desarrollo. No deberías tener bloqueos por CORS al probar localmente.
2. **Flujo de Autenticación:** 
   - El frontend debe primero hacer un `POST` a `/api/auth/login` con `username` y `password` en formato JSON.
   - Si las credenciales son correctas, la API devolverá un `access_token` (JWT).
   - El frontend debe guardar este token (por ejemplo, en `localStorage` o `sessionStorage`).
3. **Peticiones Protegidas:** Para consumir cualquier otro endpoint, el frontend debe adjuntar el token guardado en las cabeceras HTTP de la petición, específicamente en la cabecera `Authorization` usando el formato `Bearer <token>`.
4. **Formato de Datos:** Todas las peticiones `POST` y `PUT` esperan recibir y enviar datos en formato `application/json`.

**Ejemplo de Petición con Fetch API (JavaScript):**
```javascript
// Ejemplo para obtener la lista de pacientes
const token = localStorage.getItem('access_token');

fetch('http://localhost:8000/api/pacientes/', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
})
.then(response => response.json())
.then(data => console.log(data));
```

---

## 🔐 Autenticación

Todos los endpoints (excepto `/api/auth/login`) requieren el header:

```
Authorization: Bearer <access_token>
```

El token se obtiene al hacer login y expira en **8 horas**.

---

## 📑 Índice de Endpoints

| Método | Endpoint | Descripción | Rol Mínimo |
|:---|:---|:---|:---|
| `POST` | `/api/auth/login` | Iniciar sesión y obtener JWT | Público |
| `GET` | `/api/auth/me` | Datos del usuario autenticado | Cualquier staff |
| `GET` | `/api/usuarios/` | Listar cuentas del sistema | Administrador |
| `POST` | `/api/usuarios/` | Crear cuenta de usuario | Administrador |
| `DELETE` | `/api/usuarios/{id}` | Eliminar cuenta de usuario | Administrador |
| `GET` | `/api/personal/` | Listar personal | Cualquier staff |
| `GET` | `/api/personal/{id}` | Detalle de miembro del personal | Cualquier staff |
| `POST` | `/api/personal/` | Registrar nuevo personal | Administrador |
| `PUT` | `/api/personal/{id}` | Actualizar personal | Administrador |
| `DELETE` | `/api/personal/{id}` | Eliminar personal | Administrador |
| `GET` | `/api/pacientes/` | Listar pacientes | Cualquier staff |
| `GET` | `/api/pacientes/{id}` | Detalle de paciente | Cualquier staff |
| `POST` | `/api/pacientes/` | Registrar paciente | Cualquier staff |
| `PUT` | `/api/pacientes/{id}` | Actualizar paciente | Cualquier staff |
| `DELETE` | `/api/pacientes/{id}` | Eliminar paciente | Cualquier staff |
| `GET` | `/api/historias/{paciente_id}` | Historia clínica completa | Cualquier staff |
| `PUT` | `/api/historias/{paciente_id}/antecedentes` | Actualizar antecedentes | Cualquier staff |
| `POST` | `/api/historias/atenciones` | Registrar atención médica | Cualquier staff |
| `GET` | `/api/citas/disponibilidad` | Consultar disponibilidad | Cualquier staff |
| `GET` | `/api/citas/` | Listar citas | Cualquier staff |
| `POST` | `/api/citas/` | Crear nueva cita | Cualquier staff |
| `PUT` | `/api/citas/{id}/estado` | Cambiar estado de cita | Cualquier staff |
| `PUT` | `/api/citas/{id}` | Actualizar datos de cita | Cualquier staff |
| `DELETE` | `/api/citas/{id}` | Eliminar cita | Cualquier staff |
| `GET` | `/api/pagos/` | Listar pagos | Cualquier staff |
| `POST` | `/api/pagos/` | Registrar pago | Cualquier staff |

---

## 🔑 Autenticación (`/api/auth`)

### `POST /api/auth/login`
Autentica a un usuario del sistema y retorna un token JWT.

**Request Body:**
```json
{
  "username": "admin@automadent.com",
  "password": "mi_contrasena_segura"
}
```

**Response 200:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "usuario_id": 1,
  "username": "admin@automadent.com",
  "rol": "administrador",
  "personal_id": null,
  "nombre_completo": null
}
```

**Response 401 (Credenciales inválidas):**
```json
{
  "detail": "Credenciales inválidas."
}
```

---

### `GET /api/auth/me`
Retorna el perfil del usuario autenticado a partir del token JWT.

**Response 200:**
```json
{
  "usuario_id": "1",
  "username": "admin@automadent.com",
  "rol": "administrador",
  "personal_id": null
}
```

---

## 👥 Usuarios del Sistema (`/api/usuarios`)

### `GET /api/usuarios/`
Lista todas las cuentas de usuario registradas. Solo para administradores.

**Response 200:**
```json
{
  "total": 2,
  "usuarios": [
    {
      "id": 1,
      "username": "admin@automadent.com",
      "personal_id": null,
      "nombre_personal": null,
      "rol": "administrador"
    },
    {
      "id": 2,
      "username": "dr.perez",
      "personal_id": 3,
      "nombre_personal": "Juan Pérez",
      "rol": "odontologo"
    }
  ]
}
```

---

### `POST /api/usuarios/`
Crea una nueva cuenta de acceso al sistema web.

**Request Body (con personal_id):**
```json
{
  "username": "recepcionista01",
  "password": "clave_segura_123",
  "personal_id": 5
}
```

**Request Body (sin personal_id — administrador general):**
```json
{
  "username": "admin@automadent.com",
  "password": "admin_seguro_456"
}
```

**Response 201:**
```json
{
  "mensaje": "Usuario creado exitosamente.",
  "usuario": {
    "id": 3,
    "username": "recepcionista01",
    "personal_id": 5
  }
}
```

**Response 409 (Username duplicado):**
```json
{
  "detail": "El username 'recepcionista01' ya está en uso."
}
```

**Response 404 (personal_id no existe):**
```json
{
  "detail": "No existe un miembro del personal con ID 5."
}
```

---

### `DELETE /api/usuarios/{id}`
Elimina una cuenta de usuario. Su registro en `personal` no se ve afectado.

**Response 200:**
```json
{
  "mensaje": "Usuario 'recepcionista01' eliminado exitosamente."
}
```

---

## 🏥 Personal (`/api/personal`)

### `GET /api/personal/`
Retorna el listado del equipo de la clínica.

**Response 200:**
```json
{
  "total": 3,
  "personal": [
    {
      "id": 1,
      "nombre": "Juan",
      "apellido": "Pérez",
      "rol": "odontologo",
      "especialidad": "Ortodoncia",
      "telefono": "987654321"
    },
    {
      "id": 2,
      "nombre": "Ana",
      "apellido": "Gómez",
      "rol": "recepcionista",
      "especialidad": "General",
      "telefono": "912345678"
    }
  ]
}
```

---

### `GET /api/personal/{id}`
Retorna el detalle de un miembro del personal.

**Response 200:**
```json
{
  "id": 1,
  "nombre": "Juan",
  "apellido": "Pérez",
  "rol": "odontologo",
  "especialidad": "Ortodoncia",
  "telefono": "987654321"
}
```

---

### `POST /api/personal/`
Registra un nuevo miembro del personal. Puede incluir la creación de su cuenta web simultáneamente.

**Request Body (solo personal, sin cuenta web):**
```json
{
  "nombre": "Carlos",
  "apellido": "López",
  "rol": "odontologo",
  "especialidad": "Endodoncia",
  "telefono": "999888777"
}
```

**Request Body (personal + cuenta web en una sola llamada):**
```json
{
  "nombre": "María",
  "apellido": "Torres",
  "rol": "recepcionista",
  "especialidad": "General",
  "telefono": "911222333",
  "crear_usuario": {
    "username": "maria.torres",
    "password": "clave_segura_789"
  }
}
```

**Response 201:**
```json
{
  "mensaje": "Personal registrado exitosamente.",
  "personal": {
    "id": 4,
    "nombre": "María",
    "apellido": "Torres",
    "rol": "recepcionista",
    "especialidad": "General",
    "telefono": "911222333"
  },
  "usuario": {
    "id": 5,
    "username": "maria.torres"
  }
}
```

> Si no se envía `crear_usuario`, el campo `usuario` en la respuesta será `null`.

---

### `PUT /api/personal/{id}`
Actualiza campos del perfil de un miembro del personal. Solo se actualizan los campos enviados.

**Request Body:**
```json
{
  "especialidad": "Periodoncia",
  "telefono": "955666777"
}
```

**Response 200:**
```json
{
  "mensaje": "Personal actualizado exitosamente.",
  "personal": {
    "id": 1,
    "nombre": "Juan",
    "apellido": "Pérez",
    "rol": "odontologo",
    "especialidad": "Periodoncia",
    "telefono": "955666777"
  }
}
```

---

### `DELETE /api/personal/{id}`
Elimina a un miembro del personal. Su cuenta de usuario quedará con `personal_id = NULL`.

**Response 200:**
```json
{
  "mensaje": "Personal 'Juan Pérez' eliminado exitosamente."
}
```

---

## 👤 Pacientes (`/api/pacientes`)

### `GET /api/pacientes/`
Lista los pacientes. Acepta el parámetro de búsqueda `buscar`.

**Query Params opcionales:**
- `buscar=carlos` — filtra por nombre, apellido o teléfono
- `limite=50` — máximo de resultados (default: 50, máx: 200)

**Response 200:**
```json
{
  "total": 2,
  "pacientes": [
    {
      "id": 1,
      "nombre": "Carlos",
      "apellido": "Sánchez",
      "telefono": "123456789",
      "email": "carlos@email.com",
      "fecha_nacimiento": "1995-04-12",
      "fecha_registro": "2026-05-20T10:30:00+00:00"
    }
  ]
}
```

---

### `GET /api/pacientes/{id}`
Detalle de un paciente por su ID.

**Response 200:**
```json
{
  "id": 1,
  "nombre": "Carlos",
  "apellido": "Sánchez",
  "telefono": "123456789",
  "email": "carlos@email.com",
  "fecha_nacimiento": "1995-04-12",
  "fecha_registro": "2026-05-20T10:30:00+00:00"
}
```

---

### `POST /api/pacientes/`
Registra un nuevo paciente y crea automáticamente su historia clínica vacía.

> [!IMPORTANT]
> El campo `telefono` es el identificador de Telegram (chat_id). Debe ser único en el sistema.

**Request Body:**
```json
{
  "nombre": "Laura",
  "apellido": "Ramírez",
  "telefono": "987654000",
  "email": "laura@email.com",
  "fecha_nacimiento": "1990-08-22"
}
```

**Mínimo necesario (email y fecha de nacimiento son opcionales):**
```json
{
  "nombre": "Pedro",
  "apellido": "Flores",
  "telefono": "991234567"
}
```

**Response 201:**
```json
{
  "mensaje": "Paciente registrado y historia clínica creada exitosamente.",
  "paciente": {
    "id": 10,
    "nombre": "Laura",
    "apellido": "Ramírez",
    "telefono": "987654000",
    "email": "laura@email.com",
    "fecha_nacimiento": "1990-08-22",
    "fecha_registro": "2026-06-04T08:00:00+00:00"
  }
}
```

---

### `PUT /api/pacientes/{id}`
Actualiza datos de un paciente. Solo se modifican los campos enviados.

**Request Body:**
```json
{
  "email": "nuevo_email@ejemplo.com",
  "fecha_nacimiento": "1990-08-22"
}
```

**Response 200:**
```json
{
  "mensaje": "Paciente actualizado exitosamente.",
  "paciente": { "...campos actualizados..." }
}
```

---

### `DELETE /api/pacientes/{id}`
Elimina un paciente y su historia clínica (en cascada).

**Response 200:**
```json
{
  "mensaje": "Paciente 'Laura Ramírez' eliminado exitosamente."
}
```

---

## 📂 Historias Clínicas (`/api/historias`)

### `GET /api/historias/{paciente_id}`
Retorna la historia clínica completa del paciente con todas sus atenciones.

**Response 200:**
```json
{
  "paciente": {
    "id": 1,
    "nombre": "Carlos",
    "apellido": "Sánchez",
    "telefono": "123456789",
    "email": "carlos@email.com",
    "fecha_nacimiento": "1995-04-12",
    "fecha_registro": "2026-05-20T10:30:00+00:00"
  },
  "historia": {
    "id": 1,
    "antecedentes_medicos": "Alergia a la penicilina.",
    "fecha_creacion": "2026-05-20T10:30:00+00:00"
  },
  "atenciones": [
    {
      "id": 1,
      "cita_id": 5,
      "diagnostico": "Caries en molar superior derecho.",
      "tratamiento_realizado": "Obturación con resina compuesta.",
      "observaciones": "Paciente tolera bien el procedimiento.",
      "fecha_atencion": "2026-05-25T09:30:00+00:00"
    }
  ]
}
```

---

### `PUT /api/historias/{paciente_id}/antecedentes`
Actualiza los antecedentes médicos generales del paciente.

**Request Body:**
```json
{
  "antecedentes_medicos": "Alergia a la penicilina. Diabetes tipo 2 controlada."
}
```

**Response 200:**
```json
{
  "mensaje": "Antecedentes médicos actualizados exitosamente.",
  "historia_id": 1,
  "antecedentes_medicos": "Alergia a la penicilina. Diabetes tipo 2 controlada."
}
```

---

### `POST /api/historias/atenciones`
Registra una nueva evolución clínica. La cita debe estar en estado `asistida`.

**Request Body:**
```json
{
  "cita_id": 5,
  "diagnostico": "Gingivitis leve en sector anterior.",
  "tratamiento_realizado": "Profilaxis y raspado supragingival.",
  "observaciones": "Instruir al paciente en técnicas de higiene bucal."
}
```

**Request Body mínimo (observaciones es opcional):**
```json
{
  "cita_id": 5,
  "diagnostico": "Caries oclusal.",
  "tratamiento_realizado": "Obturación directa."
}
```

**Response 201:**
```json
{
  "mensaje": "Atención médica registrada exitosamente para la cita #5.",
  "atencion": {
    "id": 3,
    "historia_id": 1,
    "cita_id": 5,
    "diagnostico": "Gingivitis leve en sector anterior.",
    "tratamiento_realizado": "Profilaxis y raspado supragingival.",
    "observaciones": "Instruir al paciente en técnicas de higiene bucal.",
    "fecha_atencion": "2026-06-04T10:00:00+00:00"
  }
}
```

---

## 📅 Citas (`/api/citas`)

### `GET /api/citas/disponibilidad`
Consulta los horarios disponibles para una fecha, odontólogo o especialidad.

**Query Params:**
- `fecha=2026-06-10` (requerido)
- `odontologo_id=1` (opcional)
- `especialidad=ortodoncia` (opcional)

**Response 200:**
```json
{
  "fecha": "2026-06-10",
  "disponibilidad": [
    {
      "odontologo_id": 1,
      "nombre": "Dr(a). Juan Pérez",
      "especialidad": "Ortodoncia",
      "slots_disponibles": [
        "08:00", "08:30", "09:00", "09:30",
        "11:00", "14:00", "15:30", "16:00"
      ]
    },
    {
      "odontologo_id": 2,
      "nombre": "Dr(a). Ana García",
      "especialidad": "General",
      "slots_disponibles": [
        "08:00", "08:30", "09:00"
      ]
    }
  ]
}
```

---

### `GET /api/citas/`
Lista las citas con filtros opcionales.

**Query Params opcionales:**
- `fecha=2026-06-10`
- `estado=programada`
- `odontologo_id=1`
- `paciente_id=3`
- `limite=50`

**Response 200:**
```json
{
  "total": 2,
  "citas": [
    {
      "id": 1,
      "fecha_hora": "2026-06-10T09:00:00-05:00",
      "estado": "programada",
      "motivo_consulta": "Dolor de muela",
      "paciente_id": 3,
      "odontologo_id": 1,
      "created_at": "2026-06-04T08:00:00+00:00",
      "paciente_nombre": "Carlos Sánchez",
      "odontologo_nombre": "Dr(a). Juan Pérez"
    }
  ]
}
```

---

### `POST /api/citas/`
Agenda una nueva cita. El slot debe estar disponible.

**Request Body:**
```json
{
  "paciente_id": 3,
  "odontologo_id": 1,
  "fecha_hora": "2026-06-10T09:00",
  "motivo_consulta": "Revisión general y limpieza dental"
}
```

**Request Body mínimo:**
```json
{
  "paciente_id": 3,
  "odontologo_id": 1,
  "fecha_hora": "2026-06-10T09:00"
}
```

**Response 201:**
```json
{
  "mensaje": "Cita agendada exitosamente.",
  "cita": {
    "id": 10,
    "fecha_hora": "2026-06-10T09:00:00-05:00",
    "estado": "programada",
    "motivo_consulta": "Revisión general y limpieza dental",
    "paciente_id": 3,
    "odontologo_id": 1,
    "paciente_nombre": "Carlos Sánchez",
    "odontologo_nombre": "Dr(a). Juan Pérez"
  }
}
```

---

### `PUT /api/citas/{id}/estado`
Cambia el estado de una cita. Envía notificación automática por Telegram al paciente.

**Estados válidos:** `programada` | `confirmada` | `asistida` | `cancelada` | `no_show`  
*(El alias `atendida` es equivalente a `asistida`)*

**Request Body:**
```json
{
  "nuevo_estado": "confirmada"
}
```

**Response 200:**
```json
{
  "mensaje": "Estado de la cita #10 actualizado.",
  "estado_anterior": "programada",
  "estado_nuevo": "confirmada"
}
```

---

### `PUT /api/citas/{id}`
Actualiza datos de una cita existente (reprogramación).

**Request Body:**
```json
{
  "fecha_hora": "2026-06-12T11:00",
  "motivo_consulta": "Revisión de ortodoncia"
}
```

**Response 200:**
```json
{
  "mensaje": "Cita actualizada exitosamente.",
  "cita": { "...campos de la cita actualizados..." }
}
```

---

### `DELETE /api/citas/{id}`
Elimina una cita permanentemente.

**Response 200:**
```json
{
  "mensaje": "Cita #10 eliminada exitosamente."
}
```

---

## 💰 Pagos (`/api/pagos`)

### `GET /api/pagos/`
Lista los pagos registrados con datos enriquecidos del paciente.

**Query Params opcionales:**
- `estado_pago=pagado` (`pagado`, `pendiente`, `fallido`)
- `limite=50`

**Response 200:**
```json
{
  "total": 1,
  "pagos": [
    {
      "id": 1,
      "cita_id": 5,
      "monto": "150.00",
      "metodo_pago": "efectivo",
      "estado_pago": "pagado",
      "fecha_pago": "2026-05-25T10:15:00-05:00",
      "paciente_nombre": "Carlos Sánchez",
      "odontologo_nombre": "Dr(a). Juan Pérez",
      "fecha_cita": "2026-05-25T09:00:00-05:00"
    }
  ]
}
```

---

### `POST /api/pagos/`
Registra el pago de una cita que se encuentre en estado `asistida`.

**Métodos válidos:** `efectivo` | `tarjeta` | `yape` | `plin`

**Request Body:**
```json
{
  "cita_id": 5,
  "monto": 150.00,
  "metodo_pago": "efectivo"
}
```

**Response 201:**
```json
{
  "mensaje": "Pago de S/ 150.00 registrado exitosamente para la cita #5.",
  "pago": {
    "id": 1,
    "cita_id": 5,
    "monto": 150.00,
    "metodo_pago": "efectivo",
    "estado_pago": "pagado",
    "fecha_pago": "2026-06-04T10:30:00-05:00"
  }
}
```

**Response 422 (cita no está asistida):**
```json
{
  "detail": "Solo se pueden registrar pagos para citas en estado 'asistida'. Estado actual: 'programada'."
}
```

**Response 409 (pago ya registrado):**
```json
{
  "detail": "Ya existe un pago registrado para la cita #5."
}
```

---

## ❌ Códigos de Error Comunes

| Código | Significado |
|:---|:---|
| `400` | Petición inválida (ej: intentar eliminarse a sí mismo) |
| `401` | No autenticado o token expirado |
| `403` | Sin permisos para esa operación (rol insuficiente) |
| `404` | Recurso no encontrado |
| `409` | Conflicto (ej: duplicados como username, teléfono, pago ya registrado) |
| `422` | Datos inválidos o faltantes en el payload |

---

## 🚀 Cómo Iniciar la API

```bash
# Desde el directorio del proyecto:
uvicorn api:app --reload --port 8000
```

La API estará disponible en `http://localhost:8000`  
Swagger UI: `http://localhost:8000/docs`  
ReDoc: `http://localhost:8000/redoc`

> [!NOTE]
> La API puede correr simultáneamente junto al Bot de Telegram (`python main.py`),
> el Servidor MCP (`python mcp_server.py`) y el Dashboard Streamlit (`streamlit run dashboard.py`),
> ya que todos comparten la misma base de datos Supabase sin conflictos.
