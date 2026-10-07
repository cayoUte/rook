"""Catálogo de talleres y tutorías.

Los datos salen del documento «Modelo de negocio: talleres de programación en
aulas de Discord». Cada taller dura 2 horas, se vende por aula (hasta 5
personas) y entrega una pieza de AulaHub.

La columna `fase` dice cuándo abrir cada taller:
    1 = primer mes · 2 = meses 2 y 3 · 3 = meses 4 a 6 · 4 = desde el mes 7

`servidor.py construir` publica la fase 1. Para abrir las siguientes:
    python servidor.py publicar --fase 2
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

PERSONAS_POR_AULA = 5
HORAS_TALLER = 2

# Precio por aula según el nivel.
PRECIOS = {1: 10, 2: 20, 3: 30}

# Etiquetas del foro #catálogo (máximo 20 en total y 20 caracteres cada una).
ETIQUETAS_TIPO = ["Taller", "Tutoría", "Ruta"]
ETIQUETAS_NIVEL = {1: "N1 · $10", 2: "N2 · $20", 3: "N3 · $30"}
ETIQUETAS_TECNOLOGIA = [
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "Bases de datos",
    "Web",
    "DevOps",
    "Algoritmos",
    "Git",
]


def _t(
    id: str,
    nombre: str,
    nivel: int,
    fase: int,
    insignia: str,
    etiquetas: List[str],
    producto: str,
    conecta: str,
) -> Dict[str, Any]:
    return {
        "id": id,
        "nombre": nombre,
        "nivel": nivel,
        "fase": fase,
        "insignia": insignia,
        "etiquetas": etiquetas,
        "producto": producto,
        "conecta": conecta,
    }


TALLERES: List[Dict[str, Any]] = [
    # ── Fase 1 · primer mes ────────────────────────────────────────────────
    _t(
        "github", "GitHub: Git y trabajo en equipo", 1, 1, "GitHub", ["Git"],
        "Repositorio del proyecto con README, issues, ramas, primer pull request y página en GitHub Pages.",
        "Todos: cada producto vive en GitHub y se entrega por pull request.",
    ),
    _t(
        "html-css", "HTML y CSS", 1, 1, "HTML y CSS", ["Web"],
        "Landing responsive de AulaHub (catálogo, precios, preguntas frecuentes) en GitHub Pages, con variables CSS de diseño.",
        "React reutiliza sus estilos; Programación funcional con JS le carga el catálogo real.",
    ),
    _t(
        "algoritmos", "Algoritmos y lógica de programación", 1, 1, "Algoritmos y lógica", ["Algoritmos"],
        "Simulador de inscripciones en consola: menú, cupo máximo de 5, reparto del precio al centavo y lista de espera.",
        "Sus reglas pasan a POO con Python y de ahí a las APIs.",
    ),
    _t(
        "poo-python", "POO con Python", 2, 1, "POO con Python", ["Python"],
        "Librería `aulahub-core`: clases Taller, Aula, Estudiante e Inscripción con reglas de negocio, excepciones propias y pruebas.",
        "FastAPI la importa; la usan el bot de Discord y el planificador.",
    ),
    # ── Fase 2 · meses 2 y 3 ───────────────────────────────────────────────
    _t(
        "sql", "SQL con PostgreSQL", 2, 2, "SQL con PostgreSQL", ["Bases de datos"],
        "Esquema con llaves, restricciones y datos semilla, vistas de reportes y una transacción que impide pasar de 5 cupos.",
        "Base de datos de FastAPI y Spring Boot; fuente de Pandas y del asistente con IA.",
    ),
    _t(
        "fastapi", "API REST con FastAPI", 2, 2, "FastAPI", ["Python"],
        "API Aulas v1 que cumple el contrato común, sobre PostgreSQL, con documentación automática.",
        "React, bot y Pandas; OAuth2 la protege; Docker la empaqueta.",
    ),
    _t(
        "react", "Interfaces con React", 2, 2, "React", ["Web", "JavaScript"],
        "App web con catálogo, cupos por aula, inscripción y «mis aulas», construida contra el contrato común.",
        "Cualquiera de las 3 APIs cambiando una variable; estilos de HTML y CSS; login con OAuth2.",
    ),
    _t(
        "js-funcional", "Programación funcional con JavaScript", 2, 2, "JS funcional", ["JavaScript"],
        "Módulo `aulahub-stats` de funciones puras (ocupación, ingresos, ranking) y catálogo dinámico en la landing.",
        "Landing, panel de React y servicio de tiempo real.",
    ),
    _t(
        "integracion", "Integración · Aula de integración", 3, 2, "Aula de integración", [],
        "Hasta cinco personas traen piezas distintas (landing, React, API, base de datos y, cuando existan, auth y bot) y las conectan y despliegan en 2 horas.",
        "Todo. Requisito: 2 talleres previos por persona.",
    ),
    # ── Fase 3 · meses 4 a 6 ───────────────────────────────────────────────
    _t(
        "express", "API REST con Express.js", 2, 3, "Express.js", ["JavaScript"],
        "La misma API Aulas v1 en Node, sobre MongoDB.",
        "React la usa sin cambios, igual que FastAPI y Spring Boot; tiempo real.",
    ),
    _t(
        "mongodb", "NoSQL con MongoDB", 2, 3, "MongoDB", ["Bases de datos"],
        "Colecciones para bitácora de aulas, comentarios y actividad, con índices y agregaciones.",
        "Base de datos de Express; el bot guarda ahí sus registros.",
    ),
    _t(
        "estructuras", "Optimización de código y estructuras de datos", 2, 3, "Estructuras de datos", ["Algoritmos"],
        "Lista de espera (cola), ranking (heap), autocompletado de talleres (trie) y un refactor medido con benchmarks.",
        "Búsqueda y lista de espera de las APIs; comandos del bot.",
    ),
    _t(
        "oauth2", "Autenticación y autorización con OAuth2", 3, 3, "OAuth2", ["Web"],
        "«Iniciar sesión con Discord» (flujo Authorization Code) que emite un token con los roles del servidor, y un middleware que protege la API (contrato v2).",
        "React, las 3 APIs, bot, Next.js y app móvil.",
    ),
    _t(
        "spring-boot", "API REST con Spring Boot", 3, 3, "Spring Boot", ["Java"],
        "API Aulas v1 en Java con Spring Data JPA y PostgreSQL.",
        "React (intercambiable); pruebas con JUnit; eventos de pago con RabbitMQ.",
    ),
    _t(
        "linux", "Servidores Linux (familia RHEL)", 3, 3, "Servidores Linux", ["DevOps"],
        "Servidor listo: SSH con llaves, firewall, SELinux, la API como servicio systemd y Nginx con HTTPS.",
        "Aloja APIs, front y bot; base de Docker y CI/CD.",
    ),
    # ── Fase 4 · desde el mes 7, en el orden que pida la lista de espera ───
    _t(
        "bots-discord", "Python · Bots de Discord", 2, 4, "Bots de Discord", ["Python"],
        "Bot con los comandos /talleres, /inscribirme y /mis-aulas que crea los canales y roles de cada aula.",
        "API Aulas, roles de OAuth2, bitácora en MongoDB.",
    ),
    _t(
        "pandas", "Python · Análisis de datos con Pandas", 2, 4, "Pandas", ["Python"],
        "Reporte de ocupación, ingresos por taller y recompra, exportado a Excel con gráficos.",
        "PostgreSQL, API y módulo de estadísticas de JS.",
    ),
    _t(
        "grafos", "Python · Algoritmos en grafos: el planificador", 2, 4, "Algoritmos en grafos", ["Python", "Algoritmos"],
        "Servicio que encuentra el horario común de 5 personas, arma grupos por nivel y ordena los talleres por requisitos (orden topológico del propio catálogo).",
        "API (sugerir horario), bot y rutas.",
    ),
    _t(
        "rag", "Python · IA aplicada: asistente con RAG", 3, 4, "Asistente con RAG", ["Python"],
        "Endpoint que responde dudas con el material de los talleres, con embeddings en pgvector y un modelo gratuito o local.",
        "FastAPI, PostgreSQL y el comando /pregunta del bot.",
    ),
    _t(
        "typescript", "TypeScript · De JavaScript a TypeScript", 2, 4, "TypeScript", ["TypeScript"],
        "SDK tipado del contrato (tipos generados desde OpenAPI y cliente) publicado como paquete.",
        "React, Next.js y app móvil: si una API rompe el contrato, falla la compilación.",
    ),
    _t(
        "nextjs", "TypeScript · Next.js full-stack", 3, 4, "Next.js", ["TypeScript", "Web"],
        "Sitio público renderizado en servidor (catálogo indexable) con páginas de certificado verificable por enlace.",
        "API, OAuth2 y SDK tipado; reemplaza la landing.",
    ),
    _t(
        "websockets", "TypeScript · Tiempo real con WebSockets", 3, 4, "Tiempo real", ["TypeScript"],
        "Servicio de notificaciones: cupos en vivo, «tu aula empieza en 10 minutos» y pago confirmado.",
        "React, eventos de RabbitMQ y bot.",
    ),
    _t(
        "react-native", "TypeScript · App móvil con React Native (Expo)", 3, 4, "React Native", ["TypeScript"],
        "App «Mis aulas» con inicio de sesión y recordatorios.",
        "API, OAuth2, SDK tipado y notificaciones.",
    ),
    _t(
        "java-moderno", "Java · Java moderno: POO, colecciones y streams", 2, 4, "Java moderno", ["Java"],
        "Librería `aulahub-core-java` con records, enums e interfaces selladas, con las mismas reglas del core de Python.",
        "Spring Boot, patrones de diseño y JUnit.",
    ),
    _t(
        "patrones", "Java · Patrones de diseño", 2, 4, "Patrones de diseño", ["Java"],
        "Refactor del core con Strategy (políticas de precio), Observer (eventos de inscripción), Factory y Repository.",
        "Spring Boot; el Observer se convierte en eventos de RabbitMQ.",
    ),
    _t(
        "junit", "Java · Pruebas con JUnit 5 y Mockito", 2, 4, "JUnit y Mockito", ["Java"],
        "Pruebas unitarias del core y pruebas de la API contra el contrato.",
        "Spring Boot y CI/CD; la prueba de contrato sirve para cualquier API.",
    ),
    _t(
        "rabbitmq", "Java · Mensajería con Spring y RabbitMQ", 3, 4, "RabbitMQ", ["Java"],
        "Servicio de pagos que publica los eventos `InscripcionCreada` y `PagoConfirmado`.",
        "Tiempo real, bot (anuncia en Discord) y Pandas.",
    ),
    _t(
        "docker", "Integración · Docker y Docker Compose", 3, 4, "Docker", ["DevOps"],
        "Un `docker-compose.yml` que levanta el ecosistema con un comando: front, la API que elijas, base de datos y bot.",
        "Todo; Linux y CI/CD lo despliegan.",
    ),
    _t(
        "ci-cd", "Integración · CI/CD con GitHub Actions", 3, 4, "CI/CD", ["DevOps", "Git"],
        "Pipeline que corre las pruebas y la prueba de contrato, construye la imagen y despliega al servidor en cada merge.",
        "GitHub, pruebas, Docker y Linux.",
    ),
    _t(
        "seguridad-web", "Integración · Seguridad web (OWASP Top 10)", 3, 4, "Seguridad web", ["DevOps", "Web"],
        "Auditoría y parches de tu propia API: inyección, acceso a datos ajenos (IDOR), secretos, CORS y límite de peticiones.",
        "Las 3 APIs y OAuth2.",
    ),
]

# Tutorías: misma aula de hasta 5 personas con un solo pago.
TUTORIAS: List[Dict[str, str]] = [
    {"formato": "Express", "duracion": "1 h", "precio": "$10", "sirve": "una duda puntual o un ejercicio tipo"},
    {"formato": "Estándar", "duracion": "2 h", "precio": "$18", "sirve": "un tema completo con ejercicios"},
    {"formato": "Maratón antes del examen", "duracion": "3 h", "precio": "$25", "sirve": "temario del parcial, simulacro y corrección"},
    {"formato": "Plan de semestre", "duracion": "8 sesiones de 2 h", "precio": "$120 prepagado", "sirve": "un grupo fijo acompañado toda la materia"},
]

# Ajusta esta lista a las materias que dominas y a tu malla.
MATERIAS: List[str] = [
    "**Programación:** lógica, Programación I y II, POO y estructuras de datos.",
    "**Bases de datos:** modelo entidad-relación, normalización y SQL.",
    "**Matemáticas:** cálculo diferencial e integral, álgebra lineal, matemática discreta, probabilidad y estadística.",
    "**Otras de la carrera:** ingeniería de software (UML y requisitos), sistemas operativos o redes.",
]

TITULO_TUTORIAS = "Tutorías: Express, Estándar, Maratón y Plan de semestre"


def dinero(valor: float) -> str:
    """Formatea un monto en dólares con coma decimal: 6.666 → «$6,67», 5 → «$5»."""
    centavos = round(valor * 100)
    if centavos % 100 == 0:
        return f"${centavos // 100}"
    return f"${centavos // 100},{centavos % 100:02d}"


def por_persona(precio: int) -> str:
    partes = []
    for n in range(1, PERSONAS_POR_AULA + 1):
        etiqueta = "1 persona" if n == 1 else f"{n} personas"
        partes.append(f"{etiqueta} {dinero(precio / n)}")
    return " · ".join(partes)


def taller(id: str) -> Dict[str, Any]:
    for t in TALLERES:
        if t["id"] == id:
            return t
    raise KeyError(id)


def buscar_taller(texto: str) -> Optional[Dict[str, Any]]:
    """Encuentra un taller por su id o por su nombre exacto (sin distinguir mayúsculas)."""
    buscado = texto.strip().lower()
    for t in TALLERES:
        if buscado in (t["id"], t["nombre"].lower()):
            return t
    return None


def talleres_hasta(fase: int) -> List[Dict[str, Any]]:
    return [t for t in TALLERES if t["fase"] <= fase]


def clave_insignia(t: Dict[str, Any]) -> str:
    return f"insignia:{t['id']}"


def etiquetas_taller(t: Dict[str, Any]) -> List[str]:
    return ["Taller", ETIQUETAS_NIVEL[t["nivel"]]] + list(t["etiquetas"])


def texto_taller(t: Dict[str, Any]) -> str:
    """Cuerpo de la publicación del taller en #catálogo (con marcadores {#canal} y {@rol})."""
    precio = PRECIOS[t["nivel"]]
    return "\n".join(
        [
            f"**Nivel N{t['nivel']} · ${precio} por aula** · {HORAS_TALLER} horas en vivo · hasta {PERSONAS_POR_AULA} personas",
            "",
            "**Qué construyes**",
            t["producto"],
            "",
            "**Con qué se conecta**",
            t["conecta"],
            "",
            "**Cuánto paga cada persona**",
            por_persona(precio),
            "",
            f"Al terminar te llevas la insignia {{@{clave_insignia(t)}}}.",
            "Reserva en {#reservar}. Si aún no tienes grupo, pasa por {#busco-grupo}.",
        ]
    )


def texto_tutorias() -> str:
    lineas = [
        f"La misma aula de hasta {PERSONAS_POR_AULA} personas, con un solo pago que el grupo reparte.",
        "",
        "**Formatos**",
    ]
    for f in TUTORIAS:
        lineas.append(f"- **{f['formato']}** · {f['duracion']} · {f['precio']} por aula: {f['sirve']}.")
    lineas += ["", "**Materias**"]
    lineas += [f"- {m}" for m in MATERIAS]
    lineas += [
        "",
        "**Después de la tutoría**",
        "Cada tutoría cierra con un diagnóstico y un taller recomendado. Si lo reservas en los 7 días siguientes, ese taller te sale 20 % más barato.",
        "",
        "Explicamos y practicamos con ejercicios parecidos; no resolvemos deberes, proyectos ni pruebas calificadas. Las reglas completas están en {#reglas}.",
        "Reserva en {#reservar}.",
    ]
    return "\n".join(lineas)
