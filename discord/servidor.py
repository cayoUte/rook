#!/usr/bin/env python3
"""Construye y opera el servidor de Discord de los talleres.

    python servidor.py plan                     muestra el diseño sin tocar Discord
    python servidor.py construir                crea en el servidor lo que falte
    python servidor.py verificar                compara el servidor con el diseño
    python servidor.py publicar --fase 2        abre los talleres de una fase
    python servidor.py aula crear poo-python --inicio "2026-10-17 10:00" --miembros ana luis
    python servidor.py aula listar
    python servidor.py aula archivar poo-python-17oct
    python servidor.py aula archivar --vencidas

Lee el token del bot del archivo .env que está junto a este script.
Solo usa la biblioteca estándar de Python (3.9 o superior).
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import catalogo
import diseno

VERSION = "1.0"
AQUI = Path(__file__).resolve().parent
API = os.environ.get("DISCORD_API", "https://discord.com/api/v10").rstrip("/")
AGENTE = f"DiscordBot (https://discord.com/developers/docs, {VERSION}) servidor.py"

TEXTO, VOZ, CATEGORIA, ANUNCIOS, ESCENARIO, FORO = 0, 2, 4, 5, 13, 15
TIPOS = {"texto": TEXTO, "voz": VOZ, "anuncios": ANUNCIOS, "escenario": ESCENARIO, "foro": FORO}
NOMBRE_TIPO = {TEXTO: "texto", VOZ: "voz", CATEGORIA: "categoría", ANUNCIOS: "anuncios", ESCENARIO: "escenario", FORO: "foro"}
SOLO_EN_COMUNIDAD = {ANUNCIOS, ESCENARIO, FORO}
DE_VOZ = {VOZ, ESCENARIO}
CON_NOMBRE_DE_TEXTO = {TEXTO, ANUNCIOS, FORO}

SILENCIOSO = 1 << 12  # el mensaje no envía notificaciones
SIN_MENCIONES: Dict[str, List[str]] = {"parse": []}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Bits de permisos de Discord (developers/topics/permissions).
PERMISOS = {
    "CREATE_INSTANT_INVITE": 0, "KICK_MEMBERS": 1, "BAN_MEMBERS": 2, "ADMINISTRATOR": 3,
    "MANAGE_CHANNELS": 4, "MANAGE_GUILD": 5, "ADD_REACTIONS": 6, "VIEW_AUDIT_LOG": 7,
    "PRIORITY_SPEAKER": 8, "STREAM": 9, "VIEW_CHANNEL": 10, "SEND_MESSAGES": 11,
    "SEND_TTS_MESSAGES": 12, "MANAGE_MESSAGES": 13, "EMBED_LINKS": 14, "ATTACH_FILES": 15,
    "READ_MESSAGE_HISTORY": 16, "MENTION_EVERYONE": 17, "USE_EXTERNAL_EMOJIS": 18,
    "VIEW_GUILD_INSIGHTS": 19, "CONNECT": 20, "SPEAK": 21, "MUTE_MEMBERS": 22,
    "DEAFEN_MEMBERS": 23, "MOVE_MEMBERS": 24, "USE_VAD": 25, "CHANGE_NICKNAME": 26,
    "MANAGE_NICKNAMES": 27, "MANAGE_ROLES": 28, "MANAGE_WEBHOOKS": 29,
    "MANAGE_GUILD_EXPRESSIONS": 30, "USE_APPLICATION_COMMANDS": 31, "REQUEST_TO_SPEAK": 32,
    "MANAGE_EVENTS": 33, "MANAGE_THREADS": 34, "CREATE_PUBLIC_THREADS": 35,
    "CREATE_PRIVATE_THREADS": 36, "USE_EXTERNAL_STICKERS": 37, "SEND_MESSAGES_IN_THREADS": 38,
    "USE_EMBEDDED_ACTIVITIES": 39, "MODERATE_MEMBERS": 40, "USE_SOUNDBOARD": 42,
    "CREATE_GUILD_EXPRESSIONS": 43, "CREATE_EVENTS": 44, "USE_EXTERNAL_SOUNDS": 45,
    "SEND_VOICE_MESSAGES": 46, "SET_VOICE_CHANNEL_STATUS": 48, "SEND_POLLS": 49,
    "USE_EXTERNAL_APPS": 50, "PIN_MESSAGES": 51, "BYPASS_SLOWMODE": 52,
}

AYUDAS = {
    401: "El token no es válido. Copia de nuevo el token del bot en el archivo .env.",
    50001: "Al bot le falta acceso. Invítalo al servidor con permiso de Administrador.",
    50013: "Al bot le faltan permisos. Necesita el permiso de Administrador.",
    60003: "El servidor exige verificación en dos pasos para moderar: actívala en tu cuenta de Discord o quita esa exigencia en Ajustes del servidor → Seguridad.",
    30005: "El servidor llegó al máximo de 250 roles.",
    30013: "El servidor llegó al máximo de 500 canales.",
    20031: "Discord rechazó un nombre o texto por contener palabras no permitidas.",
    350000: "Discord pide al menos 7 canales predeterminados y que en 5 de ellos pueda escribir cualquiera.",
}


def bits(nombres: Iterable[str]) -> int:
    valor = 0
    for nombre in nombres:
        valor |= 1 << PERMISOS[nombre]
    return valor


def nombres_de(valor: int) -> List[str]:
    return [n for n, b in PERMISOS.items() if valor & (1 << b)]


def normal(nombre: str, tipo: int) -> str:
    """Nombre comparable: Discord pone los canales de texto en minúsculas y con guiones."""
    nombre = unicodedata.normalize("NFC", nombre or "").strip().lower()
    return nombre.replace(" ", "-") if tipo in CON_NOMBRE_DE_TEXTO else nombre


def etiqueta(tipo: int, nombre: str) -> str:
    """Cómo se nombra un canal en el registro: #texto, voz «Sala» o categoría «Inicio»."""
    if tipo == TEXTO:
        return f"#{nombre}"
    if tipo in (ANUNCIOS, FORO):
        return f"#{nombre} ({NOMBRE_TIPO[tipo]})"
    return f"{NOMBRE_TIPO.get(tipo, 'canal')} «{nombre}»"


def slug(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")


def creado_en(id: str) -> datetime:
    """Fecha de creación que lleva dentro cada id de Discord."""
    return datetime.fromtimestamp(((int(id) >> 22) + 1420070400000) / 1000, tz=timezone.utc)


# ── Registro ────────────────────────────────────────────────────────────────


class Registro:
    """Escribe en la consola y en registro.log lo que hace cada ejecución."""

    def __init__(self, ruta: Optional[Path] = None, silencio: bool = False) -> None:
        self.ruta = ruta
        self.silencio = silencio
        self.creados = 0
        self.iguales = 0
        self.avisos: List[str] = []
        self.errores: List[str] = []

    def linea(self, texto: str = "") -> None:
        if not self.silencio:
            print(texto)
        if self.ruta:
            with open(self.ruta, "a", encoding="utf-8") as archivo:
                archivo.write(texto + "\n")

    def inicio(self, orden: str) -> None:
        self.linea()
        self.linea(f"##### {datetime.now().astimezone().isoformat(timespec='seconds')} · servidor.py {orden}")

    def paso(self, titulo: str) -> None:
        self.linea()
        self.linea(f"== {titulo}")

    def hecho(self, texto: str) -> None:
        self.creados += 1
        self.linea(f"  + {texto}")

    def igual(self, texto: str) -> None:
        self.iguales += 1
        self.linea(f"  = {texto}")

    def nota(self, texto: str) -> None:
        self.linea(f"    {texto}")

    def aviso(self, texto: str) -> None:
        self.avisos.append(texto)
        self.linea(f"  ! {texto}")

    def error(self, texto: str) -> None:
        self.errores.append(texto)
        self.linea(f"  x {texto}")


# ── Cliente de la API ───────────────────────────────────────────────────────


class ErrorApi(Exception):
    def __init__(self, estado: int, carga: Dict[str, Any], metodo: str, ruta: str) -> None:
        self.estado = estado
        self.codigo = carga.get("code")
        self.mensaje = str(carga.get("message") or "")
        self.campos = _aplanar(carga.get("errors"))
        self.metodo = metodo
        self.ruta = ruta
        super().__init__(self.texto())

    def texto(self) -> str:
        partes = [f"{self.metodo} {self.ruta} → HTTP {self.estado}"]
        if self.codigo is not None:
            partes.append(f"(código {self.codigo})")
        partes.append(self.mensaje)
        if self.campos:
            partes.append("[" + "; ".join(self.campos) + "]")
        ayuda = AYUDAS.get(self.codigo) or AYUDAS.get(self.estado)  # type: ignore[arg-type]
        if ayuda:
            partes.append("→ " + ayuda)
        return " ".join(p for p in partes if p)


class ErrorDeUso(Exception):
    """Algo que debe corregir quien ejecuta el script; se muestra sin traza."""


def _aplanar(errores: Any, prefijo: str = "") -> List[str]:
    """Convierte el árbol `errors` de Discord en líneas «campo: mensaje»."""
    if not isinstance(errores, dict):
        return []
    lineas: List[str] = []
    for clave, valor in errores.items():
        if clave == "_errors" and isinstance(valor, list):
            for e in valor:
                lineas.append(f"{prefijo or 'cuerpo'}: {e.get('message')}")
        else:
            lineas += _aplanar(valor, f"{prefijo}.{clave}" if prefijo else str(clave))
    return lineas


class Api:
    def __init__(self, token: str, base: str = API, dormir: Callable[[float], None] = time.sleep) -> None:
        self.token = token
        self.base = base
        self.dormir = dormir
        self.avisar: Callable[[str], None] = lambda mensaje: None
        self.escrituras = 0

    def _esperar(self, segundos: float) -> None:
        if segundos >= 5:
            self.avisar(f"Discord pide esperar {segundos:.0f} s antes de seguir…")
        self.dormir(segundos)

    def pedir(self, metodo: str, ruta: str, cuerpo: Any = None, consulta: Optional[Dict[str, Any]] = None) -> Any:
        url = self.base + ruta
        if consulta:
            url += "?" + urllib.parse.urlencode(consulta)
        cabeceras = {"Authorization": f"Bot {self.token}", "User-Agent": AGENTE, "Accept": "application/json"}
        datos: Optional[bytes] = None
        if cuerpo is not None:
            datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
            cabeceras["Content-Type"] = "application/json"
        elif metodo != "GET":
            datos = b""  # Discord exige Content-Length también en las escrituras sin cuerpo
        if metodo != "GET":
            self.escrituras += 1

        intentos = 6
        for intento in range(1, intentos + 1):
            peticion = urllib.request.Request(url, data=datos, method=metodo, headers=cabeceras)
            try:
                with urllib.request.urlopen(peticion, timeout=30) as respuesta:
                    texto = respuesta.read().decode("utf-8")
                    self._respetar_limite(respuesta.headers)
                    return json.loads(texto) if texto.strip() else None
            except urllib.error.HTTPError as e:
                texto = e.read().decode("utf-8", "replace")
                try:
                    carga = json.loads(texto)
                    if not isinstance(carga, dict):
                        carga = {"message": texto[:300]}
                except ValueError:
                    carga = {"message": texto[:300]}
                if e.code == 429 and intento < intentos:
                    espera = float(carga.get("retry_after") or e.headers.get("Retry-After") or 1)
                    if espera > 180:
                        raise ErrorApi(e.code, carga, metodo, ruta) from None
                    self._esperar(espera + 0.25)
                    continue
                if e.code in (500, 502, 503, 504) and intento < intentos:
                    self.dormir(min(2.0**intento, 20.0))
                    continue
                raise ErrorApi(e.code, carga, metodo, ruta) from None
            except (OSError, http.client.HTTPException) as e:
                # Una lectura se puede repetir sin riesgo; una escritura quizá sí llegó, así que no se repite a ciegas.
                if metodo == "GET" and intento < 4:
                    self.dormir(2.0 * intento)
                    continue
                raise ErrorDeUso(
                    f"Se cortó la conexión con Discord ({e}). Revisa tu internet y vuelve a ejecutar: lo ya creado se conserva."
                ) from None
        raise ErrorDeUso(f"Discord no respondió a {metodo} {ruta} después de {intentos} intentos.")

    def _respetar_limite(self, cabeceras: Any) -> None:
        """Si se agotó el cupo de esta ruta, espera a que se renueve antes de seguir."""
        try:
            if cabeceras.get("X-RateLimit-Remaining") == "0":
                espera = float(cabeceras.get("X-RateLimit-Reset-After") or 0)
                if 0 < espera <= 120:
                    self._esperar(espera + 0.05)
        except (TypeError, ValueError):
            pass

    def get(self, ruta: str, **consulta: Any) -> Any:
        return self.pedir("GET", ruta, consulta=consulta or None)

    def post(self, ruta: str, cuerpo: Any = None) -> Any:
        return self.pedir("POST", ruta, cuerpo if cuerpo is not None else {})

    def patch(self, ruta: str, cuerpo: Any) -> Any:
        return self.pedir("PATCH", ruta, cuerpo)

    def put(self, ruta: str, cuerpo: Any = None) -> Any:
        return self.pedir("PUT", ruta, cuerpo)

    def delete(self, ruta: str) -> Any:
        return self.pedir("DELETE", ruta)


# ── Configuración y estado ──────────────────────────────────────────────────


def leer_env(ruta: Path) -> Dict[str, str]:
    valores: Dict[str, str] = {}
    if not ruta.exists():
        return valores
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def cargar_config(carpeta: Path) -> Tuple[str, Optional[str]]:
    env = leer_env(carpeta / ".env")
    token = (os.environ.get("DISCORD_TOKEN") or env.get("DISCORD_TOKEN") or "").strip()
    servidor = (os.environ.get("GUILD_ID") or env.get("GUILD_ID") or "").strip() or None
    if token.lower().startswith("bot "):
        token = token[4:].strip()
    if not token or token.startswith("pega-"):
        raise ErrorDeUso(
            "Falta el token del bot. Copia .env.example como .env y pega el token en DISCORD_TOKEN "
            "(portal de desarrolladores → tu aplicación → Bot → Reset Token)."
        )
    if servidor and not servidor.isdigit():
        raise ErrorDeUso("GUILD_ID debe ser el id numérico del servidor, o quedar vacío.")
    return token, servidor


def cargar_estado(ruta: Path, servidor: str) -> Dict[str, Any]:
    vacio: Dict[str, Any] = {"servidor": servidor, "roles": {}, "canales": {}, "hecho": {}}
    if not ruta.exists():
        return vacio
    try:
        estado = json.loads(ruta.read_text(encoding="utf-8"))
    except ValueError:
        return vacio
    if not isinstance(estado, dict) or estado.get("servidor") != servidor:
        return vacio  # el archivo es de otro servidor
    for clave in ("roles", "canales", "hecho"):
        if not isinstance(estado.get(clave), dict):
            estado[clave] = {}
    return estado


# ── El servidor ─────────────────────────────────────────────────────────────


class Servidor:
    """Lo que hay en Discord, lo que dice el diseño y cómo se corresponden."""

    def __init__(self, api: Api, reg: Registro, carpeta: Path, id_pedido: Optional[str] = None) -> None:
        self.api = api
        self.reg = reg
        self.carpeta = carpeta
        self.bot = self._identificar()
        self.id = self._elegir_servidor(id_pedido)
        self.ruta_estado = carpeta / "estado.json"
        self.estado = cargar_estado(self.ruta_estado, self.id)
        self.guild: Dict[str, Any] = {}
        self.roles: List[Dict[str, Any]] = []
        self.canales: List[Dict[str, Any]] = []
        self._espec_roles = {r["clave"]: r for r in diseno.todos_los_roles()}
        self._espec_canales: Dict[str, Dict[str, Any]] = {}
        for categoria in diseno.CATEGORIAS:
            self._espec_canales[categoria["clave"]] = {**categoria, "tipo_id": CATEGORIA}
        for canal in diseno.canales():
            self._espec_canales[canal["clave"]] = {**canal, "tipo_id": TIPOS[canal["tipo"]]}
        self.cargar()
        self._comprobar_permisos()

    # -- arranque --

    def _identificar(self) -> Dict[str, Any]:
        try:
            return self.api.get("/users/@me")
        except ErrorApi as e:
            if e.estado == 401:
                raise ErrorDeUso(AYUDAS[401]) from None
            raise

    def enlace_de_invitacion(self) -> str:
        return f"https://discord.com/oauth2/authorize?client_id={self.bot['id']}&scope=bot&permissions=8"

    def _elegir_servidor(self, id_pedido: Optional[str]) -> str:
        servidores = self.api.get("/users/@me/guilds")
        if id_pedido:
            if not any(g["id"] == id_pedido for g in servidores):
                raise ErrorDeUso(
                    f"El bot no está en el servidor {id_pedido}. Invítalo con este enlace y vuelve a ejecutar:\n  {self.enlace_de_invitacion()}"
                )
            return id_pedido
        if not servidores:
            raise ErrorDeUso(
                "El bot todavía no está en ningún servidor. Abre este enlace, elige tu servidor, autoriza y vuelve a ejecutar:\n"
                f"  {self.enlace_de_invitacion()}"
            )
        if len(servidores) > 1:
            lista = "\n".join(f"  {g['id']}  {g['name']}" for g in servidores)
            raise ErrorDeUso(f"El bot está en varios servidores. Pon el id del correcto en GUILD_ID dentro de .env:\n{lista}")
        return servidores[0]["id"]

    def cargar(self) -> None:
        self.guild = self.api.get(f"/guilds/{self.id}")
        self.roles = self.api.get(f"/guilds/{self.id}/roles")
        self.canales = self.api.get(f"/guilds/{self.id}/channels")

    def _comprobar_permisos(self) -> None:
        miembro = self.api.get(f"/guilds/{self.id}/members/{self.bot['id']}")
        mios = set(miembro.get("roles", [])) | {self.id}
        permisos = 0
        for rol in self.roles:
            if rol["id"] in mios:
                permisos |= int(rol["permissions"])
        if not permisos & bits(["ADMINISTRATOR"]):
            raise ErrorDeUso(
                "El bot no tiene permiso de Administrador en el servidor. Vuelve a invitarlo con este enlace:\n"
                f"  {self.enlace_de_invitacion()}"
            )

    def guardar_estado(self) -> None:
        self.ruta_estado.write_text(json.dumps(self.estado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def marcar(self, clave: str) -> None:
        self.estado["hecho"][clave] = True

    def ya(self, clave: str) -> bool:
        return bool(self.estado["hecho"].get(clave))

    def pendiente(self, que: str, valor: Optional[bool] = None) -> bool:
        """Anota (o consulta) que falta ordenar «roles» o «canales» porque se creó alguno."""
        clave = f"ordenar_{que}"
        if valor is not None:
            self.estado["hecho"][clave] = valor
        return bool(self.estado["hecho"].get(clave))

    # -- roles --

    def rol(self, clave: str) -> Optional[Dict[str, Any]]:
        if clave == "@everyone":
            return next((r for r in self.roles if r["id"] == self.id), None)
        id_guardado = self.estado["roles"].get(clave)
        if id_guardado:
            encontrado = next((r for r in self.roles if r["id"] == id_guardado), None)
            if encontrado:
                return encontrado
        espec = self._espec_roles.get(clave)
        if not espec:
            return None
        buscado = espec["nombre"].strip().lower()
        for rol in self.roles:
            if not rol.get("managed") and rol["id"] != self.id and rol["name"].strip().lower() == buscado:
                return rol
        return None

    def id_rol(self, clave: str) -> str:
        rol = self.rol(clave)
        if not rol:
            raise ErrorDeUso(f"No encuentro el rol «{clave}» en el servidor. Ejecuta primero: python servidor.py construir")
        return rol["id"]

    # -- canales --

    def canal(self, clave: str) -> Optional[Dict[str, Any]]:
        return self.localizar(clave)[0]

    def localizar(self, clave: str) -> Tuple[Optional[Dict[str, Any]], bool]:
        """Devuelve el canal de esa clave y si se encontró por el id guardado en estado.json."""
        id_guardado = self.estado["canales"].get(clave)
        if id_guardado:
            encontrado = next((c for c in self.canales if c["id"] == id_guardado), None)
            if encontrado:
                return encontrado, True
        espec = self._espec_canales.get(clave)
        if not espec:
            return None, False
        tipo = espec["tipo_id"]
        buscado = normal(espec["nombre"], tipo)
        ocupados = {v for k, v in self.estado["canales"].items() if k != clave}
        candidatos = [
            c for c in self.canales
            if c["type"] == tipo and normal(c.get("name") or "", tipo) == buscado and c["id"] not in ocupados
        ]
        if tipo != CATEGORIA:
            categoria = self.canal(espec["categoria"])
            if categoria:
                for c in candidatos:
                    if c.get("parent_id") == categoria["id"]:
                        return c, False
        return (candidatos[0], False) if candidatos else (None, False)

    def id_canal(self, clave: str) -> str:
        canal = self.canal(clave)
        if not canal:
            nombre = self._espec_canales.get(clave, {}).get("nombre", clave)
            raise ErrorDeUso(f"No encuentro «{nombre}» en el servidor. Ejecuta primero: python servidor.py construir")
        return canal["id"]

    def recordar_canal(self, clave: str, canal: Dict[str, Any]) -> None:
        self.estado["canales"][clave] = canal["id"]
        self.canales = [c for c in self.canales if c["id"] != canal["id"]] + [canal]

    def recordar_rol(self, clave: str, rol: Dict[str, Any]) -> None:
        self.estado["roles"][clave] = rol["id"]
        self.roles = [r for r in self.roles if r["id"] != rol["id"]] + [rol]

    # -- permisos y textos --

    def sobrescrituras(self, permisos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "id": self.id_rol(p["rol"]),
                "type": 0,
                "allow": str(bits(p.get("permite", []))),
                "deny": str(bits(p.get("niega", []))),
            }
            for p in permisos
        ]

    def permisos_de(self, espec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Permisos de un canal del diseño: los suyos o los de su categoría."""
        if "permisos" in espec:
            return espec["permisos"]
        categoria = self._espec_canales.get(espec.get("categoria", ""))
        return categoria["permisos"] if categoria else []

    def resolver(self, texto: str, estricto: bool = True) -> str:
        """Cambia {#canal}, {@rol} y {servidor} por menciones reales."""

        def canal(m: "re.Match[str]") -> str:
            encontrado = self.canal(m.group(1))
            if encontrado:
                return f"<#{encontrado['id']}>"
            if estricto:
                raise ErrorDeUso(f"El texto menciona el canal «{m.group(1)}», que no existe en el servidor.")
            return "#" + str(self._espec_canales.get(m.group(1), {}).get("nombre", m.group(1)))

        def rol(m: "re.Match[str]") -> str:
            encontrado = self.rol(m.group(1))
            if encontrado:
                return f"<@&{encontrado['id']}>"
            if estricto:
                raise ErrorDeUso(f"El texto menciona el rol «{m.group(1)}», que no existe en el servidor.")
            return "@" + str(self._espec_roles.get(m.group(1), {}).get("nombre", m.group(1)))

        texto = re.sub(r"\{#([a-z0-9:-]+)\}", canal, texto)
        texto = re.sub(r"\{@([a-z0-9:-]+)\}", rol, texto)
        return texto.replace("{servidor}", self.guild.get("name", "el servidor"))


# ── Pasos de `construir` ────────────────────────────────────────────────────


def paso_roles(s: Servidor, fase: int) -> None:
    base = bits(diseno.PERMISOS_BASE)
    todos = s.rol("@everyone") or {}
    if int(todos.get("permissions", 0)) == base:
        s.reg.igual("@everyone: permisos base")
    elif s.ya("permisos_base"):
        s.reg.aviso("Los permisos de @everyone ya no son los del diseño; no los toco.")
    else:
        actualizado = s.api.patch(f"/guilds/{s.id}/roles/{s.id}", {"permissions": str(base)})
        s.roles = [r for r in s.roles if r["id"] != s.id] + [actualizado]
        s.reg.hecho("@everyone: permisos base")
    s.marcar("permisos_base")
    asegurar_roles(s, diseno.roles(fase))


def asegurar_roles(s: Servidor, especificaciones: List[Dict[str, Any]]) -> None:
    for espec in especificaciones:
        existente = s.rol(espec["clave"])
        if existente:
            s.estado["roles"][espec["clave"]] = existente["id"]
            s.reg.igual(f"rol {espec['nombre']}")
            continue
        cuerpo: Dict[str, Any] = {
            "name": espec["nombre"],
            "permissions": str(bits(espec["permisos"])),
            "colors": {"primary_color": espec["color"], "secondary_color": None, "tertiary_color": None},
            "hoist": espec["separado"],
            "mentionable": espec["mencionable"],
        }
        try:
            creado = s.api.post(f"/guilds/{s.id}/roles", cuerpo)
        except ErrorApi as e:
            if e.estado != 400:
                raise
            cuerpo["color"] = cuerpo.pop("colors")["primary_color"]  # forma anterior del mismo campo
            creado = s.api.post(f"/guilds/{s.id}/roles", cuerpo)
        s.recordar_rol(espec["clave"], creado)
        s.pendiente("roles", True)
        s.reg.hecho(f"rol {espec['nombre']}")


def ordenar_roles(s: Servidor, fase: int) -> None:
    """Deja los roles del diseño en su orden, solo si en esta construcción se creó alguno."""
    if not s.pendiente("roles"):
        return
    s.roles = s.api.get(f"/guilds/{s.id}/roles")  # al crear un rol, Discord recoloca los demás
    deseado = [r["id"] for r in (s.rol(e["clave"]) for e in diseno.roles(fase)) if r]
    propios = set(deseado)
    actual = [r["id"] for r in sorted(s.roles, key=lambda r: (-r["position"], int(r["id"]))) if r["id"] in propios]
    s.pendiente("roles", False)
    if actual == deseado:
        return
    posiciones = sorted((r["position"] for r in s.roles if r["id"] in propios), reverse=True)
    techo = posiciones[0]
    if techo - len(deseado) + 1 < 1:
        s.reg.aviso("No pude reordenar los roles; ordénalos a mano en Ajustes del servidor → Roles.")
        return
    cambios = [{"id": id, "position": techo - i} for i, id in enumerate(deseado)]
    try:
        s.roles = s.api.patch(f"/guilds/{s.id}/roles", cambios)
        s.reg.hecho("orden de los roles")
    except ErrorApi as e:
        s.reg.aviso(f"No pude reordenar los roles ({e.mensaje}); ordénalos a mano en Ajustes del servidor → Roles.")


def cuerpo_canal(s: Servidor, espec: Dict[str, Any]) -> Dict[str, Any]:
    tipo = espec["tipo_id"]
    cuerpo: Dict[str, Any] = {
        "name": espec["nombre"],
        "type": tipo,
        "permission_overwrites": s.sobrescrituras(s.permisos_de(espec)),
    }
    if tipo != CATEGORIA:
        cuerpo["parent_id"] = s.id_canal(espec["categoria"])
    if espec.get("tema"):
        cuerpo["topic"] = s.resolver(espec["tema"], estricto=False)
    if espec.get("archivar_hilos_min"):
        cuerpo["default_auto_archive_duration"] = espec["archivar_hilos_min"]
    if espec.get("limite"):
        cuerpo["user_limit"] = espec["limite"]
    if tipo == FORO:
        cuerpo["available_tags"] = [{"name": e["nombre"], "moderated": e["moderada"]} for e in espec.get("etiquetas", [])]
        cuerpo["default_sort_order"] = 1 if espec.get("orden") == "creacion" else 0
        cuerpo["default_forum_layout"] = 1
        if espec.get("reaccion"):
            cuerpo["default_reaction_emoji"] = {"emoji_id": None, "emoji_name": espec["reaccion"]}
    return cuerpo


def asegurar_canal(s: Servidor, clave: str) -> None:
    espec = s._espec_canales[clave]
    tipo = espec["tipo_id"]
    nombre = etiqueta(tipo, espec["nombre"])
    existente, por_estado = s.localizar(clave)
    if existente:
        s.estado["canales"][clave] = existente["id"]
        destino = s.id_canal(espec["categoria"]) if tipo != CATEGORIA else None
        if tipo != CATEGORIA and not por_estado and existente.get("parent_id") != destino:
            # Un canal con ese nombre que ya venía en el servidor (el #general inicial): se adopta.
            cambios: Dict[str, Any] = {"parent_id": destino, "permission_overwrites": s.sobrescrituras(s.permisos_de(espec))}
            if espec.get("tema") and not existente.get("topic"):
                cambios["topic"] = s.resolver(espec["tema"], estricto=False)
            s.recordar_canal(clave, s.api.patch(f"/channels/{existente['id']}", cambios))
            s.pendiente("canales", True)
            s.reg.hecho(f"{nombre} (ya existía; lo moví a su categoría)")
        else:
            s.reg.igual(nombre)
        return
    cuerpo = cuerpo_canal(s, espec)
    try:
        creado = s.api.post(f"/guilds/{s.id}/channels", cuerpo)
    except ErrorApi as e:
        if e.estado != 400 or "default_reaction_emoji" not in cuerpo:
            raise
        cuerpo.pop("default_reaction_emoji")  # adorno opcional: se reintenta sin él
        creado = s.api.post(f"/guilds/{s.id}/channels", cuerpo)
    s.recordar_canal(clave, creado)
    s.pendiente("canales", True)
    s.reg.hecho(nombre)


def paso_canales(s: Servidor, de_comunidad: bool) -> None:
    for categoria in diseno.CATEGORIAS:
        if not de_comunidad:
            asegurar_canal(s, categoria["clave"])
        for canal in categoria["canales"]:
            if (TIPOS[canal["tipo"]] in SOLO_EN_COMUNIDAD) == de_comunidad:
                asegurar_canal(s, canal["clave"])


def paso_comunidad(s: Servidor) -> None:
    if "COMMUNITY" in s.guild.get("features", []):
        s.reg.igual("comunidad activada")
        return
    # Requisitos de Discord: correo verificado, revisar los archivos de todos y avisar solo las menciones.
    requisitos = {
        "verification_level": max(int(s.guild.get("verification_level") or 0), 1),
        "explicit_content_filter": 2,
        "default_message_notifications": 1,
    }
    if any(s.guild.get(k) != v for k, v in requisitos.items()):
        s.guild = s.api.patch(f"/guilds/{s.id}", requisitos)
    s.guild = s.api.patch(
        f"/guilds/{s.id}",
        {
            "features": sorted(set(s.guild.get("features", [])) | {"COMMUNITY"}),
            "rules_channel_id": s.id_canal(diseno.AJUSTES["canal_reglas"]),
            "public_updates_channel_id": s.id_canal(diseno.AJUSTES["canal_avisos_de_discord"]),
        },
    )
    s.reg.hecho("comunidad activada (reglas en #reglas, avisos de Discord en #bitácora)")


def _orden_actual(canales: List[Dict[str, Any]]) -> List[str]:
    return [c["id"] for c in sorted(canales, key=lambda c: (c.get("position", 0), int(c["id"])))]


def paso_orden(s: Servidor, fase: int) -> None:
    """Ordena roles, categorías y canales como en el diseño y deja al final lo que no es del diseño."""
    ordenar_roles(s, fase)
    if not s.pendiente("canales"):
        s.reg.igual("orden de categorías y canales")
        return
    s.canales = s.api.get(f"/guilds/{s.id}/channels")
    cambios: List[Dict[str, Any]] = []
    categorias = [c for c in s.canales if c["type"] == CATEGORIA]
    propias = [s.id_canal(c["clave"]) for c in diseno.CATEGORIAS]
    ajenas = [id for id in _orden_actual(categorias) if id not in propias]
    if _orden_actual(categorias) != propias + ajenas:
        cambios += [{"id": id, "position": i} for i, id in enumerate(propias + ajenas)]
    for categoria in diseno.CATEGORIAS:
        padre = s.id_canal(categoria["clave"])
        for de_voz in (False, True):
            presentes = [c for c in s.canales if c.get("parent_id") == padre and c["type"] != CATEGORIA and (c["type"] in DE_VOZ) == de_voz]
            aqui = {c["id"] for c in presentes}
            deseado = [id for id in (s.id_canal(c["clave"]) for c in categoria["canales"] if (TIPOS[c["tipo"]] in DE_VOZ) == de_voz) if id in aqui]
            actual = [id for id in _orden_actual(presentes) if id in deseado]
            if actual != deseado:
                cambios += [{"id": id, "position": i} for i, id in enumerate(deseado)]
    if cambios:
        s.api.patch(f"/guilds/{s.id}/channels", cambios)
        s.canales = s.api.get(f"/guilds/{s.id}/channels")
        s.reg.hecho("orden de categorías y canales")
    else:
        s.reg.igual("orden de categorías y canales")
    s.pendiente("canales", False)


def paso_ajustes(s: Servidor) -> None:
    if s.ya("ajustes"):
        s.reg.igual("ajustes del servidor (ya aplicados una vez; no los toco)")
        return
    a = diseno.AJUSTES
    grupos: List[Tuple[str, Dict[str, Any]]] = [
        ("nivel de verificación", {"verification_level": max(int(s.guild.get("verification_level") or 0), a["verificacion"])}),
        ("idioma", {"preferred_locale": a["idioma"]}),
        ("descripción", {"description": a["descripcion"]}),
        # Bandera 4: sin los consejos de configuración de Discord en el canal de sistema.
        ("canal de sistema", {"system_channel_id": s.id_canal(a["canal_de_sistema"]), "system_channel_flags": 4}),
        ("alertas de seguridad", {"safety_alerts_channel_id": s.id_canal(a["canal_avisos_de_discord"])}),
    ]
    faltan = [(nombre, cuerpo) for nombre, cuerpo in grupos if any(s.guild.get(k) != v for k, v in cuerpo.items())]
    for nombre, _ in grupos:
        if nombre not in [n for n, _ in faltan]:
            s.reg.igual(nombre)
    completo = True
    if faltan:
        junto: Dict[str, Any] = {}
        for _, cuerpo in faltan:
            junto.update(cuerpo)
        try:
            s.guild = s.api.patch(f"/guilds/{s.id}", junto)
            for nombre, _ in faltan:
                s.reg.hecho(nombre)
        except ErrorApi as e:
            if e.estado != 400:
                raise
            # Discord rechazó el conjunto: se aplica uno por uno para saber cuál no acepta.
            for nombre, cuerpo in faltan:
                try:
                    s.guild = s.api.patch(f"/guilds/{s.id}", cuerpo)
                    s.reg.hecho(nombre)
                except ErrorApi as e2:
                    completo = False
                    s.reg.aviso(f"No pude ajustar {nombre}: {e2.texto()}")
    if completo:
        s.marcar("ajustes")


def paso_automod(s: Servidor) -> None:
    existentes = {r["trigger_type"] for r in s.api.get(f"/guilds/{s.id}/auto-moderation/rules")}
    acciones = [
        {"type": 1, "metadata": {"custom_message": diseno.AUTOMOD_MENSAJE}},
        {"type": 2, "metadata": {"channel_id": s.id_canal(diseno.AJUSTES["canal_avisos_de_discord"])}},
    ]
    exentos = [s.id_rol("admin"), s.id_rol("tutor")]
    for regla in diseno.AUTOMOD:
        if regla["tipo"] in existentes:
            s.reg.igual(f"regla {regla['nombre']}")
            continue
        try:
            s.api.post(
                f"/guilds/{s.id}/auto-moderation/rules",
                {
                    "name": regla["nombre"],
                    "event_type": 1,
                    "trigger_type": regla["tipo"],
                    "trigger_metadata": regla["metadatos"],
                    "actions": acciones,
                    "enabled": True,
                    "exempt_roles": exentos,
                },
            )
            s.reg.hecho(f"regla {regla['nombre']}")
        except ErrorApi as e:
            s.reg.aviso(f"No pude crear la regla «{regla['nombre']}»: {e.texto()}")


def enviar(s: Servidor, id_canal: str, texto: str, menciones: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if len(texto) > 2000:
        raise ErrorDeUso(f"Un mensaje pasa de 2000 caracteres ({len(texto)}): «{texto[:40]}…»")
    return s.api.post(
        f"/channels/{id_canal}/messages",
        {"content": texto, "allowed_mentions": menciones or SIN_MENCIONES, "flags": SILENCIOSO},
    )


def fijar(s: Servidor, id_canal: str, id_mensaje: str) -> None:
    """Fija un mensaje y borra el aviso «fijó un mensaje» que Discord deja debajo."""
    try:
        s.api.put(f"/channels/{id_canal}/messages/pins/{id_mensaje}")
        ultimos = s.api.get(f"/channels/{id_canal}/messages", limit=1)
        if ultimos and ultimos[0].get("type") == 6 and ultimos[0]["author"]["id"] == s.bot["id"]:
            s.api.delete(f"/channels/{id_canal}/messages/{ultimos[0]['id']}")
    except ErrorApi as e:
        s.reg.aviso(f"No pude fijar un mensaje: {e.mensaje}")


def _se_conversa(s: Servidor, espec: Dict[str, Any]) -> bool:
    """Falso en los canales de solo lectura, donde el texto fijo es lo único que hay."""
    negados = {p for regla in s.permisos_de(espec) if regla["rol"] == "@everyone" for p in regla.get("niega", [])}
    return "SEND_MESSAGES" not in negados


def paso_textos(s: Servidor) -> None:
    for clave, mensajes in diseno.MENSAJES.items():
        espec = s._espec_canales[clave]
        id_canal = s.id_canal(clave)
        # Si se perdió estado.json, se mira si el bot ya escribió en el canal.
        if s.ya(f"texto:{clave}") or any(
            m["author"]["id"] == s.bot["id"] for m in s.api.get(f"/channels/{id_canal}/messages", limit=50)
        ):
            s.marcar(f"texto:{clave}")
            s.reg.igual(f"texto de #{espec['nombre']}")
            continue
        primero = None
        for texto in mensajes:
            enviado = enviar(s, id_canal, s.resolver(texto))
            primero = primero or enviado
        # Donde se conversa, el texto se fija para que no se pierda entre los mensajes.
        if primero and _se_conversa(s, espec):
            fijar(s, id_canal, primero["id"])
        s.marcar(f"texto:{clave}")
        s.reg.hecho(f"texto de #{espec['nombre']}")


def _publicaciones(s: Servidor, id_foro: str) -> List[str]:
    activas = s.api.get(f"/guilds/{s.id}/threads/active").get("threads", [])
    archivadas = s.api.get(f"/channels/{id_foro}/threads/archived/public", limit=100).get("threads", [])
    return [t["name"].strip().lower() for t in activas + archivadas if t.get("parent_id") == id_foro]


def paso_catalogo(s: Servidor, fase: int) -> None:
    id_foro = s.id_canal("catalogo")
    foro = s.api.get(f"/channels/{id_foro}")
    etiquetas = {e["name"]: e["id"] for e in foro.get("available_tags", [])}
    existentes = _publicaciones(s, id_foro)

    def asegurar(titulo: str, nombres: List[str], texto: str) -> None:
        if titulo.strip().lower() in existentes:
            s.reg.igual(f"publicación {titulo}")
            return
        faltan = [n for n in nombres if n not in etiquetas]
        if faltan:
            s.reg.aviso(f"«{titulo}»: el foro no tiene las etiquetas {', '.join(faltan)}")
        s.api.post(
            f"/channels/{id_foro}/threads",
            {
                "name": titulo,
                "applied_tags": [etiquetas[n] for n in nombres if n in etiquetas][:5],
                "message": {"content": s.resolver(texto), "allowed_mentions": SIN_MENCIONES, "flags": SILENCIOSO},
            },
        )
        s.reg.hecho(f"publicación {titulo}")

    # El foro muestra primero lo más nuevo: se publica al revés para que el primer taller quede arriba.
    for t in reversed(catalogo.talleres_hasta(fase)):
        asegurar(t["nombre"], catalogo.etiquetas_taller(t), catalogo.texto_taller(t))
    asegurar(catalogo.TITULO_TUTORIAS, ["Tutoría"], catalogo.texto_tutorias())


def canales_publicos(s: Servidor) -> List[Dict[str, Any]]:
    """Canales del diseño que ve cualquier miembro."""
    return [c for c in diseno.canales() if not any(p["rol"] == "@everyone" and "VIEW_CHANNEL" in p.get("niega", []) for p in s.permisos_de(c))]


def paso_onboarding(s: Servidor) -> None:
    if not diseno.AJUSTES["onboarding"]:
        s.reg.nota("apagado en diseno.py (AJUSTES[\"onboarding\"]); ahí se explica por qué")
        return
    actual = s.api.get(f"/guilds/{s.id}/onboarding")
    if actual.get("enabled") and actual.get("prompts"):
        s.reg.igual("onboarding")
        return

    def preguntas(con_emojis: bool) -> List[Dict[str, Any]]:
        lista = []
        for i, p in enumerate(diseno.ONBOARDING):
            opciones = []
            for o in p["opciones"]:
                ids = [s.id_rol(o["rol"][0])]
                if p.get("rol_comun"):
                    ids.insert(0, s.id_rol(p["rol_comun"]))
                opcion: Dict[str, Any] = {"title": o["titulo"], "description": o.get("descripcion"), "role_ids": ids, "channel_ids": []}
                if con_emojis and o.get("emoji"):
                    opcion["emoji_name"] = o["emoji"]
                opciones.append(opcion)
            lista.append(
                {
                    "id": str(i),
                    "type": 0,
                    "title": p["titulo"],
                    "options": opciones,
                    "single_select": p["una_sola"],
                    "required": p["obligatoria"],
                    "in_onboarding": True,
                }
            )
        return lista

    publicos = canales_publicos(s)
    todos = [s.id_canal(c["clave"]) for c in publicos]
    solo_texto = [s.id_canal(c["clave"]) for c in publicos if TIPOS[c["tipo"]] not in DE_VOZ]
    # Los adornos van de más a menos: si Discord rechaza una variante, se intenta la siguiente.
    variantes = [(True, todos), (False, todos), (False, solo_texto)]
    ultimo: Optional[ErrorApi] = None
    for con_emojis, predeterminados in variantes:
        try:
            s.api.put(
                f"/guilds/{s.id}/onboarding",
                {"prompts": preguntas(con_emojis), "default_channel_ids": predeterminados, "enabled": True, "mode": 0},
            )
            s.reg.hecho("onboarding: carrera, semestre e intereses")
            s.reg.nota("Ojo: con el onboarding, cada estudiante debe activar «Mostrar todos los canales» para ver su aula.")
            return
        except ErrorApi as e:
            if e.estado != 400:
                raise
            ultimo = e
    s.reg.aviso(
        "No pude activar el onboarding; configúralo a mano en los ajustes del servidor. "
        + (ultimo.texto() if ultimo else "")
    )


def paso_dueno(s: Servidor) -> None:
    if s.ya("roles_del_dueno"):
        s.reg.igual("roles del dueño (ya asignados una vez)")
        return
    dueno = s.guild["owner_id"]
    miembro = s.api.get(f"/guilds/{s.id}/members/{dueno}")
    for clave in diseno.AJUSTES["roles_del_dueno"]:
        id_rol = s.id_rol(clave)
        if id_rol in miembro.get("roles", []):
            s.reg.igual(f"el dueño ya tiene el rol {s._espec_roles[clave]['nombre']}")
        else:
            s.api.put(f"/guilds/{s.id}/members/{dueno}/roles/{id_rol}")
            s.reg.hecho(f"rol {s._espec_roles[clave]['nombre']} para el dueño del servidor")
    s.marcar("roles_del_dueno")


def paso_invitacion(s: Servidor) -> None:
    if s.estado.get("invitacion"):
        s.reg.igual(f"invitación {s.estado['invitacion']}")
        return
    ruta = f"/channels/{s.id_canal(diseno.AJUSTES['canal_de_invitacion'])}/invites"
    miembro = diseno.AJUSTES["rol_de_miembro"]
    nombre = s._espec_roles[miembro]["nombre"]
    for previa in s.api.get(ruta):
        # Si se perdió estado.json, se reutiliza la invitación permanente que ya creó el bot.
        if (previa.get("inviter") or {}).get("id") == s.bot["id"] and not previa.get("max_age") and not previa.get("max_uses"):
            s.estado["invitacion"] = f"https://discord.gg/{previa['code']}"
            s.reg.igual(f"invitación {s.estado['invitacion']}")
            return
    try:
        # Invitación de comunidad: quien la acepta recibe el rol sin que nadie se lo asigne.
        invitacion = s.api.post(ruta, {"max_age": 0, "max_uses": 0, "unique": True, "role_ids": [s.id_rol(miembro)]})
        detalle = f"no caduca y entrega el rol {nombre}"
    except ErrorApi as e:
        if e.estado != 400:
            raise
        invitacion = s.api.post(ruta, {"max_age": 0, "max_uses": 0, "unique": False})
        detalle = "no caduca"
        s.reg.aviso(f"Discord no aceptó que la invitación entregue el rol {nombre} ({e.mensaje}). El rol se asigna igual al entrar a un aula.")
    s.estado["invitacion"] = f"https://discord.gg/{invitacion['code']}"
    s.reg.hecho(f"invitación ({detalle}): {s.estado['invitacion']}")


def sobrantes(s: Servidor) -> List[str]:
    """Canales y categorías que no son del diseño ni aulas."""
    encontrados = [s.canal(clave) for clave in s._espec_canales]
    propios = {c["id"] for c in encontrados if c}
    dinamicas = {c["id"] for c in (s.canal("cat:aulas-activas"), s.canal("cat:archivo")) if c}
    lista = []
    for c in s.canales:
        if c["id"] not in propios and c.get("parent_id") not in dinamicas:
            lista.append(etiqueta(c["type"], c.get("name") or ""))
    return lista


# ── Verificación ────────────────────────────────────────────────────────────


def verificar(s: Servidor, fase: int) -> List[str]:
    """Compara el servidor con el diseño y devuelve las diferencias."""
    s.cargar()
    dif: List[str] = []
    todos = s.rol("@everyone") or {}
    if int(todos.get("permissions", 0)) != bits(diseno.PERMISOS_BASE):
        sobran = set(nombres_de(int(todos.get("permissions", 0)))) - set(diseno.PERMISOS_BASE)
        faltan = set(diseno.PERMISOS_BASE) - set(nombres_de(int(todos.get("permissions", 0))))
        dif.append(f"@everyone: permisos distintos (de más: {sorted(sobran) or '—'}; de menos: {sorted(faltan) or '—'})")
    for espec in diseno.roles(fase):
        rol = s.rol(espec["clave"])
        if not rol:
            dif.append(f"falta el rol {espec['nombre']}")
        elif int(rol["permissions"]) != bits(espec["permisos"]):
            dif.append(f"rol {espec['nombre']}: permisos distintos a los del diseño")
    for clave, espec in s._espec_canales.items():
        canal = s.canal(clave)
        nombre = etiqueta(espec["tipo_id"], espec["nombre"])
        if not canal:
            dif.append(f"falta {nombre}")
            continue
        if espec["tipo_id"] != CATEGORIA:
            padre = s.canal(espec["categoria"])
            if padre and canal.get("parent_id") != padre["id"]:
                dif.append(f"{nombre}: no está en la categoría {s._espec_canales[espec['categoria']]['nombre']}")
        try:
            esperado = {o["id"]: (int(o["allow"]), int(o["deny"])) for o in s.sobrescrituras(s.permisos_de(espec))}
        except ErrorDeUso:
            continue
        real = {o["id"]: (int(o["allow"]), int(o["deny"])) for o in canal.get("permission_overwrites", [])}
        limpio = lambda d: {k: v for k, v in d.items() if v != (0, 0)}  # noqa: E731
        if limpio(esperado) != limpio(real):
            dif.append(f"{nombre}: permisos distintos a los del diseño")
    if "COMMUNITY" not in s.guild.get("features", []):
        dif.append("la comunidad no está activada")
    if int(s.guild.get("verification_level") or 0) < diseno.AJUSTES["verificacion"]:
        dif.append("el nivel de verificación es más bajo que el del diseño")
    try:
        if diseno.AJUSTES["onboarding"]:
            onboarding = s.api.get(f"/guilds/{s.id}/onboarding")
            if not onboarding.get("enabled"):
                dif.append("el onboarding no está activado")
            elif len(onboarding.get("prompts", [])) < len(diseno.ONBOARDING):
                dif.append("al onboarding le faltan preguntas")
        tipos = {r["trigger_type"] for r in s.api.get(f"/guilds/{s.id}/auto-moderation/rules")}
        for regla in diseno.AUTOMOD:
            if regla["tipo"] not in tipos:
                dif.append(f"falta la regla de AutoMod «{regla['nombre']}»")
        foro = s.canal("catalogo")
        if foro:
            publicadas = _publicaciones(s, foro["id"])
            for t in catalogo.talleres_hasta(fase):
                if t["nombre"].strip().lower() not in publicadas:
                    dif.append(f"falta en #catálogo la publicación «{t['nombre']}»")
    except ErrorApi as e:
        dif.append(f"no pude revisar onboarding, AutoMod o catálogo: {e.texto()}")
    return dif


def informar_verificacion(s: Servidor, fase: int) -> List[str]:
    s.reg.paso("Verificación")
    dif = verificar(s, fase)
    if dif:
        for d in dif:
            s.reg.linea(f"  ≠ {d}")
    else:
        s.reg.linea("  El servidor coincide con el diseño.")
    extra = sobrantes(s)
    if extra:
        s.reg.linea(f"  No son del diseño (bórralos a mano si no los quieres): {', '.join(extra)}")
    return dif


# ── Órdenes ─────────────────────────────────────────────────────────────────


def orden_construir(s: Servidor, fase: int) -> int:
    pasos: List[Tuple[str, Callable[[], None], bool]] = [
        ("Roles", lambda: paso_roles(s, fase), True),
        ("Categorías y canales", lambda: paso_canales(s, de_comunidad=False), True),
        ("Comunidad", lambda: paso_comunidad(s), True),
        ("Anuncios, foros y escenario", lambda: paso_canales(s, de_comunidad=True), True),
        ("Orden", lambda: paso_orden(s, fase), False),
        ("Ajustes del servidor", lambda: paso_ajustes(s), False),
        ("AutoMod", lambda: paso_automod(s), False),
        ("Textos", lambda: paso_textos(s), False),
        ("Catálogo", lambda: paso_catalogo(s, fase), False),
        ("Onboarding", lambda: paso_onboarding(s), False),
        ("Dueño", lambda: paso_dueno(s), False),
        ("Invitación", lambda: paso_invitacion(s), False),
    ]
    s.reg.linea(f"Servidor: {s.guild['name']} ({s.id}) · bot: {s.bot.get('username')} · fase {fase}")
    for titulo, paso, imprescindible in pasos:
        s.reg.paso(titulo)
        try:
            paso()
        except (ErrorApi, ErrorDeUso) as e:
            s.reg.error(f"{titulo}: {e}")
            if imprescindible:
                s.guardar_estado()
                s.reg.linea()
                s.reg.linea("Me detuve aquí. Corrige el error y vuelve a ejecutar: lo ya creado se conserva.")
                return 1
        finally:
            s.guardar_estado()
    dif = informar_verificacion(s, fase)
    resumen(s)
    return 1 if (dif or s.reg.errores) else 0


def resumen(s: Servidor) -> None:
    r = s.reg
    r.linea()
    r.linea(f"Resumen: {r.creados} creados · {r.iguales} ya estaban · {len(r.avisos)} avisos · {len(r.errores)} errores")
    if s.estado.get("invitacion"):
        r.linea(f"Invitación: {s.estado['invitacion']}")


def orden_verificar(s: Servidor, fase: int) -> int:
    return 1 if informar_verificacion(s, fase) else 0


def orden_publicar(s: Servidor, fase: int) -> int:
    s.reg.paso(f"Insignias hasta la fase {fase}")
    asegurar_roles(s, diseno.roles_de_insignias(fase))
    ordenar_roles(s, fase)
    s.guardar_estado()
    s.reg.paso(f"Catálogo hasta la fase {fase}")
    paso_catalogo(s, fase)
    s.estado["fase"] = max(fase, int(s.estado.get("fase") or 0))
    s.guardar_estado()
    resumen(s)
    return 0


def orden_plan(fase: int) -> int:
    """Imprime el diseño. No se conecta a Discord."""
    print(f"DISEÑO DEL SERVIDOR · fase {fase}\n")
    print("Roles (de arriba hacia abajo)")
    for r in diseno.roles(fase):
        marcas = [m for m, v in (("aparte en la lista", r["separado"]), ("mencionable", r["mencionable"])) if v]
        print(f"  {r['nombre']}" + (f"  ({', '.join(marcas)})" if marcas else ""))
    print("\nCategorías y canales")
    simbolo = {"texto": "#", "anuncios": "📣", "foro": "🗂", "voz": "🔊", "escenario": "🎤"}
    for cat in diseno.CATEGORIAS:
        privado = any(p["rol"] == "@everyone" and "VIEW_CHANNEL" in p.get("niega", []) for p in cat["permisos"])
        print(f"  {cat['nombre'].upper()}" + ("  (privada)" if privado else ""))
        for c in cat["canales"]:
            print(f"    {simbolo[c['tipo']]} {c['nombre']}")
        if not cat["canales"]:
            print("    (se llena con las aulas)")
    print("\nOnboarding")
    if diseno.AJUSTES["onboarding"]:
        for p in diseno.ONBOARDING:
            print(f"  {p['titulo']}  " + " · ".join(o["titulo"] for o in p["opciones"]))
    else:
        print("  apagado (ver AJUSTES en diseno.py)")
    print("\nAutoMod")
    for regla in diseno.AUTOMOD:
        print(f"  {regla['nombre']}")
    print("\nCatálogo que se publica")
    for t in catalogo.talleres_hasta(fase):
        print(f"  N{t['nivel']} ${catalogo.PRECIOS[t['nivel']]}  {t['nombre']}")
    print(f"  {catalogo.TITULO_TUTORIAS}")
    return 0


# ── Aulas ───────────────────────────────────────────────────────────────────


def zona() -> timezone:
    return timezone(timedelta(hours=diseno.AJUSTES["utc_offset_horas"]))


def leer_fecha(texto: str) -> datetime:
    for formato in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(texto.strip(), formato).replace(tzinfo=zona())
        except ValueError:
            continue
    raise ErrorDeUso(f"No entiendo la fecha «{texto}». Usa el formato \"2026-10-17 10:00\".")


def fecha_larga(d: datetime) -> str:
    return f"{DIAS[d.weekday()]} {d.day} de {MESES_LARGOS[d.month - 1]}, {d:%H:%M}"


def horas_texto(horas: float) -> str:
    entero = int(horas) if float(horas).is_integer() else horas
    return f"{entero} hora" if entero == 1 else f"{str(entero).replace('.', ',')} horas"


def resolver_miembro(s: Servidor, texto: str) -> Tuple[str, str]:
    """Acepta un id, una mención o un nombre de usuario. Devuelve (id, nombre visible)."""
    m = re.fullmatch(r"<@!?(\d+)>|(\d{15,21})", texto.strip())
    if m:
        id = m.group(1) or m.group(2)
        try:
            miembro = s.api.get(f"/guilds/{s.id}/members/{id}")
        except ErrorApi as e:
            if e.estado == 404:
                raise ErrorDeUso(f"El usuario {id} no está en el servidor.") from None
            raise
        return id, miembro["user"].get("username", id)
    nombre = texto.strip().lstrip("@")
    encontrados = s.api.get(f"/guilds/{s.id}/members/search", query=nombre, limit=10)

    def nombres(x: Dict[str, Any]) -> List[str]:
        return [str(v).lower() for v in (x["user"].get("username"), x["user"].get("global_name"), x.get("nick")) if v]

    exactos = [x for x in encontrados if nombre.lower() in nombres(x)]
    elegidos = exactos or encontrados
    if len(elegidos) == 1:
        return elegidos[0]["user"]["id"], elegidos[0]["user"].get("username", nombre)
    if not elegidos:
        raise ErrorDeUso(f"No encuentro a «{nombre}» en el servidor. Usa su nombre de usuario o su id.")
    lista = ", ".join(f"{x['user'].get('username')} ({x['user']['id']})" for x in elegidos)
    raise ErrorDeUso(f"«{nombre}» coincide con varias personas: {lista}. Usa el id.")


def aula_crear(s: Servidor, args: argparse.Namespace) -> int:
    taller = catalogo.buscar_taller(args.taller)
    titulo = taller["nombre"] if taller else args.taller.strip()
    corto = taller["insignia"] if taller else titulo[:60]
    inicio = leer_fecha(args.inicio)
    fin = inicio + timedelta(hours=args.horas)
    if not args.sin_evento and inicio <= datetime.now(timezone.utc):
        raise ErrorDeUso("La fecha de inicio ya pasó. Corrígela o usa --sin-evento.")
    etiqueta_fecha = f"{inicio.day} {MESES[inicio.month - 1]}"
    clave = f"{slug(args.clave or (taller['id'] if taller else corto))[:40]}-{inicio.day:02d}{MESES[inicio.month - 1]}"
    nombre_texto = f"aula-{clave}"
    nombre_visible = f"Aula · {corto} · {etiqueta_fecha}"

    categoria = s.id_canal("cat:aulas-activas")
    if any(c.get("parent_id") == categoria and normal(c.get("name") or "", TEXTO) == nombre_texto for c in s.canales):
        raise ErrorDeUso(f"Ya existe #{nombre_texto}. Si es otra aula del mismo día, agrégale --clave otro-nombre.")
    if len(args.miembros) > catalogo.PERSONAS_POR_AULA and not args.forzar:
        raise ErrorDeUso(f"Un aula es de máximo {catalogo.PERSONAS_POR_AULA} personas. Usa --forzar si de verdad son {len(args.miembros)}.")
    miembros = [resolver_miembro(s, m) for m in args.miembros]

    s.reg.paso(nombre_visible)
    rol = s.api.post(f"/guilds/{s.id}/roles", {"name": nombre_visible, "permissions": "0", "mentionable": True})
    s.reg.hecho(f"rol {nombre_visible}")
    permisos = s.sobrescrituras(diseno.SOLO_STAFF) + [
        {"id": rol["id"], "type": 0, "allow": str(bits(diseno.PERMISOS_AULA)), "deny": "0"}
    ]
    texto = s.api.post(
        f"/guilds/{s.id}/channels",
        {
            "name": nombre_texto,
            "type": TEXTO,
            "parent_id": categoria,
            "topic": f"{titulo} · {fecha_larga(inicio)} · {horas_texto(args.horas)}",
            "permission_overwrites": permisos,
        },
    )
    s.reg.hecho(f"canal #{nombre_texto}")
    voz = s.api.post(
        f"/guilds/{s.id}/channels",
        {
            "name": nombre_visible,
            "type": VOZ,
            "parent_id": categoria,
            "user_limit": diseno.AJUSTES["limite_voz_aula"],
            "permission_overwrites": permisos,
        },
    )
    s.reg.hecho(f"canal de voz {nombre_visible} (límite {diseno.AJUSTES['limite_voz_aula']})")
    id_miembro = s.id_rol(diseno.AJUSTES["rol_de_miembro"])
    for id, nombre in miembros:
        s.api.put(f"/guilds/{s.id}/members/{id}/roles/{rol['id']}")
        s.api.put(f"/guilds/{s.id}/members/{id}/roles/{id_miembro}")
        s.reg.hecho(f"{nombre} entra al aula")

    # Enlace para el resto del grupo: quien lo acepta entra al servidor y recibe el rol del aula.
    enlace = None
    cupos = max(catalogo.PERSONAS_POR_AULA - len(miembros), 0)
    if cupos and not args.sin_enlace:
        try:
            invitacion = s.api.post(
                f"/channels/{texto['id']}/invites",
                {"max_age": 0, "max_uses": cupos, "unique": True, "role_ids": [rol["id"], id_miembro]},
            )
            enlace = f"https://discord.gg/{invitacion['code']}"
            s.reg.hecho(f"enlace del aula para {cupos} {'persona' if cupos == 1 else 'personas'}")
        except ErrorApi as e:
            s.reg.aviso(
                f"No pude crear el enlace del aula ({e.mensaje}). Créalo a mano: clic derecho en #{nombre_texto} → "
                f"Invitar → Editar enlace → Roles → {nombre_visible}."
            )

    enlace_evento = "(sin evento)"
    if not args.sin_evento:
        try:
            evento = s.api.post(
                f"/guilds/{s.id}/scheduled-events",
                {
                    "name": titulo[:100],
                    "description": f"Aula de {horas_texto(args.horas)} con pantallas compartidas. Material y entregas en #{nombre_texto}.",
                    "scheduled_start_time": inicio.isoformat(),
                    "scheduled_end_time": fin.isoformat(),
                    "privacy_level": 2,
                    "entity_type": 2,
                    "channel_id": voz["id"],
                },
            )
            enlace_evento = f"https://discord.com/events/{s.id}/{evento['id']}"
            s.reg.hecho("evento con recordatorio")
        except ErrorApi as e:
            s.reg.aviso(f"No pude crear el evento: {e.texto()}")

    linea_kit = ""
    if taller or args.kit:
        linea_kit = diseno.LINEA_KIT.format(enlace=f": {args.kit}" if args.kit else "")
    marcadores = {
        "titulo": titulo,
        "rol": f"<@&{rol['id']}>",
        "inicio": str(int(inicio.timestamp())),
        "horas": horas_texto(args.horas),
        "voz": f"<#{voz['id']}>",
        "evento": enlace_evento,
        "kit": linea_kit,
    }
    contenido = diseno.MENSAJE_AULA
    for marcador, valor in marcadores.items():
        contenido = contenido.replace("{" + marcador + "}", valor)
    mensaje = s.api.post(
        f"/channels/{texto['id']}/messages",
        {"content": contenido, "allowed_mentions": {"roles": [rol["id"]]}},
    )
    fijar(s, texto["id"], mensaje["id"])
    s.reg.hecho("lista de preparación publicada y fijada")

    bitacora = s.canal("bitacora")
    if bitacora:
        aviso = f"🟢 Aula creada: **{nombre_visible}** · <t:{int(inicio.timestamp())}:f> · {len(miembros)} dentro · <#{texto['id']}>"
        if enlace:
            aviso += f"\nEnlace para el grupo ({cupos} usos): <{enlace}>"
        enviar(s, bitacora["id"], aviso)
    s.reg.linea()
    s.reg.linea("Aula lista.")
    if enlace:
        s.reg.linea(f"  Enlace para el grupo ({cupos} usos; pégalo en el hilo de la reserva): {enlace}")
    s.reg.linea(f"  Clave para archivarla: {clave}")
    return 0


def aulas_activas(s: Servidor) -> List[Dict[str, Any]]:
    """Aulas abiertas: su canal de texto, su rol, su canal de voz y la fecha de la clase."""
    categoria = s.id_canal("cat:aulas-activas")
    fijos = {s.id, s.id_rol("tutor")}
    dentro = [c for c in s.canales if c.get("parent_id") == categoria]
    aulas = []
    for c in sorted(dentro, key=lambda c: int(c["id"])):
        if c["type"] != TEXTO:
            continue
        roles = [o["id"] for o in c.get("permission_overwrites", []) if o["type"] == 0 and o["id"] not in fijos]
        id_rol = roles[0] if roles else None
        voz = next(
            (v for v in dentro if v["type"] == VOZ and id_rol and any(o["id"] == id_rol for o in v.get("permission_overwrites", []))),
            None,
        )
        nombre = c.get("name") or ""
        aulas.append({"clave": nombre[5:] if nombre.startswith("aula-") else nombre, "texto": c, "rol": id_rol, "voz": voz, "fecha": _fecha_del_nombre(c)})
    return aulas


def _fecha_del_nombre(canal: Dict[str, Any]) -> Optional[datetime]:
    """El nombre termina en día y mes (…-17oct); el año sale de cuándo se creó el canal."""
    m = re.search(r"-(\d{2})([a-z]{3})$", canal.get("name") or "")
    if not m or m.group(2) not in MESES:
        return None
    creado = creado_en(canal["id"]).astimezone(zona())
    try:
        fecha = datetime(creado.year, MESES.index(m.group(2)) + 1, int(m.group(1)), 23, 59, tzinfo=zona())
        if fecha < creado - timedelta(days=1):
            fecha = fecha.replace(year=creado.year + 1)
    except ValueError:
        return None
    return fecha


def aula_listar(s: Servidor, args: argparse.Namespace) -> int:
    aulas = aulas_activas(s)
    if not aulas:
        s.reg.linea("No hay aulas activas.")
        return 0
    ahora = datetime.now(timezone.utc)
    limite = diseno.AJUSTES["dias_para_archivar"]
    for a in aulas:
        if a["fecha"] is None:
            estado = "sin fecha en el nombre"
        else:
            dias = (ahora - a["fecha"]).days
            estado = f"clase en {-dias} días" if dias < 0 else ("clase hoy" if dias == 0 else f"clase hace {dias} días")
            if dias >= limite:
                estado += " · VENCIDA"
        s.reg.linea(f"  {a['clave']:<40} {estado}")
    return 0


def aula_archivar(s: Servidor, args: argparse.Namespace) -> int:
    aulas = aulas_activas(s)
    if args.vencidas:
        limite = datetime.now(timezone.utc) - timedelta(days=diseno.AJUSTES["dias_para_archivar"])
        elegidas = [a for a in aulas if a["fecha"] is not None and a["fecha"] <= limite]
        if not elegidas:
            s.reg.linea("No hay aulas vencidas.")
            return 0
    elif args.clave:
        buscada = args.clave.strip().lower()
        buscada = buscada[5:] if buscada.startswith("aula-") else buscada
        elegidas = [a for a in aulas if a["clave"] == buscada]
        if not elegidas:
            disponibles = ", ".join(a["clave"] for a in aulas) or "ninguna"
            raise ErrorDeUso(f"No hay un aula activa con la clave «{buscada}». Activas: {disponibles}.")
    else:
        raise ErrorDeUso("Indica la clave del aula o usa --vencidas.")

    archivo = s.id_canal("cat:archivo")
    bitacora = s.canal("bitacora")
    for a in elegidas:
        s.reg.paso(f"Archivar {a['clave']}")
        try:
            enlaces = s.api.get(f"/channels/{a['texto']['id']}/invites")
            for invitacion in enlaces:
                s.api.delete(f"/invites/{invitacion['code']}")
            if enlaces:
                s.reg.hecho("enlace del aula anulado")
        except ErrorApi as e:
            s.reg.aviso(f"No pude anular el enlace del aula: {e.mensaje}")
        if a["voz"]:
            s.api.delete(f"/channels/{a['voz']['id']}")
            s.reg.hecho("canal de voz borrado")
        s.api.patch(
            f"/channels/{a['texto']['id']}",
            {"parent_id": archivo, "permission_overwrites": s.sobrescrituras(diseno.SOLO_STAFF)},
        )
        s.reg.hecho("canal de texto movido a Archivo (solo lo ve el equipo)")
        if a["rol"]:
            s.api.delete(f"/guilds/{s.id}/roles/{a['rol']}")
            s.reg.hecho("rol temporal borrado")
        if bitacora:
            enviar(s, bitacora["id"], f"📦 Aula archivada: **{a['clave']}** · <#{a['texto']['id']}>")
    return 0


# ── Entrada ─────────────────────────────────────────────────────────────────


def argumentos() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="servidor.py", description="Construye y opera el servidor de Discord de los talleres.")
    sub = p.add_subparsers(dest="orden", required=True)
    fase = diseno.AJUSTES["fase"]

    x = sub.add_parser("plan", help="muestra el diseño sin tocar Discord")
    x.add_argument("--fase", type=int, default=fase)
    x = sub.add_parser("construir", help="crea en el servidor lo que falte")
    x.add_argument("--fase", type=int, default=fase, help="fase del catálogo que se publica")
    x = sub.add_parser("verificar", help="compara el servidor con el diseño")
    x.add_argument("--fase", type=int, default=None)
    x = sub.add_parser("publicar", help="abre los talleres de una fase: insignias y publicaciones")
    x.add_argument("--fase", type=int, required=True)

    aula = sub.add_parser("aula", help="crea, lista o archiva aulas")
    sub_aula = aula.add_subparsers(dest="accion", required=True)
    x = sub_aula.add_parser("crear", help="rol temporal, canales, evento y lista de preparación")
    x.add_argument("taller", help="id o nombre del taller (ver catalogo.py), o un título libre para una tutoría")
    x.add_argument("--inicio", required=True, help='fecha y hora local: "2026-10-17 10:00"')
    x.add_argument("--miembros", nargs="+", default=[], metavar="USUARIO", help="quienes ya están en el servidor: nombres de usuario, menciones o ids")
    x.add_argument("--horas", type=float, default=float(catalogo.HORAS_TALLER))
    x.add_argument("--kit", help="enlace al kit del taller")
    x.add_argument("--clave", help="nombre corto para los canales, si no quieres el del taller")
    x.add_argument("--sin-evento", action="store_true")
    x.add_argument("--sin-enlace", action="store_true", help="no crea el enlace de invitación del aula")
    x.add_argument("--forzar", action="store_true", help="permite más de 5 personas")
    sub_aula.add_parser("listar", help="aulas activas y cuáles ya vencieron")
    x = sub_aula.add_parser("archivar", help="borra voz y rol, y mueve el texto a Archivo")
    x.add_argument("clave", nargs="?")
    x.add_argument("--vencidas", action="store_true", help="todas las que pasaron los 7 días")
    return p


def main(argv: Optional[List[str]] = None, carpeta: Path = AQUI, api: Optional[Api] = None, silencio: bool = False) -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    args = argumentos().parse_args(argv)
    if args.orden == "plan":
        return orden_plan(args.fase)

    reg = Registro(carpeta / "registro.log", silencio=silencio)
    reg.inicio(" ".join(argv if argv is not None else sys.argv[1:]))
    try:
        if api is None:
            token, id_pedido = cargar_config(carpeta)
            api = Api(token)
        else:
            id_pedido = None
        api.avisar = reg.nota
        s = Servidor(api, reg, carpeta, id_pedido)
        fase = getattr(args, "fase", None) or s.estado.get("fase") or diseno.AJUSTES["fase"]
        if args.orden == "construir":
            s.estado["fase"] = max(fase, int(s.estado.get("fase") or 0))
            return orden_construir(s, s.estado["fase"])
        if args.orden == "verificar":
            return orden_verificar(s, fase)
        if args.orden == "publicar":
            return orden_publicar(s, args.fase)
        accion = {"crear": aula_crear, "listar": aula_listar, "archivar": aula_archivar}[args.accion]
        try:
            return accion(s, args)
        finally:
            s.guardar_estado()
    except ErrorDeUso as e:
        reg.linea()
        reg.linea(f"No pude continuar: {e}")
        return 2
    except ErrorApi as e:
        reg.linea()
        reg.linea(f"Discord rechazó una operación: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
