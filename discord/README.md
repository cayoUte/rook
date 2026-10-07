# Servidor de Discord de los talleres

Script que construye y opera el servidor descrito en la sección «Operación en Discord» del modelo de negocio. Usa un bot propio y la API oficial de Discord; solo necesita Python 3.9 o superior, sin instalar nada más.

## Qué construye

```
INICIO            #bienvenida · #reglas · 📣 anuncios                      solo lectura
AULAS             🗂 catálogo · #calendario · #reservar · #busco-grupo · 🎤 Clase abierta
COMUNIDAD         #general · #showcase · #recursos · #prácticas-y-empleos · 🔊 Sala de estudio
AYUDA             🗂 dudas · #setup
AULAS ACTIVAS     un canal de texto y uno de voz por aula                  privada
STAFF             #pagos-por-validar · #bitácora · #tutores                privada
ARCHIVO           canales de texto de las aulas terminadas                 privada
```

- **Roles:** Admin, Tutor, Organizador, Estudiante, una insignia por taller publicado y un rol temporal por aula.
- **Comunidad de Discord activada**, que es lo que permite el foro, el canal de anuncios y el escenario.
- **Entrada:** correo verificado y cuenta con más de 5 minutos; AutoMod contra spam, menciones masivas e insultos, con alertas en #bitácora.
- **Textos** de bienvenida, reglas (convivencia, pagos e integridad académica), reservas y guía para tutores.
- **Catálogo** con los 4 talleres de la fase 1 y las tutorías. Los 30 talleres están en `catalogo.py`.
- **Invitación** permanente que entrega el rol Estudiante a quien la acepta.

`python servidor.py plan` muestra el diseño completo sin conectarse a Discord.

## Puesta en marcha

1. **Crea el servidor** en Discord, vacío y ya con su nombre definitivo (aparece en el texto de bienvenida).
2. **Crea el bot.** En <https://discord.com/developers/applications>: *New Application* → menú *Bot* → *Reset Token* → copia el token.
3. **Guarda el token.** Copia `.env.example` como `.env` y pega el token en `DISCORD_TOKEN`. No lo compartas ni lo subas a un repositorio; si se filtra, vuelve a pulsar *Reset Token*.
4. **Ejecuta:**

   ```
   python servidor.py construir
   ```

   La primera vez te muestra un enlace para invitar al bot con permiso de Administrador. Ábrelo, elige tu servidor, autoriza y repite el comando.

El comando crea solo lo que falta, así que se puede repetir sin duplicar nada. Si se detiene por un error, corrige la causa y vuelve a ejecutarlo. Todo lo que hace queda en `registro.log`.

Al terminar verás la invitación del servidor y, si quedaron, los canales de la plantilla inicial de Discord para que los borres a mano.

## Órdenes

| Orden | Qué hace |
|---|---|
| `python servidor.py plan` | Muestra el diseño sin tocar Discord. |
| `python servidor.py construir` | Crea lo que falte y al final compara el servidor con el diseño. |
| `python servidor.py verificar` | Solo compara; no cambia nada. |
| `python servidor.py publicar --fase 2` | Abre los talleres de esa fase: insignias y publicaciones del catálogo. |
| `python servidor.py aula crear …` | Abre un aula privada. |
| `python servidor.py aula listar` | Aulas activas y cuáles ya vencieron. |
| `python servidor.py aula archivar …` | Cierra un aula, o todas las vencidas con `--vencidas`. |

## El ciclo de un aula

1. **Reserva.** El organizador abre un hilo privado en #reservar: lo ven él, a quienes invite y el Admin. Ahí sube el comprobante.
2. **Confirmas.** Con el pago validado:

   ```
   python servidor.py aula crear poo-python --inicio "2026-10-17 10:00"
   ```

   Crea el rol temporal, el canal de texto, el canal de voz con límite de 6, el evento con recordatorio y la lista de preparación fijada. Devuelve un **enlace de 5 usos**: pégalo en el hilo de la reserva. Cada persona que lo abre entra al servidor, si no estaba, y recibe el rol del aula.

   - El primer dato es el id de un taller de `catalogo.py` o un título libre: `"Tutoría · Cálculo" --horas 1`.
   - `--miembros ana.perez luis_x` mete directo a quienes ya están en el servidor; el enlace cubre los cupos restantes.
   - `--kit URL` agrega el enlace del kit a la lista de preparación.

3. **Clase.** Cada estudiante transmite con Go Live en el canal de voz del aula.
4. **Cierre.** Asigna la insignia a mano (clic derecho en la persona → Roles) y pide el proyecto en #showcase.
5. **Archivo.** A los 7 días:

   ```
   python servidor.py aula archivar --vencidas
   ```

   Borra el canal de voz, el rol y el enlace, y mueve el canal de texto a Archivo.

## Archivos

| Archivo | Contenido |
|---|---|
| `servidor.py` | El script. |
| `diseno.py` | Roles, canales, permisos y textos. Edítalo y vuelve a ejecutar `construir`. |
| `catalogo.py` | Los 30 talleres con nivel, fase, producto y conexiones; las tutorías y sus materias. |
| `.env` | El token del bot. Lo creas tú; no se comparte. |
| `estado.json` | Ids de lo que creó el script. Con él, renombrar o mover un canal en Discord no lo duplica. |
| `registro.log` | Historial de cada ejecución. |
| `test_servidor.py`, `discord_falso.py` | Pruebas contra un Discord simulado: `python -m unittest`. |

## Decisiones que conviene conocer

- **El onboarding nativo de Discord viene apagado.** Con él encendido, a los miembros nuevos solo les aparecen los canales predeterminados, y los canales privados de su aula no se les muestran aunque tengan el rol: cada persona tendría que activar «Mostrar todos los canales». Las preguntas de carrera, semestre e intereses están listas en `diseno.py`; se encienden con `AJUSTES["onboarding"] = True`.
- **Las reservas son hilos privados**, una función nativa que no depende de ningún bot en marcha. Un bot de tickets se puede poner encima después.
- **El tutor no ve los hilos de reserva ajenos ni #pagos-por-validar**, porque ahí van los comprobantes. Solo el Admin.
- **Lo que ya existe no se toca.** Si cambias algo a mano en Discord, `construir` lo respeta y `verificar` te lo señala como diferencia.
- **Revisa antes de ejecutar** las materias de tutoría en `catalogo.py` (`MATERIAS`) y la línea «Hecho por estudiantes de la UTE» del texto de bienvenida en `diseno.py`.

## Si algo falla

- **«El token no es válido»:** copia el token de nuevo; *Reset Token* invalida el anterior.
- **Se detiene en «Comunidad»:** activa la comunidad a mano en los ajustes del servidor, eligiendo #reglas como canal de reglas y #bitácora como canal de novedades, y repite `construir`.
- **Un aviso (`!`) en el registro** es un adorno que Discord no aceptó; el resto sigue. El texto dice cómo hacerlo a mano.
- **`python` no existe en Windows:** prueba con `py servidor.py construir`.
