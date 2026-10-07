"""Un Discord de mentira para probar servidor.py sin tocar un servidor real.

Atiende en esta misma máquina la parte de la API que usa el script e imita las
reglas que más importan: la comunidad va antes que los foros, el onboarding
exige 7 canales predeterminados, los textos tienen límite y un bot no mueve
roles por encima del suyo.

Si se le pasa el openapi.json oficial (github.com/discord/discord-api-spec) y
está instalado `jsonschema`, además valida el cuerpo de cada petición contra
ese esquema.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

EPOCA_DISCORD = 1420070400000
TEXTO, VOZ, CATEGORIA, ANUNCIOS, ESCENARIO, FORO = 0, 2, 4, 5, 13, 15
DE_TEXTO = {TEXTO, ANUNCIOS, FORO}
VER, ENVIAR, ADMIN = 1 << 10, 1 << 11, 1 << 3
# Permisos con los que nace @everyone en un servidor nuevo: los de conversar más algunos
# que el diseño quita (mencionar a todos, TTS, hilos privados, eventos, apps externas).
_BITS_INICIALES = [0, 6, 9, 10, 11, 12, 14, 15, 16, 17, 18, 20, 21, 25, 26, 31, 32, 35, 36, 37, 38, 39, 42, 43, 44, 45, 46, 49, 50]
PERMISOS_INICIALES = sum(1 << b for b in _BITS_INICIALES)


class Rechazo(Exception):
    def __init__(self, estado: int, codigo: int, mensaje: str, campos: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(mensaje)
        self.estado = estado
        self.carga: Dict[str, Any] = {"code": codigo, "message": mensaje}
        if campos:
            self.carga["errors"] = campos


def invalido(campo: str, mensaje: str) -> Rechazo:
    return Rechazo(400, 50035, "Invalid Form Body", {campo: {"_errors": [{"code": "INVALID", "message": mensaje}]}})


class DiscordFalso:
    def __init__(self, modelo_roles: str = "desplaza", esquema: Optional[Dict[str, Any]] = None, con_plantilla: bool = True) -> None:
        self.modelo_roles = modelo_roles  # "desplaza": un rol nuevo empuja a los demás · "empata": todos quedan en 1
        self.esquema = esquema
        self.token = "token-de-prueba"
        self._contador = 0
        self.peticiones: List[Tuple[str, str, Any]] = []
        self.sin_validar: List[str] = []
        self.limitar_cada = 0  # si es N, una de cada N peticiones responde 429 la primera vez
        self._limitadas = 0
        self._atendidas = 0
        self.ahora_ms: Optional[int] = None  # permite fabricar ids «antiguos»
        self.bloquear_comunidad = False  # simula que Discord rechaza activar la comunidad
        self.rechazar_emojis = False  # simula que Discord rechaza los emojis del onboarding
        self.rechazar_roles_en_invitaciones = False  # simula un Discord sin invitaciones de comunidad
        self.rechazar_colors = False  # simula un Discord que solo entiende el campo `color` de los roles

        self.bot: Dict[str, Any] = {"id": self.id(), "username": "bot-prueba", "bot": True}
        self.dueno: Dict[str, Any] = {"id": self.id(), "username": "cayo", "global_name": "Cayo"}
        gid = self.id()
        self.guild: Dict[str, Any] = {
            "id": gid, "name": "Aula de prueba", "owner_id": self.dueno["id"], "features": [],
            "verification_level": 0, "explicit_content_filter": 0, "default_message_notifications": 0,
            "system_channel_id": None, "system_channel_flags": 0, "rules_channel_id": None,
            "public_updates_channel_id": None, "safety_alerts_channel_id": None,
            "preferred_locale": "en-US", "description": None,
        }
        self.roles: Dict[str, Dict[str, Any]] = {}
        self.roles[gid] = self._rol(gid, "@everyone", PERMISOS_INICIALES, 0)
        rol_bot = self._rol(self.id(), "bot-prueba", ADMIN, 1, managed=True)
        self.roles[rol_bot["id"]] = rol_bot
        self.rol_bot = rol_bot["id"]
        self.miembros: Dict[str, Dict[str, Any]] = {
            self.bot["id"]: {"user": self.bot, "roles": [rol_bot["id"]], "nick": None},
            self.dueno["id"]: {"user": self.dueno, "roles": [], "nick": None},
        }
        self.canales: Dict[str, Dict[str, Any]] = {}
        self.mensajes: Dict[str, List[Dict[str, Any]]] = {}
        self.hilos: Dict[str, Dict[str, Any]] = {}
        self.onboarding: Dict[str, Any] = {"guild_id": gid, "prompts": [], "default_channel_ids": [], "enabled": False, "mode": 0}
        self.reglas: List[Dict[str, Any]] = []
        self.eventos: List[Dict[str, Any]] = []
        self.invitaciones: List[Dict[str, Any]] = []
        if con_plantilla:
            # Lo que trae un servidor recién creado.
            texto = self._crear_canal({"name": "Text Channels", "type": CATEGORIA})
            general = self._crear_canal({"name": "general", "type": TEXTO, "parent_id": texto["id"]})
            voz = self._crear_canal({"name": "Voice Channels", "type": CATEGORIA})
            self._crear_canal({"name": "General", "type": VOZ, "parent_id": voz["id"]})
            self.guild["system_channel_id"] = general["id"]

    # -- utilidades --

    def id(self) -> str:
        self._contador += 1
        ms = self.ahora_ms if self.ahora_ms is not None else int(time.time() * 1000)
        return str(((ms - EPOCA_DISCORD) << 22) + self._contador)

    def agregar_miembro(self, username: str, global_name: Optional[str] = None, nick: Optional[str] = None) -> str:
        usuario: Dict[str, Any] = {"id": self.id(), "username": username, "global_name": global_name}
        self.miembros[usuario["id"]] = {"user": usuario, "roles": [], "nick": nick}
        return usuario["id"]

    @staticmethod
    def _rol(id: str, nombre: str, permisos: int, posicion: int, managed: bool = False) -> Dict[str, Any]:
        return {
            "id": id, "name": nombre, "permissions": str(permisos), "position": posicion, "color": 0,
            "colors": {"primary_color": 0, "secondary_color": None, "tertiary_color": None},
            "hoist": False, "managed": managed, "mentionable": False, "flags": 0,
        }

    def permisos_base(self, roles: List[str]) -> int:
        valor = int(self.roles[self.guild["id"]]["permissions"])
        for r in roles:
            if r in self.roles:
                valor |= int(self.roles[r]["permissions"])
        return valor

    def permisos_en(self, roles: List[str], id_canal: str) -> int:
        """Permisos efectivos en un canal, con el algoritmo de la documentación de Discord."""
        base = self.permisos_base(roles)
        if base & ADMIN:
            return (1 << 53) - 1
        gid = self.guild["id"]
        sobres = {o["id"]: o for o in self.canales[id_canal]["permission_overwrites"]}
        if gid in sobres:
            base = (base & ~int(sobres[gid]["deny"])) | int(sobres[gid]["allow"])
        permite = niega = 0
        for r in roles:
            if r in sobres:
                permite |= int(sobres[r]["allow"])
                niega |= int(sobres[r]["deny"])
        return (base & ~niega) | permite

    def orden_de_roles(self) -> List[str]:
        """Nombres de los roles de arriba hacia abajo (a igual posición, primero el id más antiguo)."""
        return [r["name"] for r in sorted(self.roles.values(), key=lambda r: (-r["position"], int(r["id"])))]

    def canal_por_nombre(self, nombre: str, tipo: Optional[int] = None) -> Dict[str, Any]:
        for c in self.canales.values():
            if c["name"] == nombre and (tipo is None or c["type"] == tipo):
                return c
        raise KeyError(nombre)

    def hijos(self, id_categoria: str) -> List[Dict[str, Any]]:
        """Canales de una categoría en el orden en que los muestra Discord: texto primero, luego voz."""
        dentro = [c for c in self.canales.values() if c.get("parent_id") == id_categoria]
        return sorted(dentro, key=lambda c: (c["type"] in (VOZ, ESCENARIO), c["position"], int(c["id"])))

    def categorias(self) -> List[Dict[str, Any]]:
        return sorted((c for c in self.canales.values() if c["type"] == CATEGORIA), key=lambda c: (c["position"], int(c["id"])))

    # -- canales --

    def _sobrescrituras(self, lista: Any) -> List[Dict[str, Any]]:
        salida = []
        for o in lista or []:
            if o["id"] not in self.roles and o["id"] not in self.miembros:
                raise invalido("permission_overwrites", f"rol o miembro desconocido: {o['id']}")
            salida.append({"id": o["id"], "type": int(o.get("type") or 0), "allow": str(int(o.get("allow") or 0)), "deny": str(int(o.get("deny") or 0))})
        return salida

    def _crear_canal(self, c: Dict[str, Any]) -> Dict[str, Any]:
        tipo = int(c.get("type") or 0)
        if tipo not in (TEXTO, VOZ, CATEGORIA, ANUNCIOS, ESCENARIO, FORO):
            raise invalido("type", "tipo de canal no admitido")
        if tipo in (ANUNCIOS, ESCENARIO, FORO) and "COMMUNITY" not in self.guild["features"]:
            raise Rechazo(400, 50024, "Cannot execute action on this channel type")
        nombre = str(c.get("name") or "")
        if not 1 <= len(nombre) <= 100:
            raise invalido("name", "Must be between 1 and 100 in length.")
        if tipo in DE_TEXTO:
            nombre = nombre.lower().replace(" ", "-")
        padre = c.get("parent_id")
        if padre is not None:
            if tipo == CATEGORIA or padre not in self.canales or self.canales[padre]["type"] != CATEGORIA:
                raise invalido("parent_id", "categoría desconocida")
            if len([x for x in self.canales.values() if x.get("parent_id") == padre]) >= 50:
                raise Rechazo(400, 50035, "Maximum number of channels in category reached (50)")
        tema = c.get("topic")
        if tema is not None and len(tema) > (4096 if tipo == FORO else 1024):
            raise invalido("topic", "Must be 1024 or fewer in length.")
        if len(self.canales) >= 500:
            raise Rechazo(400, 30013, "Maximum number of guild channels reached (500)")
        canal: Dict[str, Any] = {
            "id": self.id(), "type": tipo, "guild_id": self.guild["id"], "name": nombre,
            "position": c["position"] if c.get("position") is not None else len(self.canales),
            "parent_id": padre, "permission_overwrites": self._sobrescrituras(c.get("permission_overwrites")),
            "flags": 0,
        }
        if tipo in DE_TEXTO:
            canal.update(topic=tema, last_message_id=None, default_auto_archive_duration=c.get("default_auto_archive_duration"))
        if tipo in (VOZ, ESCENARIO):
            limite = int(c.get("user_limit") or 0)
            if tipo == VOZ and not 0 <= limite <= 99:
                raise invalido("user_limit", "Must be between 0 and 99.")
            canal.update(user_limit=limite, bitrate=64000)
        if tipo == FORO:
            canal.update(
                available_tags=self._etiquetas(c.get("available_tags")),
                default_sort_order=c.get("default_sort_order"), default_forum_layout=c.get("default_forum_layout") or 0,
                default_reaction_emoji=c.get("default_reaction_emoji"),
            )
        self.canales[canal["id"]] = canal
        self.mensajes[canal["id"]] = []
        return canal

    def _etiquetas(self, lista: Any) -> List[Dict[str, Any]]:
        lista = lista or []
        if len(lista) > 20:
            raise Rechazo(400, 30048, "Maximum number of tags in a forum channel has been reached")
        nombres = [e["name"] for e in lista]
        if len(set(nombres)) != len(nombres):
            raise Rechazo(400, 40061, "Tag names must be unique")
        for n in nombres:
            if not 1 <= len(n) <= 20:
                raise invalido("available_tags", "Must be between 1 and 20 in length.")
        return [{"id": self.id(), "name": e["name"], "moderated": bool(e.get("moderated")), "emoji_id": None, "emoji_name": e.get("emoji_name")} for e in lista]

    # -- rutas --

    def atender(self, metodo: str, ruta_completa: str, cuerpo: Any, cabeceras: Any) -> Tuple[int, Any]:
        partes = urllib.parse.urlsplit(ruta_completa)
        ruta = partes.path
        consulta = {k: v[0] for k, v in urllib.parse.parse_qs(partes.query).items()}
        self._atendidas += 1
        try:
            if cabeceras.get("Authorization") != f"Bot {self.token}":
                raise Rechazo(401, 0, "401: Unauthorized")
            if not str(cabeceras.get("User-Agent", "")).startswith("DiscordBot ("):
                raise Rechazo(403, 40333, "internal network error")
            if metodo != "GET" and cabeceras.get("Content-Length") is None:
                raise Rechazo(411, 0, "Length Required")
            if self.limitar_cada and self._atendidas % self.limitar_cada == 0:
                self._limitadas += 1
                return 429, {"message": "You are being rate limited.", "retry_after": 0.01, "global": False}
            self.peticiones.append((metodo, ruta, cuerpo))
            if self.esquema is not None and cuerpo is not None:
                self._validar(metodo, ruta, cuerpo)
            for patron, verbo, funcion in RUTAS:
                m = re.fullmatch(patron, ruta)
                if m and verbo == metodo:
                    resultado = funcion(self, cuerpo, consulta, *m.groups())
                    return (204, None) if resultado is None else (200, resultado)
            raise Rechazo(404, 0, f"404: ruta no simulada {metodo} {ruta}")
        except Rechazo as e:
            return e.estado, e.carga

    def _validar(self, metodo: str, ruta: str, cuerpo: Any) -> None:
        """Valida el cuerpo contra el esquema OpenAPI oficial."""
        import jsonschema  # type: ignore[import-not-found]

        assert self.esquema is not None
        for plantilla, operaciones in self.esquema["paths"].items():
            patron = re.sub(r"\{[^}]+\}", r"[^/]+", plantilla)
            if not re.fullmatch(patron, ruta) or metodo.lower() not in operaciones:
                continue
            contenido = operaciones[metodo.lower()].get("requestBody", {}).get("content", {}).get("application/json")
            if not contenido:
                self.sin_validar.append(f"{metodo} {plantilla}")
                return
            raiz = dict(self.esquema)
            raiz["x-en-prueba"] = contenido["schema"]
            raiz["$ref"] = "#/x-en-prueba"
            errores = sorted(jsonschema.Draft202012Validator(raiz).iter_errors(_numeros(cuerpo)), key=lambda e: list(e.path))
            if errores:
                e = errores[0]
                donde = ".".join(str(p) for p in e.absolute_path) or "cuerpo"
                raise invalido(donde, f"[OpenAPI] {e.message[:300]}")
            return
        self.sin_validar.append(f"{metodo} {ruta}")

    # usuarios y servidor

    def yo(self, c: Any, q: Dict[str, str]) -> Any:
        return self.bot

    def mis_servidores(self, c: Any, q: Dict[str, str]) -> Any:
        if self.bot["id"] not in self.miembros:
            return []
        return [{"id": self.guild["id"], "name": self.guild["name"], "owner": False, "permissions": "8", "features": self.guild["features"]}]

    def _g(self, gid: str) -> None:
        if gid != self.guild["id"]:
            raise Rechazo(404, 10004, "Unknown Guild")

    def ver_guild(self, c: Any, q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        return dict(self.guild)

    def cambiar_guild(self, c: Dict[str, Any], q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        nuevo = dict(self.guild)
        for campo in ("rules_channel_id", "public_updates_channel_id", "system_channel_id", "safety_alerts_channel_id"):
            if c.get(campo) is not None:
                canal = self.canales.get(c[campo])
                if not canal:
                    raise invalido(campo, "Unknown Channel")
                if canal["type"] != TEXTO:
                    raise Rechazo(400, 50086, "Community server channels must be text channels")
                nuevo[campo] = c[campo]
        for campo in ("verification_level", "explicit_content_filter", "default_message_notifications", "system_channel_flags"):
            if c.get(campo) is not None:
                nuevo[campo] = int(c[campo])
        if "preferred_locale" in c:
            if c["preferred_locale"] not in ("en-US", "es-ES", "es-419"):
                raise invalido("preferred_locale", "locale desconocido")
            nuevo["preferred_locale"] = c["preferred_locale"]
        if "description" in c:
            if c["description"] is not None and len(c["description"]) > 300:
                raise invalido("description", "Must be 300 or fewer in length.")
            if "COMMUNITY" not in (c.get("features") or nuevo["features"]):
                raise invalido("description", "solo los servidores de comunidad tienen descripción")
            nuevo["description"] = c["description"]
        if c.get("safety_alerts_channel_id") and "COMMUNITY" not in nuevo["features"]:
            raise invalido("safety_alerts_channel_id", "solo para comunidades")
        if "features" in c:
            pedidas = set(c["features"])
            if "COMMUNITY" in pedidas and "COMMUNITY" not in nuevo["features"]:
                if self.bloquear_comunidad:
                    raise Rechazo(403, 50013, "Missing Permissions")
                if not nuevo["rules_channel_id"] or not nuevo["public_updates_channel_id"]:
                    raise invalido("features", "COMMUNITY requiere rules_channel_id y public_updates_channel_id")
                if nuevo["verification_level"] < 1 or nuevo["explicit_content_filter"] != 2:
                    raise invalido("features", "COMMUNITY requiere verificación y filtro de contenido")
                if int(self.roles[gid]["permissions"]) & (ADMIN | 1 << 1 | 1 << 2 | 1 << 4 | 1 << 5 | 1 << 28):
                    raise invalido("features", "@everyone tiene permisos de moderación")
                nuevo["features"] = sorted(set(nuevo["features"]) | {"COMMUNITY", "NEWS"})
        self.guild = nuevo
        return dict(self.guild)

    # roles

    def ver_roles(self, c: Any, q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        return [dict(r) for r in self.roles.values()]

    def crear_rol(self, c: Dict[str, Any], q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        if len(self.roles) >= 250:
            raise Rechazo(400, 30005, "Maximum number of guild roles reached (250)")
        nombre = c.get("name") or "new role"
        if len(nombre) > 100:
            raise invalido("name", "Must be 100 or fewer in length.")
        if self.modelo_roles == "desplaza":
            for r in self.roles.values():
                if r["position"] >= 1:
                    r["position"] += 1
        permisos = c["permissions"] if c.get("permissions") is not None else self.roles[gid]["permissions"]
        rol = self._rol(self.id(), nombre, int(permisos), 1)
        if self.rechazar_colors and "colors" in c:
            raise invalido("colors", "Unknown field")
        colores = c.get("colors") or {}
        rol["color"] = int(colores.get("primary_color") or c.get("color") or 0)
        rol["colors"]["primary_color"] = rol["color"]
        if colores.get("secondary_color") is not None:
            raise invalido("colors", "los degradados requieren ENHANCED_ROLE_COLORS")
        rol["hoist"] = bool(c.get("hoist"))
        rol["mentionable"] = bool(c.get("mentionable"))
        self.roles[rol["id"]] = rol
        return dict(rol)

    def cambiar_rol(self, c: Dict[str, Any], q: Dict[str, str], gid: str, rid: str) -> Any:
        self._g(gid)
        if rid not in self.roles:
            raise Rechazo(404, 10011, "Unknown Role")
        rol = self.roles[rid]
        if "permissions" in c:
            rol["permissions"] = str(int(c["permissions"]))
        for campo, clave in (("name", "name"), ("hoist", "hoist"), ("mentionable", "mentionable")):
            if campo in c:
                rol[clave] = c[campo]
        return dict(rol)

    def mover_roles(self, c: List[Dict[str, Any]], q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        techo = self.roles[self.rol_bot]["position"]
        for cambio in c:
            if cambio["id"] not in self.roles:
                raise Rechazo(404, 10011, "Unknown Role")
            actual = self.roles[cambio["id"]]["position"]
            if cambio["position"] >= techo or actual >= techo or cambio["position"] < 1:
                raise Rechazo(403, 50013, "Missing Permissions")
        for cambio in c:
            self.roles[cambio["id"]]["position"] = cambio["position"]
        return [dict(r) for r in self.roles.values()]

    def borrar_rol(self, c: Any, q: Dict[str, str], gid: str, rid: str) -> Any:
        self._g(gid)
        if rid not in self.roles or self.roles[rid]["managed"] or rid == gid:
            raise Rechazo(404, 10011, "Unknown Role")
        del self.roles[rid]
        for m in self.miembros.values():
            m["roles"] = [r for r in m["roles"] if r != rid]
        for canal in self.canales.values():
            canal["permission_overwrites"] = [o for o in canal["permission_overwrites"] if o["id"] != rid]
        return None

    # miembros

    def ver_miembro(self, c: Any, q: Dict[str, str], gid: str, uid: str) -> Any:
        self._g(gid)
        if uid not in self.miembros:
            raise Rechazo(404, 10007, "Unknown Member")
        return json.loads(json.dumps(self.miembros[uid]))

    def buscar_miembros(self, c: Any, q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        texto = q.get("query", "").lower()
        limite = int(q.get("limit", 1))
        if not 1 <= len(texto) <= 100 or not 1 <= limite <= 1000:
            raise invalido("query", "consulta fuera de rango")
        encontrados = [
            json.loads(json.dumps(m)) for m in self.miembros.values()
            if any(str(v).lower().startswith(texto) for v in (m["user"]["username"], m.get("nick")) if v)
        ]
        return encontrados[:limite]

    def dar_rol(self, c: Any, q: Dict[str, str], gid: str, uid: str, rid: str) -> Any:
        self._g(gid)
        if uid not in self.miembros:
            raise Rechazo(404, 10007, "Unknown Member")
        if rid not in self.roles:
            raise Rechazo(404, 10011, "Unknown Role")
        if self.roles[rid]["position"] >= self.roles[self.rol_bot]["position"] and int(rid) < int(self.rol_bot):
            raise Rechazo(403, 50013, "Missing Permissions")
        if rid not in self.miembros[uid]["roles"]:
            self.miembros[uid]["roles"].append(rid)
        return None

    # canales

    def ver_canales(self, c: Any, q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        return [json.loads(json.dumps(x)) for x in self.canales.values()]

    def crear_canal(self, c: Dict[str, Any], q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        return json.loads(json.dumps(self._crear_canal(c)))

    def mover_canales(self, c: List[Dict[str, Any]], q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        if sum(1 for x in c if "parent_id" in x) > 1:
            raise Rechazo(400, 40009, "Only one channel can have a parent_id modified at a time")
        for x in c:
            if x["id"] not in self.canales:
                raise Rechazo(404, 10003, "Unknown Channel")
        for x in c:
            if x.get("position") is not None:
                self.canales[x["id"]]["position"] = x["position"]
        return None

    def _c(self, cid: str) -> Dict[str, Any]:
        if cid in self.canales:
            return self.canales[cid]
        if cid in self.hilos:
            return self.hilos[cid]
        raise Rechazo(404, 10003, "Unknown Channel")

    def ver_canal(self, c: Any, q: Dict[str, str], cid: str) -> Any:
        return json.loads(json.dumps(self._c(cid)))

    def cambiar_canal(self, c: Dict[str, Any], q: Dict[str, str], cid: str) -> Any:
        canal = self._c(cid)
        if "parent_id" in c:
            padre = c["parent_id"]
            if padre is not None and (padre not in self.canales or self.canales[padre]["type"] != CATEGORIA):
                raise invalido("parent_id", "categoría desconocida")
            if padre is not None and len([x for x in self.canales.values() if x.get("parent_id") == padre]) >= 50:
                raise Rechazo(400, 50035, "Maximum number of channels in category reached (50)")
            canal["parent_id"] = padre
        if "permission_overwrites" in c:
            canal["permission_overwrites"] = self._sobrescrituras(c["permission_overwrites"])
        if "topic" in c:
            if c["topic"] is not None and len(c["topic"]) > 1024:
                raise invalido("topic", "Must be 1024 or fewer in length.")
            canal["topic"] = c["topic"]
        if c.get("position") is not None:
            canal["position"] = c["position"]
        return json.loads(json.dumps(canal))

    def borrar_canal(self, c: Any, q: Dict[str, str], cid: str) -> Any:
        canal = self._c(cid)
        if cid in (self.guild["rules_channel_id"], self.guild["public_updates_channel_id"]):
            raise Rechazo(400, 50074, "Cannot delete a channel required for Community guilds")
        for hijo in self.canales.values():
            if hijo.get("parent_id") == cid:
                hijo["parent_id"] = None
        self.canales.pop(cid, None)
        self.eventos = [e for e in self.eventos if e.get("channel_id") != cid]
        self.invitaciones = [i for i in self.invitaciones if i["channel_id"] != cid]
        return json.loads(json.dumps(canal))

    def crear_invitacion(self, c: Dict[str, Any], q: Dict[str, str], cid: str) -> Any:
        self._c(cid)
        if not 0 <= int(c.get("max_age", 86400)) <= 604800 or not 0 <= int(c.get("max_uses", 0)) <= 100:
            raise invalido("max_age", "fuera de rango")
        roles = list(c.get("role_ids") or [])
        if roles and self.rechazar_roles_en_invitaciones:
            raise invalido("role_ids", "Unknown field")
        for rid in roles:
            if rid not in self.roles or self.roles[rid]["managed"] or rid == self.guild["id"]:
                raise Rechazo(400, 50028, "Invalid Role")
        for i in self.invitaciones:
            if not c.get("unique") and i["channel_id"] == cid and i["max_age"] == c.get("max_age", 86400) and i["role_ids"] == roles:
                return i
        self._invitaciones_creadas = getattr(self, "_invitaciones_creadas", 0) + 1
        invitacion = {
            "code": f"inv{self._invitaciones_creadas}", "channel_id": cid, "max_age": c.get("max_age", 86400),
            "max_uses": c.get("max_uses", 0), "uses": 0, "role_ids": roles, "inviter": dict(self.bot),
        }
        self.invitaciones.append(invitacion)
        return invitacion

    def ver_invitaciones(self, c: Any, q: Dict[str, str], cid: str) -> Any:
        self._c(cid)
        return [i for i in self.invitaciones if i["channel_id"] == cid]

    def borrar_invitacion(self, c: Any, q: Dict[str, str], codigo: str) -> Any:
        encontrada = next((i for i in self.invitaciones if i["code"] == codigo), None)
        if not encontrada:
            raise Rechazo(404, 10006, "Unknown Invite")
        self.invitaciones.remove(encontrada)
        return encontrada

    def aceptar_invitacion(self, enlace: str, id_usuario: str) -> None:
        """Lo que pasa cuando alguien abre un enlace: entra (si hace falta) y recibe los roles del enlace."""
        codigo = enlace.rsplit("/", 1)[-1]
        invitacion = next((i for i in self.invitaciones if i["code"] == codigo), None)
        if not invitacion or (invitacion["max_uses"] and invitacion["uses"] >= invitacion["max_uses"]):
            raise KeyError(f"invitación inválida o agotada: {codigo}")
        invitacion["uses"] += 1
        miembro = self.miembros[id_usuario]
        for rid in invitacion["role_ids"]:
            if rid in self.roles and rid not in miembro["roles"]:
                miembro["roles"].append(rid)

    # mensajes

    def ver_mensajes(self, c: Any, q: Dict[str, str], cid: str) -> Any:
        self._c(cid)
        limite = int(q.get("limit", 50))
        if not 1 <= limite <= 100:
            raise invalido("limit", "Must be between 1 and 100.")
        return list(reversed(self.mensajes.get(cid, [])))[:limite]

    def _mensaje(self, cid: str, c: Dict[str, Any], tipo: int = 0) -> Dict[str, Any]:
        contenido = c.get("content") or ""
        if tipo == 0 and not contenido and not c.get("poll") and not c.get("embeds"):
            raise Rechazo(400, 50006, "Cannot send an empty message")
        if len(contenido) > 2000:
            raise invalido("content", "Must be 2000 or fewer in length.")
        if re.search(r"\{[#@][a-z0-9:-]+\}|\{servidor\}", contenido):
            raise invalido("content", "quedó un marcador sin resolver")
        permitidas = c.get("allowed_mentions")
        if permitidas is None:
            permitidas = {"parse": ["users", "roles", "everyone"]}
        ids_roles = re.findall(r"<@&(\d+)>", contenido)
        avisados = [r for r in ids_roles if "roles" in (permitidas.get("parse") or []) or r in (permitidas.get("roles") or [])]
        for rid in permitidas.get("roles") or []:
            if rid not in ids_roles:
                raise invalido("allowed_mentions", "menciona un rol que no está en el contenido")
        for canal in re.findall(r"<#(\d+)>", contenido):
            if canal not in self.canales and canal not in self.hilos:
                raise invalido("content", f"menciona un canal que no existe: {canal}")
        for rid in ids_roles:
            if rid not in self.roles:
                raise invalido("content", f"menciona un rol que no existe: {rid}")
        mensaje = {
            "id": self.id(), "channel_id": cid, "author": dict(self.bot), "content": contenido, "type": tipo,
            "flags": int(c.get("flags") or 0), "mention_roles": avisados, "pinned": False,
        }
        self.mensajes.setdefault(cid, []).append(mensaje)
        return mensaje

    def crear_mensaje(self, c: Dict[str, Any], q: Dict[str, str], cid: str) -> Any:
        canal = self._c(cid)
        if canal["type"] == FORO:
            raise Rechazo(400, 40058, "Cannot send a message in a forum channel")
        if canal["type"] == CATEGORIA:
            raise Rechazo(400, 50008, "Cannot send messages in a non-text channel")
        return self._mensaje(cid, c)

    def borrar_mensaje(self, c: Any, q: Dict[str, str], cid: str, mid: str) -> Any:
        antes = len(self.mensajes.get(cid, []))
        self.mensajes[cid] = [m for m in self.mensajes.get(cid, []) if m["id"] != mid]
        if len(self.mensajes[cid]) == antes:
            raise Rechazo(404, 10008, "Unknown Message")
        return None

    def fijar_mensaje(self, c: Any, q: Dict[str, str], cid: str, mid: str) -> Any:
        mensaje = next((m for m in self.mensajes.get(cid, []) if m["id"] == mid), None)
        if not mensaje:
            raise Rechazo(404, 10008, "Unknown Message")
        mensaje["pinned"] = True
        self._mensaje(cid, {}, tipo=6)  # aviso «fijó un mensaje»
        return None

    # hilos y foros

    def crear_hilo(self, c: Dict[str, Any], q: Dict[str, str], cid: str) -> Any:
        canal = self._c(cid)
        if canal["type"] != FORO:
            raise Rechazo(400, 50024, "Cannot execute action on this channel type")
        if not 1 <= len(c.get("name") or "") <= 100:
            raise invalido("name", "Must be between 1 and 100 in length.")
        aplicadas = c.get("applied_tags") or []
        validas = {e["id"] for e in canal["available_tags"]}
        if len(aplicadas) > 5 or any(e not in validas for e in aplicadas):
            raise Rechazo(400, 10087, "Unknown Tag")
        if "message" not in c:
            raise invalido("message", "This field is required")
        if (c["message"].get("flags") or 0) & ~((1 << 2) | (1 << 12)):
            raise invalido("message.flags", "solo SUPPRESS_EMBEDS y SUPPRESS_NOTIFICATIONS")
        hilo = {
            "id": self.id(), "type": 11, "guild_id": self.guild["id"], "name": c["name"], "parent_id": cid,
            "applied_tags": aplicadas, "thread_metadata": {"archived": False, "auto_archive_duration": 4320, "locked": False},
        }
        self.hilos[hilo["id"]] = hilo
        hilo_con_mensaje = dict(hilo)
        hilo_con_mensaje["message"] = self._mensaje(hilo["id"], c["message"])
        return hilo_con_mensaje

    def hilos_activos(self, c: Any, q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        activos = [h for h in self.hilos.values() if not h["thread_metadata"]["archived"]]
        return {"threads": sorted(activos, key=lambda h: -int(h["id"])), "members": []}

    def hilos_archivados(self, c: Any, q: Dict[str, str], cid: str) -> Any:
        self._c(cid)
        if "limit" in q and not 2 <= int(q["limit"]) <= 100:
            raise invalido("limit", "Must be between 2 and 100.")
        archivados = [h for h in self.hilos.values() if h["parent_id"] == cid and h["thread_metadata"]["archived"]]
        return {"threads": archivados, "members": [], "has_more": False}

    # onboarding, automod y eventos

    def ver_onboarding(self, c: Any, q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        return json.loads(json.dumps(self.onboarding))

    def cambiar_onboarding(self, c: Dict[str, Any], q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        if "COMMUNITY" not in self.guild["features"]:
            raise Rechazo(403, 50001, "Missing Access")
        nuevo = dict(self.onboarding)
        if c.get("prompts") is not None:
            if len(c["prompts"]) > 15:
                raise invalido("prompts", "Must be 15 or fewer in length.")
            preguntas = []
            for p in c["prompts"]:
                if "id" not in p or not 1 <= len(p["title"]) <= 100 or not 1 <= len(p["options"]) <= 50:
                    raise invalido("prompts", "pregunta mal formada")
                opciones = []
                for o in p["options"]:
                    if not 1 <= len(o["title"]) <= 50 or len(o.get("description") or "") > 100:
                        raise invalido("prompts.options", "título o descripción demasiado largos")
                    if not (o.get("role_ids") or o.get("channel_ids")):
                        raise invalido("prompts.options", "cada opción necesita un rol o un canal")
                    if "emoji" in o:
                        raise invalido("prompts.options.emoji", "usa emoji_name en vez del objeto emoji")
                    if self.rechazar_emojis and o.get("emoji_name"):
                        raise Rechazo(400, 50151, "The specified emoji is invalid")
                    for rid in o.get("role_ids") or []:
                        if rid not in self.roles or self.roles[rid]["managed"]:
                            raise Rechazo(400, 50028, "Invalid Role")
                    opciones.append({
                        "id": self.id(), "title": o["title"], "description": o.get("description"),
                        "role_ids": list(o.get("role_ids") or []), "channel_ids": list(o.get("channel_ids") or []),
                        "emoji": {"id": None, "name": o.get("emoji_name"), "animated": False},
                    })
                preguntas.append({
                    "id": self.id(), "type": p.get("type") or 0, "title": p["title"], "options": opciones,
                    "single_select": bool(p.get("single_select")), "required": bool(p.get("required")), "in_onboarding": bool(p.get("in_onboarding")),
                })
            nuevo["prompts"] = preguntas
        if c.get("default_channel_ids") is not None:
            for cid in c["default_channel_ids"]:
                if cid not in self.canales:
                    raise Rechazo(400, 10003, "Unknown Channel")
            nuevo["default_channel_ids"] = list(c["default_channel_ids"])
        if c.get("enabled") is not None:
            nuevo["enabled"] = bool(c["enabled"])
        if nuevo["enabled"]:
            predeterminados = [self.canales[cid] for cid in nuevo["default_channel_ids"]]
            visibles = [x for x in predeterminados if self.permisos_en([], x["id"]) & VER]
            con_chat = [x for x in visibles if x["type"] in (TEXTO, ANUNCIOS) and self.permisos_en([], x["id"]) & ENVIAR]
            if len(visibles) < 7 or len(con_chat) < 5:
                raise Rechazo(400, 350000, "Cannot enable onboarding, requirements are not met")
        self.onboarding = nuevo
        return json.loads(json.dumps(self.onboarding))

    def ver_reglas(self, c: Any, q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        return list(self.reglas)

    def crear_regla(self, c: Dict[str, Any], q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        tipo = c["trigger_type"]
        maximo = {1: 6, 3: 1, 4: 1, 5: 1, 6: 1}.get(tipo)
        if maximo is None:
            raise invalido("trigger_type", "tipo desconocido")
        if len([r for r in self.reglas if r["trigger_type"] == tipo]) >= maximo:
            raise invalido("trigger_type", "Maximum number of rules of this type reached")
        if not c.get("actions"):
            raise invalido("actions", "This field is required")
        for a in c["actions"]:
            if a["type"] == 2 and a["metadata"]["channel_id"] not in self.canales:
                raise Rechazo(400, 10003, "Unknown Channel")
            if a["type"] == 1 and len((a.get("metadata") or {}).get("custom_message") or "") > 150:
                raise invalido("actions", "custom_message: Must be 150 or fewer in length.")
            if a["type"] == 3 and tipo not in (1, 5):
                raise invalido("actions", "TIMEOUT solo en reglas de palabras o de menciones")
        if tipo == 4 and not (c.get("trigger_metadata") or {}).get("presets"):
            raise invalido("trigger_metadata", "presets es obligatorio")
        for rid in c.get("exempt_roles") or []:
            if rid not in self.roles:
                raise Rechazo(400, 50028, "Invalid Role")
        regla = dict(c, id=self.id(), guild_id=gid, creator_id=self.bot["id"])
        self.reglas.append(regla)
        return regla

    def ver_eventos(self, c: Any, q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        return list(self.eventos)

    def crear_evento(self, c: Dict[str, Any], q: Dict[str, str], gid: str) -> Any:
        self._g(gid)
        inicio = datetime.fromisoformat(c["scheduled_start_time"])
        if inicio.tzinfo is None or inicio <= datetime.now(timezone.utc):
            raise invalido("scheduled_start_time", "Cannot schedule event in the past.")
        if c.get("scheduled_end_time") and datetime.fromisoformat(c["scheduled_end_time"]) <= inicio:
            raise invalido("scheduled_end_time", "End time must be after start time.")
        if c.get("privacy_level") != 2 or not 1 <= len(c.get("name") or "") <= 100 or len(c.get("description") or "") > 1000:
            raise invalido("name", "evento mal formado")
        if c.get("entity_type") == 2:
            canal = self.canales.get(c.get("channel_id") or "")
            if not canal or canal["type"] != VOZ:
                raise invalido("channel_id", "el evento de voz necesita un canal de voz")
        evento = dict(c, id=self.id(), guild_id=gid, status=1)
        self.eventos.append(evento)
        return evento


def _numeros(valor: Any, clave: str = "") -> Any:
    """La documentación pide los permisos como texto y el esquema OpenAPI como entero; Discord acepta ambos."""
    if isinstance(valor, dict):
        return {k: _numeros(v, k) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_numeros(v, clave) for v in valor]
    if clave in ("permissions", "allow", "deny") and isinstance(valor, str) and valor.isdigit():
        return int(valor)
    return valor


G, C, ID = r"/guilds/(\d+)", r"/channels/(\d+)", r"(\d+)"
RUTAS: List[Tuple[str, str, Callable[..., Any]]] = [
    (r"/users/@me", "GET", DiscordFalso.yo),
    (r"/users/@me/guilds", "GET", DiscordFalso.mis_servidores),
    (G, "GET", DiscordFalso.ver_guild),
    (G, "PATCH", DiscordFalso.cambiar_guild),
    (G + "/roles", "GET", DiscordFalso.ver_roles),
    (G + "/roles", "POST", DiscordFalso.crear_rol),
    (G + "/roles", "PATCH", DiscordFalso.mover_roles),
    (G + "/roles/" + ID, "PATCH", DiscordFalso.cambiar_rol),
    (G + "/roles/" + ID, "DELETE", DiscordFalso.borrar_rol),
    (G + "/members/search", "GET", DiscordFalso.buscar_miembros),
    (G + "/members/" + ID, "GET", DiscordFalso.ver_miembro),
    (G + "/members/" + ID + "/roles/" + ID, "PUT", DiscordFalso.dar_rol),
    (G + "/channels", "GET", DiscordFalso.ver_canales),
    (G + "/channels", "POST", DiscordFalso.crear_canal),
    (G + "/channels", "PATCH", DiscordFalso.mover_canales),
    (G + "/threads/active", "GET", DiscordFalso.hilos_activos),
    (G + "/onboarding", "GET", DiscordFalso.ver_onboarding),
    (G + "/onboarding", "PUT", DiscordFalso.cambiar_onboarding),
    (G + "/auto-moderation/rules", "GET", DiscordFalso.ver_reglas),
    (G + "/auto-moderation/rules", "POST", DiscordFalso.crear_regla),
    (G + "/scheduled-events", "GET", DiscordFalso.ver_eventos),
    (G + "/scheduled-events", "POST", DiscordFalso.crear_evento),
    (C, "GET", DiscordFalso.ver_canal),
    (C, "PATCH", DiscordFalso.cambiar_canal),
    (C, "DELETE", DiscordFalso.borrar_canal),
    (C + "/invites", "POST", DiscordFalso.crear_invitacion),
    (C + "/invites", "GET", DiscordFalso.ver_invitaciones),
    (r"/invites/([A-Za-z0-9-]+)", "DELETE", DiscordFalso.borrar_invitacion),
    (C + "/messages", "GET", DiscordFalso.ver_mensajes),
    (C + "/messages", "POST", DiscordFalso.crear_mensaje),
    (C + "/messages/pins/" + ID, "PUT", DiscordFalso.fijar_mensaje),
    (C + "/messages/" + ID, "DELETE", DiscordFalso.borrar_mensaje),
    (C + "/threads", "POST", DiscordFalso.crear_hilo),
    (C + "/threads/archived/public", "GET", DiscordFalso.hilos_archivados),
]


class _Manejador(BaseHTTPRequestHandler):
    falso: DiscordFalso
    candado = threading.Lock()

    def _atender(self) -> None:
        largo = self.headers.get("Content-Length")
        crudo = self.rfile.read(int(largo)) if largo and int(largo) else b""
        cuerpo = json.loads(crudo.decode("utf-8")) if crudo else None
        with self.candado:
            estado, carga = self.falso.atender(self.command, self.path, cuerpo, self.headers)
        datos = b"" if carga is None else json.dumps(carga, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        if estado == 429:
            self.send_header("Retry-After", "1")
        self.end_headers()
        self.wfile.write(datos)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _atender

    def log_message(self, *args: Any) -> None:
        pass


def levantar(falso: DiscordFalso) -> Tuple[ThreadingHTTPServer, str]:
    """Arranca el Discord falso en un puerto libre y devuelve (servidor, url)."""
    manejador = type("Manejador", (_Manejador,), {"falso": falso})
    http = ThreadingHTTPServer(("127.0.0.1", 0), manejador)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    return http, f"http://127.0.0.1:{http.server_address[1]}"
