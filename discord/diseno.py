"""Diseño del servidor: roles, categorías, canales, permisos y textos.

Sigue la sección «Operación en Discord» del modelo de negocio. Este archivo es
solo datos: edítalo y vuelve a ejecutar `python servidor.py construir`. El
script crea lo que falta y no toca lo que ya existe.

Marcadores que se resuelven al publicar un texto:
    {#clave}    mención del canal con esa clave
    {@clave}    mención del rol con esa clave (no notifica a nadie)
    {servidor}  nombre del servidor
"""

from __future__ import annotations

from typing import Any, Dict, List

import catalogo

AJUSTES: Dict[str, Any] = {
    # Fase del catálogo que se publica al construir (ver catalogo.py).
    "fase": 1,
    # Las fechas de `aula crear` se leen en esta zona. Ecuador continental: UTC-5.
    "utc_offset_horas": -5,
    # 2 = la cuenta debe tener correo verificado y más de 5 minutos en Discord.
    "verificacion": 2,
    "idioma": "es-419",
    "descripcion": (
        "Talleres de programación en vivo en aulas de hasta 5 personas: "
        "en 2 horas construyes algo que funciona y te lo llevas a tu GitHub."
    ),
    # Roles que recibe el dueño del servidor para aparecer como tutor y recibir las menciones.
    "roles_del_dueno": ["admin", "tutor"],
    # Rol que da el enlace de invitación del servidor y que recibe quien entra a un aula.
    "rol_de_miembro": "estudiante",
    # Onboarding nativo de Discord (preguntas de carrera, semestre e intereses al entrar).
    # Viene apagado porque tiene un costo: con el onboarding encendido, a los miembros nuevos
    # solo les aparecen los canales predeterminados y, según varios reportes en el foro de
    # soporte de Discord, los canales privados de su aula NO se les muestran aunque tengan el
    # rol; cada persona tendría que activar «Mostrar todos los canales». Si igual lo quieres,
    # pon True y vuelve a ejecutar `construir`.
    "onboarding": False,
    "canal_reglas": "reglas",
    "canal_avisos_de_discord": "bitacora",
    "canal_de_sistema": "general",
    "canal_de_invitacion": "bienvenida",
    # Límite de personas del canal de voz de cada aula: 5 estudiantes y el tutor.
    "limite_voz_aula": 6,
    "dias_para_archivar": 7,
}

# ── Permisos ────────────────────────────────────────────────────────────────

# Lo que puede hacer cualquier miembro (rol @everyone).
PERMISOS_BASE: List[str] = [
    "VIEW_CHANNEL",
    "READ_MESSAGE_HISTORY",
    "SEND_MESSAGES",
    "SEND_MESSAGES_IN_THREADS",
    "CREATE_PUBLIC_THREADS",
    "EMBED_LINKS",
    "ATTACH_FILES",
    "ADD_REACTIONS",
    "USE_EXTERNAL_EMOJIS",
    "USE_EXTERNAL_STICKERS",
    "SEND_VOICE_MESSAGES",
    "SEND_POLLS",
    "USE_APPLICATION_COMMANDS",
    "CONNECT",
    "SPEAK",
    "STREAM",  # compartir pantalla con Go Live
    "USE_VAD",
    "USE_EMBEDDED_ACTIVITIES",
    "REQUEST_TO_SPEAK",
    "CHANGE_NICKNAME",
    "CREATE_INSTANT_INVITE",  # el boca a boca: cualquiera invita a sus compañeros
]

# Lo que el tutor suma a lo anterior.
PERMISOS_TUTOR: List[str] = [
    "MANAGE_MESSAGES",
    "PIN_MESSAGES",
    "MANAGE_THREADS",
    "MODERATE_MEMBERS",  # silenciar temporalmente
    "MUTE_MEMBERS",
    "DEAFEN_MEMBERS",
    "MOVE_MEMBERS",
    "PRIORITY_SPEAKER",
    "CREATE_EVENTS",
    "MANAGE_EVENTS",
    "MENTION_EVERYONE",  # avisar a todos o a un rol que no es mencionable
]

NO_ESCRIBIR = ["SEND_MESSAGES", "CREATE_PUBLIC_THREADS", "CREATE_PRIVATE_THREADS", "SEND_MESSAGES_IN_THREADS"]

SOLO_LECTURA = [{"rol": "@everyone", "niega": NO_ESCRIBIR}]
LECTURA_Y_TUTOR_PUBLICA = SOLO_LECTURA + [{"rol": "tutor", "permite": ["SEND_MESSAGES"]}]
ABIERTO: List[Dict[str, Any]] = []
SOLO_STAFF = [
    {"rol": "@everyone", "niega": ["VIEW_CHANNEL"]},
    {"rol": "tutor", "permite": ["VIEW_CHANNEL"]},
]
SOLO_ADMIN = [{"rol": "@everyone", "niega": ["VIEW_CHANNEL"]}]

# Permisos del rol temporal de un aula sobre sus dos canales.
PERMISOS_AULA = ["VIEW_CHANNEL", "SEND_MESSAGES", "CONNECT", "SPEAK", "STREAM"]

# ── Roles (de arriba hacia abajo) ───────────────────────────────────────────

ROLES_FIJOS: List[Dict[str, Any]] = [
    {"clave": "admin", "nombre": "Admin", "permisos": ["ADMINISTRATOR"], "color": 0xE74C3C, "separado": False, "mencionable": True},
    {"clave": "tutor", "nombre": "Tutor", "permisos": PERMISOS_TUTOR, "color": 0x3498DB, "separado": True, "mencionable": False},
    {"clave": "organizador", "nombre": "Organizador", "permisos": [], "color": 0xF1C40F, "separado": True, "mencionable": False},
    {"clave": "estudiante", "nombre": "Estudiante", "permisos": [], "color": 0x2ECC71, "separado": True, "mencionable": False},
]

COLOR_INSIGNIA = {1: 0x1ABC9C, 2: 0x9B59B6, 3: 0xE67E22}

# ── Onboarding: carrera, semestre e intereses ───────────────────────────────
# Solo se usa si AJUSTES["onboarding"] es True. Cada opción asigna su rol.
# Ajusta las carreras a las de tu universidad.

ONBOARDING: List[Dict[str, Any]] = [
    {
        "titulo": "¿Qué carrera estudias?",
        "una_sola": True,
        "obligatoria": True,
        "opciones": [
            {"titulo": "Software", "emoji": "💻", "descripcion": "Ingeniería o desarrollo de software", "rol": ("carrera:software", "Carrera · Software")},
            {"titulo": "Computación", "emoji": "🧮", "descripcion": "Ciencias de la computación", "rol": ("carrera:computacion", "Carrera · Computación")},
            {"titulo": "Tecnologías de la información", "emoji": "🌐", "descripcion": "TI, redes o sistemas", "rol": ("carrera:ti", "Carrera · TI")},
            {"titulo": "Otra carrera", "emoji": "🎓", "descripcion": "Estudio otra cosa o ya no estudio", "rol": ("carrera:otra", "Carrera · Otra")},
        ],
        # Rol que reciben todas las opciones de esta pregunta.
        "rol_comun": "estudiante",
    },
    {
        "titulo": "¿En qué semestre estás?",
        "una_sola": True,
        "obligatoria": True,
        "opciones": [
            {"titulo": "1.º o 2.º semestre", "emoji": "🌱", "descripcion": "Recién empiezo la carrera", "rol": ("semestre:1-2", "Semestre · 1.º–2.º")},
            {"titulo": "3.º a 5.º semestre", "emoji": "📘", "descripcion": "Voy por la mitad", "rol": ("semestre:3-5", "Semestre · 3.º–5.º")},
            {"titulo": "6.º semestre en adelante", "emoji": "🎯", "descripcion": "Busco portafolio, prácticas o empleo", "rol": ("semestre:6", "Semestre · 6.º o más")},
            {"titulo": "Ya egresé o no aplica", "emoji": "🏁", "descripcion": None, "rol": ("semestre:egresado", "Semestre · Egresado")},
        ],
    },
    {
        "titulo": "¿Qué te interesa?",
        "una_sola": False,
        "obligatoria": False,
        "opciones": [
            {"titulo": "Aprobar una materia", "emoji": "📚", "descripcion": "Tutorías de programación, bases de datos o matemáticas", "rol": ("interes:tutorias", "Interés · Tutorías")},
            {"titulo": "Empezar desde cero", "emoji": "🧱", "descripcion": "Lógica, Git, HTML y CSS", "rol": ("interes:fundamentos", "Interés · Fundamentos")},
            {"titulo": "Python", "emoji": "🐍", "descripcion": "POO, FastAPI, datos e IA", "rol": ("interes:python", "Interés · Python")},
            {"titulo": "JavaScript y TypeScript", "emoji": "⚡", "descripcion": "React, Express y Next.js", "rol": ("interes:javascript", "Interés · JavaScript")},
            {"titulo": "Java", "emoji": "☕", "descripcion": "Spring Boot, patrones y pruebas", "rol": ("interes:java", "Interés · Java")},
            {"titulo": "DevOps", "emoji": "🐳", "descripcion": "Linux, Docker, CI/CD y seguridad", "rol": ("interes:devops", "Interés · DevOps")},
            {"titulo": "Algoritmos y entrevistas", "emoji": "🧩", "descripcion": "Estructuras de datos, grafos y concursos", "rol": ("interes:algoritmos", "Interés · Algoritmos")},
        ],
    },
]

# ── Categorías y canales ────────────────────────────────────────────────────
# tipo: texto · anuncios · foro · voz · escenario
# Un canal sin `permisos` usa los de su categoría.

ETIQUETAS_CATALOGO = (
    [{"nombre": n, "moderada": True} for n in catalogo.ETIQUETAS_TIPO]
    + [{"nombre": n, "moderada": True} for n in catalogo.ETIQUETAS_NIVEL.values()]
    + [{"nombre": n, "moderada": True} for n in catalogo.ETIQUETAS_TECNOLOGIA]
)

ETIQUETAS_DUDAS = [
    {"nombre": n, "moderada": False}
    for n in ["Python", "JavaScript", "TypeScript", "Java", "SQL", "HTML y CSS", "Git", "Linux y Docker", "Matemáticas", "Otra", "Resuelto"]
]

CATEGORIAS: List[Dict[str, Any]] = [
    {
        "clave": "cat:inicio",
        "nombre": "Inicio",
        "permisos": SOLO_LECTURA,
        "canales": [
            {"clave": "bienvenida", "nombre": "bienvenida", "tipo": "texto", "tema": "Cómo funciona el servidor en 3 pasos."},
            {"clave": "reglas", "nombre": "reglas", "tipo": "texto", "tema": "Convivencia, reservas y pagos, e integridad académica."},
            {
                "clave": "anuncios",
                "nombre": "anuncios",
                "tipo": "anuncios",
                "tema": "Talleres nuevos, aulas abiertas y la clase abierta gratis de cada mes.",
                "permisos": LECTURA_Y_TUTOR_PUBLICA,
            },
        ],
    },
    {
        "clave": "cat:aulas",
        "nombre": "Aulas",
        "permisos": ABIERTO,
        "canales": [
            {
                "clave": "catalogo",
                "nombre": "catálogo",
                "tipo": "foro",
                "tema": (
                    "Cada publicación es un taller, una tutoría o una ruta. Filtra con las etiquetas de tecnología y nivel.\n\n"
                    "El precio es por aula de hasta 5 personas, no por persona. Para reservar ve a {#reservar}. "
                    "Si un taller te interesa y aún no tienes grupo, coméntalo en su publicación o pasa por {#busco-grupo}."
                ),
                # En un foro, SEND_MESSAGES es crear publicaciones: solo el equipo publica y todos comentan.
                "permisos": [
                    {"rol": "@everyone", "niega": ["SEND_MESSAGES", "CREATE_PUBLIC_THREADS", "CREATE_PRIVATE_THREADS"]},
                    {"rol": "tutor", "permite": ["SEND_MESSAGES"]},
                ],
                "etiquetas": ETIQUETAS_CATALOGO,
                "reaccion": "🙋",
                "orden": "creacion",
            },
            {
                "clave": "calendario",
                "nombre": "calendario",
                "tipo": "texto",
                "tema": "Horarios de las aulas abiertas y de las clases gratis. Los eventos están arriba de la lista de canales.",
                "permisos": LECTURA_Y_TUTOR_PUBLICA,
            },
            {
                "clave": "reservar",
                "nombre": "reservar",
                "tipo": "texto",
                "tema": "Abre un hilo privado para reservar tu aula. El pago confirma el cupo y se hace hasta 24 horas antes.",
                # Cada reserva es un hilo privado: lo ven quien lo abre, a quienes invite y el Admin.
                # El tutor no ve los hilos ajenos porque ahí se suben comprobantes de pago.
                "permisos": [
                    {"rol": "@everyone", "niega": ["SEND_MESSAGES", "CREATE_PUBLIC_THREADS"], "permite": ["CREATE_PRIVATE_THREADS"]},
                    {"rol": "tutor", "niega": ["MANAGE_THREADS"]},
                ],
                "archivar_hilos_min": 10080,
            },
            {
                "clave": "busco-grupo",
                "nombre": "busco-grupo",
                "tipo": "texto",
                "tema": "¿Vienes sin grupo? Di qué taller quieres y tus horarios para juntar un aula de hasta 5.",
            },
            {
                "clave": "clase-abierta",
                "nombre": "Clase abierta",
                "tipo": "escenario",
                # Moderadores del escenario: necesitan estos tres permisos en el canal.
                "permisos": [{"rol": "tutor", "permite": ["MANAGE_CHANNELS", "MUTE_MEMBERS", "MOVE_MEMBERS"]}],
            },
        ],
    },
    {
        "clave": "cat:comunidad",
        "nombre": "Comunidad",
        "permisos": ABIERTO,
        "canales": [
            {"clave": "general", "nombre": "general", "tipo": "texto", "tema": "Conversación general de la comunidad."},
            {"clave": "showcase", "nombre": "showcase", "tipo": "texto", "tema": "Muro de proyectos: comparte el enlace a tu producto terminado."},
            {"clave": "recursos", "nombre": "recursos", "tipo": "texto", "tema": "Documentación, herramientas y material útil."},
            {"clave": "practicas", "nombre": "prácticas-y-empleos", "tipo": "texto", "tema": "Ofertas de prácticas y de empleo, portafolio y entrevistas."},
            {"clave": "sala-estudio", "nombre": "Sala de estudio", "tipo": "voz"},
        ],
    },
    {
        "clave": "cat:ayuda",
        "nombre": "Ayuda",
        "permisos": ABIERTO,
        "canales": [
            {
                "clave": "dudas",
                "nombre": "dudas",
                "tipo": "foro",
                "tema": (
                    "Una duda por publicación, con su etiqueta.\n\n"
                    "1. Cuenta qué quieres lograr y qué intentaste.\n"
                    "2. Pega el código y el error como texto, no como foto.\n"
                    "3. Si puedes, enlaza tu repositorio.\n\n"
                    "Aquí explicamos y damos pistas. No resolvemos deberes, proyectos ni pruebas calificadas.\n"
                    "Cuando tu duda quede resuelta, ponle la etiqueta Resuelto."
                ),
                "etiquetas": ETIQUETAS_DUDAS,
                "orden": "actividad",
            },
            {"clave": "setup", "nombre": "setup", "tipo": "texto", "tema": "Problemas con Codespaces, Git, el micrófono o compartir pantalla."},
        ],
    },
    {
        # Aquí crea `aula crear` un canal de texto y uno de voz por aula.
        "clave": "cat:aulas-activas",
        "nombre": "Aulas activas",
        "permisos": SOLO_STAFF,
        "canales": [],
    },
    {
        "clave": "cat:staff",
        "nombre": "Staff",
        "permisos": SOLO_STAFF,
        "canales": [
            {
                "clave": "pagos",
                "nombre": "pagos-por-validar",
                "tipo": "texto",
                "tema": "Comprobantes pendientes de validar. Bórralos cuando ya no hagan falta.",
                "permisos": SOLO_ADMIN,
            },
            {"clave": "bitacora", "nombre": "bitácora", "tipo": "texto", "tema": "Registro de operación: aulas creadas y archivadas, avisos de Discord y alertas de AutoMod."},
            {"clave": "tutores", "nombre": "tutores", "tipo": "texto", "tema": "Coordinación entre tutores."},
        ],
    },
    {
        # Aquí mueve `aula archivar` el canal de texto de cada aula terminada.
        "clave": "cat:archivo",
        "nombre": "Archivo",
        "permisos": SOLO_STAFF,
        "canales": [],
    },
]

# ── AutoMod ─────────────────────────────────────────────────────────────────
# tipo: 3 = spam sospechoso · 4 = listas de palabras de Discord · 5 = menciones masivas
# Admin y Tutor quedan exentos. Las alertas llegan a #bitácora.

AUTOMOD: List[Dict[str, Any]] = [
    {"nombre": "Spam sospechoso", "tipo": 3, "metadatos": {}},
    {
        "nombre": "Menciones masivas",
        "tipo": 5,
        # Una reserva menciona hasta 5 personas y al Admin, así que el límite va holgado.
        "metadatos": {"mention_total_limit": 10, "mention_raid_protection_enabled": True},
    },
    {
        "nombre": "Insultos y contenido sexual",
        "tipo": 4,
        "metadatos": {"presets": [2, 3], "allow_list": []},  # 2 = contenido sexual · 3 = insultos
    },
]
AUTOMOD_MENSAJE = "El filtro del servidor bloqueó tu mensaje. Si fue un error, avisa a un tutor."

# ── Textos fijos ────────────────────────────────────────────────────────────
# clave del canal → lista de mensajes (máximo 2000 caracteres cada uno).

MENSAJES: Dict[str, List[str]] = {
    "bienvenida": [
        """# Te damos la bienvenida a {servidor}
Talleres de programación en vivo, en aulas de hasta 5 personas. En 2 horas construyes algo que funciona y te lo llevas a tu GitHub.

## Cómo funciona
**1. Elige.** Revisa los talleres y las tutorías en {#catalogo}. Puedes venir con tu grupo o unirte a un horario publicado en {#calendario}.
**2. Reserva y paga.** Abre tu reserva en {#reservar}. El precio es por aula, no por persona: un taller de $20 sale a $4 cada uno si llenan el aula.
**3. Construye.** Te abrimos un aula privada con canal de voz y de texto. Compartes pantalla, programas con el tutor viendo tu código y sales con tu pieza funcionando.

## Para empezar
- Lee {#reglas}.
- ¿Vienes sin grupo? Pasa por {#busco-grupo}.
- ¿Algo no te funciona? Escribe en {#setup} o abre una publicación en {#dudas}.

-# Hecho por estudiantes de la UTE. No es un servicio oficial de la universidad.""",
    ],
    "reglas": [
        """# Reglas
## Convivencia
1. **Respeto siempre.** Nada de insultos, acoso ni discriminación.
2. **Sin spam.** Nada de publicidad ajena, cadenas ni invitaciones a otros servidores sin permiso.
3. **Cada cosa en su canal.** Dudas en {#dudas}, problemas de instalación en {#setup} y reservas en {#reservar}.
4. **Cuida los datos.** No publiques comprobantes, contraseñas, tokens ni datos personales de nadie. Los comprobantes van solo en tu reserva privada y los borramos cuando ya no hacen falta.
5. **Pregunta bien.** Cuenta qué intentaste y pega el error como texto, no como foto.

Quien incumpla estas reglas puede quedar silenciado o fuera del servidor.""",
        """## Reservas y pagos
- El precio es por aula, de 1 a 5 personas, y el grupo lo reparte entre sus miembros.
- El pago confirma el cupo y se hace hasta 24 horas antes.
- Reprogramar con 24 horas de aviso es gratis. Después, el aula se da con quienes lleguen y no hay reembolso.
- Si cancelamos nosotros, reprogramamos o devolvemos el 100 % y te regalamos 1 hora de tutoría.
- **Garantía:** si no terminas tu producto en el aula, te acompañamos 30 minutos extra esa semana.
- Solo se graba la pantalla del tutor, y con aviso. Nunca la tuya sin tu permiso.""",
        """## Integridad académica
1. En las tutorías explicamos y practicamos con ejercicios parecidos. No resolvemos deberes, proyectos ni pruebas calificadas.
2. No hay tutoría durante un examen en curso.
3. Ningún tutor da tutoría de una materia en la que es ayudante de cátedra o califica trabajos.
4. Si pides que te hagan la tarea, la respuesta es no: te ofrecemos la tutoría del tema.""",
    ],
    "calendario": [
        """# Calendario
Aquí publicamos los horarios de las **aulas abiertas** y de la **clase abierta gratis** de cada mes.

- En un aula abierta el precio se reparte entre quienes se inscriban hasta el cierre, 24 horas antes. Con un taller de $20: si van 3, cada uno paga $6,67; si llegan 5, $4.
- Los eventos aparecen arriba de la lista de canales, en **Eventos**. Marca **Me interesa** y Discord te avisa cuando empiece.
- Para apartar tu cupo, abre tu reserva en {#reservar}.""",
    ],
    "reservar": [
        """# Reserva tu aula
**1. Abre un hilo privado en este canal.** Entra a **Hilos** (arriba, junto al nombre del canal), crea uno y marca la opción de hilo **privado**. Ponle el taller y la fecha, por ejemplo: `POO con Python · sáb 17`.

**2. Copia esto en tu hilo y complétalo:**
> **Taller o tutoría:**
> **Fecha y hora:**
> **Aula:** cerrada (mi grupo) o abierta (me uno a un horario publicado)
> **Cuántas personas son (hasta 5):**

**3. Menciona a {@admin}** y te respondemos con los datos para pagar por DeUna o transferencia.

**4. Paga hasta 24 horas antes** y sube el comprobante en el mismo hilo. En un aula abierta, cada quien paga su parte al cierre de inscripciones.

**5. Recibe el enlace de tu aula.** Cuando validamos el pago te lo dejamos en el hilo. Compártelo con tu grupo: quien lo abre entra directo al aula privada, con su canal de voz, el evento con recordatorio y la lista de preparación.

Las políticas de reprogramación y reembolso están en {#reglas}.""",
    ],
    "busco-grupo": [
        """# ¿Vienes sin grupo?
Escribe aquí para juntarte con otras personas que quieren el mismo taller:
> **Taller o tutoría:**
> **Días y horas en que puedo:**
> **Cuántos somos:**

Cuando se junten, uno de ustedes abre la reserva en {#reservar}.

**Arma tu aula:** quien organiza un aula completa de 5 gana 1 hora de tutoría gratis o 20 % menos en su siguiente aula, y el rol {@organizador}.""",
    ],
    "showcase": [
        """# Muro de proyectos
Cada producto terminado en un taller se publica aquí. Comparte:
- El enlace a tu repositorio o a tu página desplegada.
- El taller donde lo hiciste.
- Una captura o un video corto, si quieres.

Todo lo que ves aquí se construyó en un aula de 2 horas.""",
    ],
    "recursos": [
        """# Recursos
Comparte documentación, herramientas y material que te haya servido. Para empezar:
- **GitHub Student Developer Pack:** GitHub Pro gratis para estudiantes, con más uso de Codespaces.
- **GitHub Codespaces:** el entorno donde se abre el kit de cada taller, sin instalar nada.""",
    ],
    "practicas": [
        """# Prácticas y empleos
Ofertas de prácticas y de empleo, y consejos de portafolio y entrevistas.
Si publicas una oferta, incluye la empresa, los requisitos y cómo postular.""",
    ],
    "setup": [
        """# Antes de tu aula
1. Abre el kit del taller en GitHub Codespaces y comprueba que carga.
2. Prueba tu micrófono en {#sala-estudio}.
3. Sube la letra del editor a 18–20 px. Sin Nitro la transmisión llega a 720p y la letra pequeña no se lee.
4. Practica compartir pantalla con **Go Live** en un canal de voz.

Si algo falla, escribe aquí qué hiciste y pega el error como texto.""",
    ],
    "pagos": [
        """# Pagos por validar
1. El organizador sube el comprobante en su hilo de {#reservar}.
2. Reenvía ese mensaje a este canal.
3. Valida el pago en la cuenta.
4. Crea el aula: `python servidor.py aula crear <taller> --inicio "AAAA-MM-DD HH:MM"`
5. Pega en el hilo de la reserva el enlace del aula que te devuelve el comando.
6. Borra el comprobante de aquí cuando ya no haga falta.""",
    ],
    "tutores": [
        """# Guion de un taller (120 minutos)
- **Arranque · 10 min.** Demo del producto final; todos abren el kit.
- **Conceptos · 25 min.** De 3 a 5 ideas clave con diagramas, casi sin código.
- **Construcción por hitos · 60 min.** Tres hitos: tú programas y ellos replican en pantalla.
- **Integración · 15 min.** Conectan su pieza con otra y pasan la prueba.
- **Cierre · 10 min.** Push a GitHub, siguiente taller y encuesta.

Quien se atrasa en un hito salta al siguiente con su rama del kit: el grupo nunca espera a una sola persona.

## Pantallas compartidas
- Cada estudiante transmite con Go Live en el canal de voz del aula y los ves a la vez en la vista de cuadrícula.
- Cuando alguien se traba, entra a su código con VS Code Live Share en vez de dictarle.
- Solo grabas tu pantalla, y con aviso; nunca la de un estudiante sin su permiso.

## Al cerrar cada aula
Insignia del taller, proyecto en {#showcase}, encuesta de una pregunta, 48 horas de soporte en el canal del aula y el siguiente taller recomendado. El aula se archiva a los 7 días: `python servidor.py aula archivar --vencidas`""",
    ],
}

# Mensaje que `aula crear` publica y fija en el canal de texto del aula.
# Marcadores propios: {titulo} {rol} {inicio} {horas} {voz} {evento} {kit}
MENSAJE_AULA = """# {titulo}
{rol}, su aula está lista. La clase es el <t:{inicio}:F> (<t:{inicio}:R>) y dura {horas} en {voz}.

**Antes de la clase**
{kit}- Prueba tu micrófono en el canal de voz.
- Sube la letra del editor a 18–20 px: vas a compartir pantalla con Go Live y sin Nitro llega a 720p.
- Marca **Me interesa** en el evento para que Discord te avise: {evento}

**Durante y después**
- El material y las entregas van en este canal.
- Tienes 48 horas de soporte aquí después de la clase.
- Si necesitas reprogramar, avisa con 24 horas."""

LINEA_KIT = "- Abre el kit del taller en GitHub Codespaces y comprueba que carga{enlace}.\n"


def roles_de_onboarding() -> List[Dict[str, Any]]:
    """Roles que asignan las preguntas del onboarding, en el orden en que aparecen."""
    roles = []
    for pregunta in ONBOARDING:
        for opcion in pregunta["opciones"]:
            clave, nombre = opcion["rol"]
            roles.append({"clave": clave, "nombre": nombre, "permisos": [], "color": 0, "separado": False, "mencionable": False})
    return roles


def roles_de_insignias(fase: int) -> List[Dict[str, Any]]:
    return [
        {
            "clave": catalogo.clave_insignia(t),
            "nombre": f"Insignia · {t['insignia']}",
            "permisos": [],
            "color": COLOR_INSIGNIA[t["nivel"]],
            "separado": False,
            "mencionable": False,
        }
        for t in catalogo.talleres_hasta(fase)
    ]


def roles(fase: int) -> List[Dict[str, Any]]:
    """Roles que debe tener el servidor, de arriba hacia abajo."""
    return ROLES_FIJOS + roles_de_insignias(fase) + (roles_de_onboarding() if AJUSTES["onboarding"] else [])


def todos_los_roles() -> List[Dict[str, Any]]:
    """Todos los roles que el diseño conoce, se usen ya o no."""
    return ROLES_FIJOS + roles_de_insignias(fase=99) + roles_de_onboarding()


def canales() -> List[Dict[str, Any]]:
    """Todos los canales con la clave de su categoría."""
    lista = []
    for categoria in CATEGORIAS:
        for canal in categoria["canales"]:
            lista.append({**canal, "categoria": categoria["clave"]})
    return lista
