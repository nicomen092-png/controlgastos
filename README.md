# Control de Gastos 💸

Registra automáticamente cada compra que haces con **Apple Pay** en una hoja de
Google Sheets. Justo después de pagar, el iPhone te pregunta:

1. **¿En qué categoría?** → eliges de una lista (Comida, Transporte, Ocio…)
2. **¿En qué estás gastando?** → escribes o dictas un detalle ("almuerzo con el equipo")

…y te responde con una notificación tipo:

> Guardado: $12.50 en Comida. Este mes llevas $184.30 en Comida.

```
 Pagas con Apple Pay ──► Automatización "Transacción" (Atajos de iOS)
                              │  pregunta categoría + "¿En qué estás gastando?"
                              ▼
                     Google Apps Script (Aplicación web)
                              │
                              ▼
               Google Sheets: Gastos · Categorías · Resumen
```

## Qué incluye

| Archivo | Para qué sirve |
|---|---|
| `apps-script/Code.gs` | Backend: recibe los gastos, crea las hojas y el resumen mensual. |
| `apps-script/Panel.html` | Panel web con el total del mes, gasto por categoría y últimos movimientos. |
| `apps-script/appsscript.json` | Configuración del proyecto (zona horaria, permisos de la app web). |

---

## Paso 1 — Crear la hoja y el script (10 min, desde la computadora)

1. Entra a [sheets.new](https://sheets.new) y ponle un nombre, por ejemplo **Control de Gastos**.
2. Menú **Extensiones → Apps Script**.
3. En el editor, borra lo que haya en `Código.gs` y pega el contenido de
   [`apps-script/Code.gs`](apps-script/Code.gs).
4. Crea un archivo HTML: **+ → HTML**, nómbralo exactamente `Panel` y pega
   [`apps-script/Panel.html`](apps-script/Panel.html).
5. (Opcional) En **Configuración del proyecto ⚙️** cambia la zona horaria a la tuya.
   Por defecto viene `America/Argentina/Buenos_Aires`.
6. Arriba, elige la función **`configurar`** y pulsa **▶ Ejecutar**.
   Google te pedirá permisos → **Revisar permisos → tu cuenta → Configuración
   avanzada → Ir a (no seguro) → Permitir**. Es normal: el script es tuyo.
7. Abre **Registro de ejecución** y copia tu **token secreto** (16 caracteres).
   Si lo pierdes, ejecuta la función `verToken`.

Tu hoja ahora tiene tres pestañas: **Gastos**, **Categorías** (edítala libremente
para agregar/quitar categorías) y **Resumen** (total del mes y por categoría).

## Paso 2 — Publicar como aplicación web

1. En el editor: **Implementar → Nueva implementación**.
2. Tipo: **Aplicación web**.
3. *Ejecutar como*: **Yo**. *Quién tiene acceso*: **Cualquier usuario**.
   (El token es lo que impide que otros escriban en tu hoja.)
4. **Implementar** y copia la **URL de la aplicación web** (termina en `/exec`).

> Si más adelante cambias el código: **Implementar → Gestionar implementaciones →
> ✏️ → Versión: Nueva versión**. Así la URL no cambia.

Prueba rápida: abre en el navegador `TU_URL?accion=categorias`. Deberías ver la
lista de categorías.

## Paso 3 — La automatización en el iPhone (la parte que pregunta)

Requiere iOS 17 o superior y la tarjeta agregada en Wallet.

1. Abre la app **Atajos** → pestaña **Automatización** → **+** (Nueva automatización).
2. Elige **Transacción**.
3. Selecciona tus tarjetas (y si quieres, categorías/comercios). Marca
   **Ejecutar inmediatamente** → **Siguiente** → **Nueva automatización en blanco**.
4. Agrega estas acciones **en este orden**:

   | # | Acción | Configuración |
   |---|---|---|
   | 1 | **Texto** | Pega `TU_URL?accion=categorias` |
   | 2 | **Obtener contenido de URL** | URL = *Texto* (de la acción 1). Método **GET**. |
   | 3 | **Dividir texto** | Separador: **Saltos de línea** |
   | 4 | **Elegir de la lista** | Lista = *Texto dividido*. Toca ▸ y en *Mensaje* escribe **¿En qué categoría?** |
   | 5 | **Solicitar entrada** | Tipo **Texto**. Pregunta: **¿En qué estás gastando?** |
   | 6 | **Obtener contenido de URL** | URL = `TU_URL` (sin `?accion…`). Método **POST**. Cuerpo de la solicitud: **JSON** con los campos de abajo. |
   | 7 | **Obtener valor del diccionario** | Clave `mensaje` del *Contenido de la URL* |
   | 8 | **Mostrar notificación** | Texto = *Valor del diccionario* |

   Campos JSON de la acción 6 (todos tipo **Texto**):

   | Clave | Valor |
   |---|---|
   | `token` | tu token secreto |
   | `monto` | variable **Entrada del atajo → Importe** |
   | `comercio` | variable **Entrada del atajo → Comerciante** |
   | `tarjeta` | variable **Entrada del atajo → Tarjeta o pase** |
   | `categoria` | variable **Elemento elegido** (acción 4) |
   | `descripcion` | variable **Entrada proporcionada** (acción 5) |
   | `origen` | `Apple Pay` |

   > Para elegir *Importe*, *Comerciante*, etc.: toca el campo, elige la variable
   > mágica **Entrada del atajo** y luego tócala otra vez para escoger la propiedad.

5. **OK**. ¡Listo! Haz una compra con Apple Pay y te aparecerán las dos preguntas.

### Extra: gastos en efectivo (atajo manual)

Crea un **atajo normal** (no automatización) llamado *Anotar gasto* con las mismas
acciones 1–8, pero agrega al principio **Solicitar entrada → Número → "¿Cuánto
gastaste?"** y usa esa respuesta como `monto`; pon `origen` = `Efectivo` y deja
`comercio`/`tarjeta` vacíos. Puedes lanzarlo con Siri ("Oye Siri, anotar gasto"),
desde un widget o con el botón de Acción.

## Paso 4 — Ver tu resumen

- En la hoja: pestaña **Resumen**.
- En el celular: abre `TU_URL?token=TU_TOKEN` en Safari y usa
  **Compartir → Agregar a pantalla de inicio**. Tendrás un ícono con el total del
  mes, el gasto por categoría y los últimos movimientos.

---

## Preguntas frecuentes

**No me aparecen las preguntas después de pagar.**
Toca la notificación de Atajos que aparece tras el pago; en algunas versiones de
iOS las acciones que piden datos se abren desde ahí. Si sigue sin funcionar,
desactiva *Ejecutar inmediatamente* (te pedirá confirmar antes de ejecutarse).

**Escribí una categoría que no estaba en la lista.**
Si prefieres escribir la categoría libremente, cambia la acción 4 por
**Solicitar entrada**. El script agrega automáticamente a la pestaña
**Categorías** cualquier categoría nueva que reciba (sin duplicar por mayúsculas).

**La notificación dice "Token inválido".**
Revisa que el token del atajo sea exactamente el del registro (`verToken`).

**El monto sale mal (por ejemplo 1234 en vez de 12,34).**
El script entiende formatos como `$1.234,50`, `1,234.50`, `€ 12,5` o `12.50 USD`.
Si tu banco usa otro formato, abre un issue con un ejemplo.

**¿Es seguro?**
Los datos quedan en *tu* Google Drive. La URL solo acepta gastos que traigan tu
token; no la compartas junto con el token.
