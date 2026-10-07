"""Pruebas de servidor.py contra un Discord falso que corre en esta máquina.

    python -m unittest -v

Para validar además cada petición contra el esquema OpenAPI oficial de Discord:

    pip install jsonschema
    DISCORD_OPENAPI=ruta/al/openapi.json python -m unittest -v

(el archivo está en github.com/discord/discord-api-spec, carpeta specs).
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import catalogo
import diseno
import servidor
from discord_falso import ANUNCIOS, CATEGORIA, ESCENARIO, FORO, TEXTO, VOZ, DiscordFalso, levantar
from servidor import bits


def cargar_esquema() -> Optional[Dict[str, Any]]:
    ruta = os.environ.get("DISCORD_OPENAPI")
    if not ruta:
        return None
    if importlib.util.find_spec("jsonschema") is None:
        return None
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo)


ESQUEMA = cargar_esquema()


def puede(valor: int, permiso: str) -> bool:
    return bool(valor & bits([permiso]))


class Base(unittest.TestCase):
    modelo_roles = "desplaza"

    def setUp(self) -> None:
        self.falso = DiscordFalso(modelo_roles=self.modelo_roles, esquema=ESQUEMA)
        self.http, self.url = levantar(self.falso)
        self.tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.http.shutdown()
        self.http.server_close()
        self.tmp.cleanup()

    def ejecutar(self, *argv: str) -> Tuple[int, servidor.Api]:
        api = servidor.Api(self.falso.token, base=self.url, dormir=lambda segundos: None)
        codigo = servidor.main(list(argv), carpeta=self.carpeta, api=api, silencio=True)
        return codigo, api

    def construir(self) -> None:
        codigo, _ = self.ejecutar("construir")
        self.assertEqual(codigo, 0, self.registro())

    def registro(self) -> str:
        ruta = self.carpeta / "registro.log"
        return ruta.read_text(encoding="utf-8") if ruta.exists() else ""

    def estado(self) -> Dict[str, Any]:
        return json.loads((self.carpeta / "estado.json").read_text(encoding="utf-8"))

    def rol(self, nombre: str) -> Dict[str, Any]:
        return next(r for r in self.falso.roles.values() if r["name"] == nombre)

    def permisos(self, roles: List[str], canal: str, tipo: Optional[int] = None) -> int:
        ids = [self.rol(nombre)["id"] for nombre in roles]
        return self.falso.permisos_en(ids, self.falso.canal_por_nombre(canal, tipo)["id"])

    def nombres_hijos(self, categoria: str) -> List[str]:
        return [c["name"] for c in self.falso.hijos(self.falso.canal_por_nombre(categoria, CATEGORIA)["id"])]


class Construir(Base):
    def test_estructura(self) -> None:
        general_inicial = self.falso.canal_por_nombre("general", TEXTO)["id"]
        self.construir()
        f = self.falso

        self.assertEqual(
            [c["name"] for c in f.categorias()],
            ["Inicio", "Aulas", "Comunidad", "Ayuda", "Aulas activas", "Staff", "Archivo", "Text Channels", "Voice Channels"],
        )
        self.assertEqual(self.nombres_hijos("Inicio"), ["bienvenida", "reglas", "anuncios"])
        self.assertEqual(self.nombres_hijos("Aulas"), ["catálogo", "calendario", "reservar", "busco-grupo", "Clase abierta"])
        self.assertEqual(self.nombres_hijos("Comunidad"), ["general", "showcase", "recursos", "prácticas-y-empleos", "Sala de estudio"])
        self.assertEqual(self.nombres_hijos("Ayuda"), ["dudas", "setup"])
        self.assertEqual(self.nombres_hijos("Aulas activas"), [])
        self.assertEqual(self.nombres_hijos("Staff"), ["pagos-por-validar", "bitácora", "tutores"])
        self.assertEqual(self.nombres_hijos("Archivo"), [])

        tipos = {"anuncios": ANUNCIOS, "catálogo": FORO, "dudas": FORO, "Clase abierta": ESCENARIO, "Sala de estudio": VOZ, "reservar": TEXTO}
        for nombre, tipo in tipos.items():
            self.assertEqual(f.canal_por_nombre(nombre)["type"], tipo, nombre)

        # El #general que traía el servidor se adopta en vez de duplicarse.
        self.assertEqual(f.canal_por_nombre("general", TEXTO)["id"], general_inicial)
        self.assertEqual(len([c for c in f.canales.values() if c["name"] == "general"]), 1)
        self.assertIn("categoría «Text Channels»", self.registro())

        self.assertEqual(f.canal_por_nombre("reservar")["default_auto_archive_duration"], 10080)
        catalogo_foro = f.canal_por_nombre("catálogo")
        self.assertEqual(len(catalogo_foro["available_tags"]), 15)
        self.assertEqual(catalogo_foro["default_sort_order"], 1)
        self.assertEqual(catalogo_foro["default_reaction_emoji"], {"emoji_id": None, "emoji_name": "🙋"})
        self.assertIn(f"<#{f.canal_por_nombre('reservar')['id']}>", catalogo_foro["topic"])

    def test_ajustes_del_servidor(self) -> None:
        self.construir()
        g = self.falso.guild
        self.assertIn("COMMUNITY", g["features"])
        self.assertEqual(g["rules_channel_id"], self.falso.canal_por_nombre("reglas")["id"])
        self.assertEqual(g["public_updates_channel_id"], self.falso.canal_por_nombre("bitácora")["id"])
        self.assertEqual(g["safety_alerts_channel_id"], self.falso.canal_por_nombre("bitácora")["id"])
        self.assertEqual(g["system_channel_id"], self.falso.canal_por_nombre("general", TEXTO)["id"])
        self.assertEqual((g["verification_level"], g["explicit_content_filter"], g["default_message_notifications"]), (2, 2, 1))
        self.assertEqual(g["preferred_locale"], "es-419")
        self.assertEqual(g["description"], diseno.AJUSTES["descripcion"])
        self.assertEqual(len(self.falso.reglas), 3)
        self.assertEqual({r["trigger_type"] for r in self.falso.reglas}, {3, 4, 5})
        exentos = {self.rol("Admin")["id"], self.rol("Tutor")["id"]}
        for regla in self.falso.reglas:
            self.assertEqual(set(regla["exempt_roles"]), exentos)
            self.assertTrue(regla["enabled"])

    def test_roles(self) -> None:
        self.construir()
        f = self.falso
        esperado = ["bot-prueba"] + [r["nombre"] for r in diseno.roles(1)] + ["@everyone"]
        self.assertEqual(f.orden_de_roles(), esperado)
        self.assertEqual(int(f.roles[f.guild["id"]]["permissions"]), bits(diseno.PERMISOS_BASE))
        self.assertEqual(int(self.rol("Admin")["permissions"]), bits(["ADMINISTRATOR"]))
        self.assertEqual(int(self.rol("Tutor")["permissions"]), bits(diseno.PERMISOS_TUTOR))
        for nombre in ("Organizador", "Estudiante", "Insignia · GitHub"):
            self.assertEqual(int(self.rol(nombre)["permissions"]), 0, nombre)
        self.assertFalse([r for r in f.roles.values() if r["name"].startswith(("Carrera", "Semestre", "Interés"))])
        self.assertTrue(self.rol("Tutor")["hoist"])
        self.assertEqual(self.rol("Tutor")["colors"]["primary_color"], 0x3498DB)
        self.assertTrue(self.rol("Admin")["mentionable"])
        self.assertFalse(self.rol("Tutor")["mentionable"])
        # El dueño aparece como tutor y recibe las menciones de las reservas.
        dueno = f.miembros[f.dueno["id"]]
        self.assertEqual(set(dueno["roles"]), {self.rol("Admin")["id"], self.rol("Tutor")["id"]})

    def test_permisos_de_un_miembro(self) -> None:
        self.construir()
        nadie: List[str] = []
        for canal in ("bienvenida", "reglas", "anuncios", "calendario"):
            p = self.permisos(nadie, canal)
            self.assertTrue(puede(p, "VIEW_CHANNEL"), canal)
            self.assertFalse(puede(p, "SEND_MESSAGES"), canal)
            self.assertFalse(puede(p, "CREATE_PUBLIC_THREADS"), canal)
            self.assertFalse(puede(p, "SEND_MESSAGES_IN_THREADS"), canal)
            self.assertTrue(puede(p, "ADD_REACTIONS"), canal)
        for canal in ("general", "showcase", "recursos", "prácticas-y-empleos", "busco-grupo", "setup", "dudas"):
            p = self.permisos(nadie, canal, None if canal != "general" else TEXTO)
            self.assertTrue(puede(p, "SEND_MESSAGES"), canal)
            self.assertTrue(puede(p, "ATTACH_FILES"), canal)
            self.assertFalse(puede(p, "MENTION_EVERYONE"), canal)
            self.assertFalse(puede(p, "CREATE_PRIVATE_THREADS"), canal)
            self.assertFalse(puede(p, "MANAGE_MESSAGES"), canal)

        # Reservas: nadie escribe en el canal; cada quien abre su hilo privado.
        p = self.permisos(nadie, "reservar")
        self.assertFalse(puede(p, "SEND_MESSAGES"))
        self.assertFalse(puede(p, "CREATE_PUBLIC_THREADS"))
        self.assertTrue(puede(p, "CREATE_PRIVATE_THREADS"))
        self.assertTrue(puede(p, "SEND_MESSAGES_IN_THREADS"))
        self.assertTrue(puede(p, "ATTACH_FILES"))
        self.assertFalse(puede(p, "MANAGE_THREADS"))

        # Catálogo: solo el equipo publica talleres; cualquiera comenta.
        p = self.permisos(nadie, "catálogo")
        self.assertFalse(puede(p, "SEND_MESSAGES"))
        self.assertTrue(puede(p, "SEND_MESSAGES_IN_THREADS"))

        for canal in ("pagos-por-validar", "bitácora", "tutores"):
            self.assertFalse(puede(self.permisos(nadie, canal), "VIEW_CHANNEL"), canal)
        for categoria in ("Aulas activas", "Staff", "Archivo"):
            self.assertFalse(puede(self.permisos(nadie, categoria, CATEGORIA), "VIEW_CHANNEL"), categoria)

        p = self.permisos(nadie, "Sala de estudio")
        for permiso in ("CONNECT", "SPEAK", "STREAM"):
            self.assertTrue(puede(p, permiso), permiso)
        p = self.permisos(nadie, "Clase abierta")
        self.assertTrue(puede(p, "CONNECT"))
        self.assertTrue(puede(p, "REQUEST_TO_SPEAK"))
        self.assertFalse(puede(p, "MUTE_MEMBERS"))

        # Estudiante, Organizador y las insignias no cambian ningún permiso.
        decorados = ["Estudiante", "Insignia · GitHub", "Organizador"]
        for canal in ("reglas", "reservar", "tutores", "catálogo"):
            self.assertEqual(self.permisos(decorados, canal), self.permisos(nadie, canal), canal)

    def test_permisos_del_tutor(self) -> None:
        self.construir()
        tutor = ["Tutor"]
        for canal in ("anuncios", "calendario", "catálogo"):
            self.assertTrue(puede(self.permisos(tutor, canal), "SEND_MESSAGES"), canal)
        for canal in ("bienvenida", "reglas"):
            self.assertFalse(puede(self.permisos(tutor, canal), "SEND_MESSAGES"), canal)
        self.assertTrue(puede(self.permisos(tutor, "tutores"), "VIEW_CHANNEL"))
        self.assertTrue(puede(self.permisos(tutor, "bitácora"), "VIEW_CHANNEL"))
        self.assertTrue(puede(self.permisos(tutor, "Aulas activas", CATEGORIA), "VIEW_CHANNEL"))
        # Los comprobantes solo los ve el Admin.
        self.assertFalse(puede(self.permisos(tutor, "pagos-por-validar"), "VIEW_CHANNEL"))
        self.assertFalse(puede(self.permisos(tutor, "reservar"), "MANAGE_THREADS"))
        self.assertTrue(puede(self.permisos(tutor, "general", TEXTO), "MANAGE_THREADS"))
        self.assertTrue(puede(self.permisos(tutor, "general", TEXTO), "MANAGE_MESSAGES"))
        escenario = self.permisos(tutor, "Clase abierta")
        for permiso in ("MANAGE_CHANNELS", "MUTE_MEMBERS", "MOVE_MEMBERS"):
            self.assertTrue(puede(escenario, permiso), permiso)
        self.assertFalse(puede(self.permisos(tutor, "general", TEXTO), "MANAGE_CHANNELS"))
        for permiso in ("MANAGE_ROLES", "MANAGE_GUILD", "KICK_MEMBERS", "BAN_MEMBERS", "ADMINISTRATOR"):
            self.assertFalse(puede(self.permisos(tutor, "general", TEXTO), permiso), permiso)
        self.assertTrue(puede(self.permisos(["Admin"], "pagos-por-validar"), "VIEW_CHANNEL"))

    def test_textos(self) -> None:
        self.construir()
        f = self.falso
        for clave, mensajes in diseno.MENSAJES.items():
            nombre = next(c["nombre"] for c in diseno.canales() if c["clave"] == clave)
            publicados = [m for m in f.mensajes[f.canal_por_nombre(nombre)["id"]] if m["type"] == 0]
            self.assertEqual(len(publicados), len(mensajes), nombre)
            for m in publicados:
                self.assertEqual(m["mention_roles"], [], nombre)  # ningún texto fijo notifica a nadie
                self.assertTrue(m["flags"] & (1 << 12), nombre)
        bienvenida = f.mensajes[f.canal_por_nombre("bienvenida")["id"]][0]["content"]
        self.assertIn("Te damos la bienvenida a Aula de prueba", bienvenida)
        self.assertIn(f"<#{f.canal_por_nombre('catálogo')['id']}>", bienvenida)
        reservar = f.mensajes[f.canal_por_nombre("reservar")["id"]][0]["content"]
        self.assertIn(f"<@&{self.rol('Admin')['id']}>", reservar)
        # En los canales de conversación el texto queda fijado y sin el aviso de «fijó un mensaje».
        for nombre, fijado in (("busco-grupo", True), ("setup", True), ("tutores", True), ("reglas", False), ("reservar", False)):
            mensajes = f.mensajes[f.canal_por_nombre(nombre)["id"]]
            self.assertEqual(mensajes[0]["pinned"], fijado, nombre)
            self.assertFalse([m for m in mensajes if m["type"] == 6], nombre)
        self.assertEqual(f.mensajes[f.canal_por_nombre("general", TEXTO)["id"]], [])

    def test_catalogo(self) -> None:
        self.construir()
        f = self.falso
        foro = f.canal_por_nombre("catálogo")
        etiquetas = {e["id"]: e["name"] for e in foro["available_tags"]}
        hilos = sorted((h for h in f.hilos.values() if h["parent_id"] == foro["id"]), key=lambda h: int(h["id"]))
        # Se publica al revés: lo más nuevo (tutorías, luego el primer taller) queda arriba en el foro.
        self.assertEqual(
            [h["name"] for h in reversed(hilos)],
            [catalogo.TITULO_TUTORIAS] + [t["nombre"] for t in catalogo.talleres_hasta(1)],
        )
        poo = next(h for h in hilos if h["name"] == "POO con Python")
        self.assertEqual([etiquetas[e] for e in poo["applied_tags"]], ["Taller", "N2 · $20", "Python"])
        texto = f.mensajes[poo["id"]][0]["content"]
        self.assertIn("**Nivel N2 · $20 por aula**", texto)
        self.assertIn("1 persona $20 · 2 personas $10 · 3 personas $6,67 · 4 personas $5 · 5 personas $4", texto)
        self.assertIn(f"<@&{self.rol('Insignia · POO con Python')['id']}>", texto)
        tutorias = next(h for h in hilos if h["name"] == catalogo.TITULO_TUTORIAS)
        self.assertEqual([etiquetas[e] for e in tutorias["applied_tags"]], ["Tutoría"])
        self.assertIn("**Maratón antes del examen** · 3 h · $25 por aula", f.mensajes[tutorias["id"]][0]["content"])

    def test_onboarding_apagado_por_defecto(self) -> None:
        self.construir()
        self.assertFalse(self.falso.onboarding["enabled"])
        self.assertFalse([p for p in self.falso.peticiones if p[1].endswith("/onboarding")])
        self.assertIn("apagado en diseno.py", self.registro())

    def test_registro_y_estado(self) -> None:
        self.construir()
        registro = self.registro()
        self.assertIn("El servidor coincide con el diseño.", registro)
        self.assertIn("categoría «Text Channels»", registro)
        self.assertIn("0 errores", registro)
        self.assertNotIn(self.falso.token, registro)
        estado = self.estado()
        self.assertEqual(estado["servidor"], self.falso.guild["id"])
        # La invitación del servidor no caduca y entrega el rol Estudiante a quien la acepta.
        self.assertEqual(estado["invitacion"], "https://discord.gg/inv1")
        invitacion = self.falso.invitaciones[0]
        self.assertEqual((invitacion["max_age"], invitacion["max_uses"]), (0, 0))
        self.assertEqual(invitacion["channel_id"], self.falso.canal_por_nombre("bienvenida")["id"])
        nueva = self.falso.agregar_miembro("recien.llegada")
        self.falso.aceptar_invitacion(estado["invitacion"], nueva)
        self.assertEqual(self.falso.miembros[nueva]["roles"], [self.rol("Estudiante")["id"]])
        self.assertEqual(estado["canales"]["catalogo"], self.falso.canal_por_nombre("catálogo")["id"])
        self.assertNotIn(self.falso.token, json.dumps(estado))
        if ESQUEMA is not None:
            self.assertEqual(self.falso.sin_validar, [])

    def test_la_segunda_vez_no_cambia_nada(self) -> None:
        self.construir()
        canales, roles = len(self.falso.canales), len(self.falso.roles)
        mensajes = sum(len(m) for m in self.falso.mensajes.values())
        codigo, api = self.ejecutar("construir")
        self.assertEqual(codigo, 0, self.registro())
        self.assertEqual(api.escrituras, 0)
        self.assertEqual((len(self.falso.canales), len(self.falso.roles)), (canales, roles))
        self.assertEqual(sum(len(m) for m in self.falso.mensajes.values()), mensajes)

    def test_sin_estado_no_duplica(self) -> None:
        self.construir()
        canales, roles, hilos = len(self.falso.canales), len(self.falso.roles), len(self.falso.hilos)
        (self.carpeta / "estado.json").unlink()
        codigo, api = self.ejecutar("construir")
        self.assertEqual(codigo, 0, self.registro())
        self.assertEqual((len(self.falso.canales), len(self.falso.roles), len(self.falso.hilos)), (canales, roles, hilos))
        self.assertEqual(api.escrituras, 0)
        self.assertEqual(len(self.falso.invitaciones), 1)
        self.assertEqual(self.estado()["invitacion"], "https://discord.gg/inv1")

    def test_respeta_cambios_hechos_a_mano(self) -> None:
        self.construir()
        f = self.falso
        # El dueño renombra un canal, lo mueve y cambia los permisos de @everyone.
        recursos = f.canal_por_nombre("recursos")
        recursos["name"] = "biblioteca"
        recursos["parent_id"] = f.canal_por_nombre("Ayuda", CATEGORIA)["id"]
        f.roles[f.guild["id"]]["permissions"] = str(bits(diseno.PERMISOS_BASE) | bits(["USE_SOUNDBOARD"]))
        codigo, api = self.ejecutar("construir")
        self.assertEqual(api.escrituras, 0)
        self.assertEqual(f.canal_por_nombre("biblioteca")["id"], recursos["id"])
        self.assertEqual(len([c for c in f.canales.values() if c["name"] == "recursos"]), 0)
        self.assertEqual(codigo, 1)  # la verificación avisa de las diferencias, sin tocar nada
        self.assertIn("@everyone: permisos distintos", self.registro())

    def test_reintenta_cuando_discord_limita(self) -> None:
        self.falso.limitar_cada = 5
        self.construir()
        self.assertGreater(self.falso._limitadas, 10)
        self.assertIn("El servidor coincide con el diseño.", self.registro())

    def test_se_detiene_y_retoma(self) -> None:
        self.falso.bloquear_comunidad = True
        codigo, _ = self.ejecutar("construir")
        self.assertEqual(codigo, 1)
        self.assertIn("Me detuve aquí", self.registro())
        self.assertNotIn("COMMUNITY", self.falso.guild["features"])
        creados = len(self.falso.canales)
        self.falso.bloquear_comunidad = False
        self.construir()
        self.assertEqual(len(self.falso.canales), creados + 4)  # solo faltaban anuncios, los dos foros y el escenario

    def test_colores_de_rol_en_la_forma_anterior(self) -> None:
        self.falso.rechazar_colors = True
        self.construir()
        self.assertEqual(self.rol("Tutor")["color"], 0x3498DB)
        self.assertEqual(self.rol("Insignia · POO con Python")["color"], diseno.COLOR_INSIGNIA[2])

    def test_invitacion_sin_roles_si_discord_no_los_acepta(self) -> None:
        self.falso.rechazar_roles_en_invitaciones = True
        self.construir()
        self.assertEqual(self.falso.invitaciones[0]["role_ids"], [])
        self.assertIn("Discord no aceptó que la invitación entregue el rol Estudiante", self.registro())

    def test_verificar_detecta_lo_que_falta(self) -> None:
        self.construir()
        self.assertEqual(self.ejecutar("verificar")[0], 0)
        f = self.falso
        del f.canales[f.canal_por_nombre("setup")["id"]]
        f.canal_por_nombre("tutores")["permission_overwrites"] = []
        del f.roles[self.rol("Organizador")["id"]]
        codigo, api = self.ejecutar("verificar")
        self.assertEqual((codigo, api.escrituras), (1, 0))
        registro = self.registro()
        for esperado in ("falta #setup", "#tutores: permisos distintos", "falta el rol Organizador"):
            self.assertIn(esperado, registro)


class ConstruirConRolesEmpatados(Base):
    """Por si Discord deja todos los roles nuevos en la posición 1 y los ordena por antigüedad."""

    modelo_roles = "empata"

    def test_orden(self) -> None:
        self.construir()
        esperado = ["bot-prueba"] + [r["nombre"] for r in diseno.roles(1)] + ["@everyone"]
        self.assertEqual(self.falso.orden_de_roles(), esperado)
        self.assertFalse([p for p in self.falso.peticiones if p[0] == "PATCH" and p[1].endswith("/roles")])
        codigo, _ = self.ejecutar("publicar", "--fase", "2")
        self.assertEqual(codigo, 0, self.registro())
        esperado = ["bot-prueba"] + [r["nombre"] for r in diseno.roles(2)] + ["@everyone"]
        self.assertEqual(self.falso.orden_de_roles(), esperado)


class ConOnboarding(Base):
    """El onboarding nativo es opcional: se enciende con AJUSTES["onboarding"] = True."""

    def setUp(self) -> None:
        super().setUp()
        diseno.AJUSTES["onboarding"] = True
        self.addCleanup(diseno.AJUSTES.__setitem__, "onboarding", False)

    def test_onboarding(self) -> None:
        self.construir()
        o = self.falso.onboarding
        self.assertTrue(o["enabled"])
        self.assertEqual([p["title"] for p in o["prompts"]], [p["titulo"] for p in diseno.ONBOARDING])
        carrera, semestre, intereses = o["prompts"]
        estudiante = self.rol("Estudiante")["id"]
        for opcion in carrera["options"]:
            self.assertEqual(len(opcion["role_ids"]), 2)
            self.assertIn(estudiante, opcion["role_ids"])
        self.assertTrue(carrera["required"] and carrera["single_select"] and semestre["required"])
        self.assertFalse(intereses["required"] or intereses["single_select"])
        self.assertEqual(intereses["options"][2]["role_ids"], [self.rol("Interés · Python")["id"]])
        self.assertEqual(intereses["options"][2]["emoji"]["name"], "🐍")
        predeterminados = {self.falso.canales[c]["name"] for c in o["default_channel_ids"]}
        self.assertEqual(len(predeterminados), 15)
        self.assertNotIn("tutores", predeterminados)
        self.assertNotIn("pagos-por-validar", predeterminados)

    def test_onboarding_sin_emojis_si_discord_los_rechaza(self) -> None:
        self.falso.rechazar_emojis = True
        self.construir()
        self.assertTrue(self.falso.onboarding["enabled"])
        self.assertIsNone(self.falso.onboarding["prompts"][0]["options"][0]["emoji"]["name"])

    def test_roles_y_segunda_vez(self) -> None:
        self.construir()
        esperado = ["bot-prueba"] + [r["nombre"] for r in diseno.roles(1)] + ["@everyone"]
        self.assertEqual(len(esperado), 25)
        self.assertEqual(self.falso.orden_de_roles(), esperado)
        self.assertEqual(int(self.rol("Interés · Python")["permissions"]), 0)
        codigo, api = self.ejecutar("construir")
        self.assertEqual((codigo, api.escrituras), (0, 0), self.registro())

    def test_se_puede_encender_despues(self) -> None:
        diseno.AJUSTES["onboarding"] = False
        self.construir()
        roles = len(self.falso.roles)
        diseno.AJUSTES["onboarding"] = True
        self.construir()
        self.assertTrue(self.falso.onboarding["enabled"])
        self.assertEqual(len(self.falso.roles), roles + 15)
        esperado = ["bot-prueba"] + [r["nombre"] for r in diseno.roles(1)] + ["@everyone"]
        self.assertEqual(self.falso.orden_de_roles(), esperado)

    def test_publicar_reordena_las_insignias(self) -> None:
        self.construir()
        codigo, _ = self.ejecutar("publicar", "--fase", "2")
        self.assertEqual(codigo, 0, self.registro())
        esperado = ["bot-prueba"] + [r["nombre"] for r in diseno.roles(2)] + ["@everyone"]
        self.assertEqual(self.falso.orden_de_roles(), esperado)
        self.assertTrue([p for p in self.falso.peticiones if p[0] == "PATCH" and p[1].endswith("/roles")])


class ConOnboardingYRolesEmpatados(ConOnboarding):
    modelo_roles = "empata"

    def test_publicar_reordena_las_insignias(self) -> None:
        # Con todos los roles en la posición 1 no hay hueco para subir las insignias nuevas: se avisa.
        self.construir()
        codigo, _ = self.ejecutar("publicar", "--fase", "2")
        self.assertEqual(codigo, 0, self.registro())
        self.assertIn("No pude reordenar los roles", self.registro())
        self.assertEqual(len([r for r in self.falso.roles.values() if r["name"].startswith("Insignia")]), 9)

    def test_se_puede_encender_despues(self) -> None:
        self.skipTest("mismo caso que la clase base")


class Publicar(Base):
    def test_fase_2(self) -> None:
        self.construir()
        canales = len(self.falso.canales)
        codigo, _ = self.ejecutar("publicar", "--fase", "2")
        self.assertEqual(codigo, 0, self.registro())
        f = self.falso
        esperado = ["bot-prueba"] + [r["nombre"] for r in diseno.roles(2)] + ["@everyone"]
        self.assertEqual(f.orden_de_roles(), esperado)
        foro = f.canal_por_nombre("catálogo")
        nombres = [h["name"] for h in f.hilos.values() if h["parent_id"] == foro["id"]]
        self.assertEqual(sorted(nombres), sorted([t["nombre"] for t in catalogo.talleres_hasta(2)] + [catalogo.TITULO_TUTORIAS]))
        self.assertEqual(len(f.canales), canales)
        integracion = next(h for h in f.hilos.values() if h["name"] == "Integración · Aula de integración")
        etiquetas = {e["id"]: e["name"] for e in foro["available_tags"]}
        self.assertEqual([etiquetas[e] for e in integracion["applied_tags"]], ["Taller", "N3 · $30"])

        codigo, api = self.ejecutar("publicar", "--fase", "2")
        self.assertEqual((codigo, api.escrituras), (0, 0))
        # Después de publicar la fase 2, construir y verificar la dan por buena sin repetir nada.
        codigo, api = self.ejecutar("construir")
        self.assertEqual((codigo, api.escrituras), (0, 0), self.registro())
        self.assertEqual(self.estado()["fase"], 2)

    def test_todas_las_fases(self) -> None:
        self.construir()
        codigo, _ = self.ejecutar("publicar", "--fase", "4")
        self.assertEqual(codigo, 0, self.registro())
        foro = self.falso.canal_por_nombre("catálogo")
        self.assertEqual(len([h for h in self.falso.hilos.values() if h["parent_id"] == foro["id"]]), 31)
        self.assertEqual(len([r for r in self.falso.roles.values() if r["name"].startswith("Insignia · ")]), 30)
        self.assertEqual(self.ejecutar("verificar")[0], 0)


def dentro_de(dias: int, hora: int = 10) -> datetime:
    zona = timezone(timedelta(hours=diseno.AJUSTES["utc_offset_horas"]))
    return (datetime.now(zona) + timedelta(days=dias)).replace(hour=hora, minute=0, second=0, microsecond=0)


def sufijo(fecha: datetime) -> str:
    return f"{fecha.day:02d}{servidor.MESES[fecha.month - 1]}"


class Aulas(Base):
    def setUp(self) -> None:
        super().setUp()
        self.construir()
        self.ana = self.falso.agregar_miembro("ana.perez", "Ana Pérez")
        self.luis = self.falso.agregar_miembro("luis_x", "Luis")
        self.otra_ana = self.falso.agregar_miembro("anabel", "Anabel")

    def crear(self, *extra: str, taller: str = "poo-python", dias: int = 3) -> Tuple[int, datetime]:
        inicio = dentro_de(dias)
        codigo, _ = self.ejecutar("aula", "crear", taller, "--inicio", inicio.strftime("%Y-%m-%d %H:%M"), *extra)
        return codigo, inicio

    def test_crear(self) -> None:
        codigo, inicio = self.crear("--miembros", "ana.perez", f"<@{self.luis}>", "--kit", "https://github.com/ejemplo/kit")
        self.assertEqual(codigo, 0, self.registro())
        f = self.falso
        clave = f"poo-python-{sufijo(inicio)}"
        visible = f"Aula · POO con Python · {inicio.day} {servidor.MESES[inicio.month - 1]}"
        rol = self.rol(visible)
        self.assertEqual(int(rol["permissions"]), 0)
        self.assertEqual(self.nombres_hijos("Aulas activas"), [f"aula-{clave}", visible])
        texto, voz = f.canal_por_nombre(f"aula-{clave}"), f.canal_por_nombre(visible, VOZ)
        self.assertEqual(voz["user_limit"], 6)
        self.assertIn("POO con Python", texto["topic"])
        self.assertIn(f"{inicio.day} de {servidor.MESES_LARGOS[inicio.month - 1]}, 10:00", texto["topic"])

        for canal in (texto, voz):
            del_aula = f.permisos_en([rol["id"]], canal["id"])
            for permiso in diseno.PERMISOS_AULA:
                self.assertTrue(puede(del_aula, permiso), permiso)
            self.assertFalse(puede(f.permisos_en([], canal["id"]), "VIEW_CHANNEL"))
            self.assertFalse(puede(f.permisos_en([self.rol("Estudiante")["id"]], canal["id"]), "VIEW_CHANNEL"))
            self.assertTrue(puede(f.permisos_en([self.rol("Tutor")["id"]], canal["id"]), "VIEW_CHANNEL"))
        estudiante = self.rol("Estudiante")["id"]
        for id in (self.ana, self.luis):
            self.assertEqual(set(f.miembros[id]["roles"]), {rol["id"], estudiante})
        self.assertEqual(f.miembros[self.otra_ana]["roles"], [])

        # El enlace del aula cubre los cupos que faltan y entrega los dos roles a quien lo abre.
        enlaces = [i for i in f.invitaciones if i["channel_id"] == texto["id"]]
        self.assertEqual(len(enlaces), 1)
        self.assertEqual((enlaces[0]["max_uses"], enlaces[0]["max_age"], enlaces[0]["role_ids"]), (3, 0, [rol["id"], estudiante]))
        enlace = f"https://discord.gg/{enlaces[0]['code']}"
        self.assertIn(f"Enlace para el grupo (3 usos; pégalo en el hilo de la reserva): {enlace}", self.registro())
        nuevos = [self.otra_ana, f.agregar_miembro("pedro"), f.agregar_miembro("sofia")]
        for id in nuevos:
            f.aceptar_invitacion(enlace, id)
            self.assertEqual(set(f.miembros[id]["roles"]), {rol["id"], estudiante})
        with self.assertRaises(KeyError):  # el sexto ya no entra
            f.aceptar_invitacion(enlace, f.agregar_miembro("colado"))

        evento = f.eventos[0]
        self.assertEqual((evento["entity_type"], evento["channel_id"], evento["name"]), (2, voz["id"], "POO con Python"))
        self.assertEqual(datetime.fromisoformat(evento["scheduled_start_time"]), inicio)
        self.assertEqual(datetime.fromisoformat(evento["scheduled_end_time"]), inicio + timedelta(hours=2))

        mensajes = f.mensajes[texto["id"]]
        self.assertEqual(len(mensajes), 1)  # el aviso de «fijó un mensaje» se borra
        preparacion = mensajes[0]
        self.assertTrue(preparacion["pinned"])
        self.assertEqual(preparacion["mention_roles"], [rol["id"]])
        for esperado in (
            f"<t:{int(inicio.timestamp())}:F>", f"<#{voz['id']}>", "dura 2 horas",
            "comprueba que carga: https://github.com/ejemplo/kit.", f"https://discord.com/events/{f.guild['id']}/{evento['id']}",
        ):
            self.assertIn(esperado, preparacion["content"])
        self.assertNotIn("{", preparacion["content"])
        bitacora = f.mensajes[f.canal_por_nombre("bitácora")["id"]]
        self.assertIn("Aula creada", bitacora[-1]["content"])
        self.assertIn("2 dentro", bitacora[-1]["content"])
        self.assertIn(f"Enlace para el grupo (3 usos): <{enlace}>", bitacora[-1]["content"])
        self.assertEqual(self.ejecutar("verificar")[0], 0)  # las aulas no cuentan como diferencias

    def test_sin_miembros_y_sin_invitaciones_de_comunidad(self) -> None:
        # Lo normal: el aula se crea vacía y el grupo entra con el enlace (5 usos).
        codigo, _ = self.crear()
        self.assertEqual(codigo, 0, self.registro())
        self.assertEqual(self.falso.invitaciones[-1]["max_uses"], 5)
        # Si Discord no acepta roles en el enlace, el aula se crea igual y se explica cómo hacerlo a mano.
        self.falso.rechazar_roles_en_invitaciones = True
        codigo, _ = self.crear(taller="github")
        self.assertEqual(codigo, 0, self.registro())
        self.assertIn("Créalo a mano", self.registro())
        self.assertEqual(len(self.falso.invitaciones), 2)

    def test_tutoria_con_titulo_libre(self) -> None:
        codigo, inicio = self.crear("--miembros", "luis_x", "--horas", "1", taller="Tutoría · Cálculo", dias=2)
        self.assertEqual(codigo, 0, self.registro())
        texto = self.falso.canal_por_nombre(f"aula-tutoria-calculo-{sufijo(inicio)}")
        contenido = self.falso.mensajes[texto["id"]][0]["content"]
        self.assertIn("dura 1 hora en", contenido)
        self.assertNotIn("Codespaces", contenido)
        self.assertEqual(self.falso.eventos[0]["name"], "Tutoría · Cálculo")

    def test_nombres_de_usuario(self) -> None:
        # «ana» coincide con ana.perez y anabel: hay que desambiguar.
        codigo, _ = self.crear("--miembros", "ana")
        self.assertEqual(codigo, 2)
        self.assertIn("coincide con varias personas", self.registro())
        codigo, _ = self.crear("--miembros", "nadie")
        self.assertEqual(codigo, 2)
        self.assertIn("No encuentro a «nadie»", self.registro())
        codigo, _ = self.crear("--miembros", "123456789012345678")
        self.assertEqual(codigo, 2)
        self.assertIn("no está en el servidor", self.registro())
        self.assertEqual(self.nombres_hijos("Aulas activas"), [])  # nada quedó a medias
        codigo, _ = self.crear("--miembros", "@Anabel", "LUIS_X")
        self.assertEqual(codigo, 0, self.registro())

    def test_limites(self) -> None:
        seis = ["ana.perez", "luis_x", "anabel"] + [self.falso.agregar_miembro(f"extra{i}") for i in range(3)]
        codigo, _ = self.crear("--miembros", *seis)
        self.assertEqual(codigo, 2)
        self.assertIn("máximo 5 personas", self.registro())
        codigo, _ = self.crear("--miembros", *seis, "--forzar")
        self.assertEqual(codigo, 0, self.registro())
        self.assertEqual(len(self.falso.invitaciones), 1)  # aula llena: no hace falta enlace
        codigo, _ = self.crear("--miembros", "luis_x")
        self.assertEqual(codigo, 2)
        self.assertIn("Ya existe #aula-poo-python", self.registro())
        codigo, _ = self.crear("--miembros", "luis_x", "--clave", "poo tarde", "--sin-enlace")
        self.assertEqual(codigo, 0, self.registro())
        self.assertEqual(len(self.falso.invitaciones), 1)
        self.assertIn("aula-poo-tarde-", self.registro())
        codigo, _ = self.crear(dias=-1)
        self.assertEqual(codigo, 2)
        self.assertIn("ya pasó", self.registro())

    def test_archivar(self) -> None:
        codigo, inicio = self.crear("--miembros", "ana.perez", "luis_x")
        self.assertEqual(codigo, 0, self.registro())
        f = self.falso
        clave = f"poo-python-{sufijo(inicio)}"
        visible = f"Aula · POO con Python · {inicio.day} {servidor.MESES[inicio.month - 1]}"
        rol = self.rol(visible)["id"]
        self.assertEqual(self.ejecutar("aula", "listar")[0], 0)
        self.assertIn(clave, self.registro())
        self.assertNotIn("VENCIDA", self.registro())
        self.assertEqual(self.ejecutar("aula", "archivar", "--vencidas")[0], 0)
        self.assertIn("No hay aulas vencidas.", self.registro())
        self.assertEqual(self.ejecutar("aula", "archivar", "no-existe")[0], 2)

        self.assertEqual(len(f.invitaciones), 2)
        codigo, _ = self.ejecutar("aula", "archivar", f"aula-{clave}")
        self.assertEqual(codigo, 0, self.registro())
        self.assertEqual(len(f.invitaciones), 1)  # el enlace del aula se anula; queda el del servidor
        self.assertEqual(f.miembros[self.ana]["roles"], [self.rol("Estudiante")["id"]])
        self.assertEqual(self.nombres_hijos("Aulas activas"), [])
        self.assertEqual(self.nombres_hijos("Archivo"), [f"aula-{clave}"])
        self.assertNotIn(rol, f.roles)
        self.assertNotIn(rol, f.miembros[self.ana]["roles"])
        self.assertEqual(f.eventos, [])
        texto = f.canal_por_nombre(f"aula-{clave}")
        self.assertFalse(puede(f.permisos_en([], texto["id"]), "VIEW_CHANNEL"))
        self.assertTrue(puede(f.permisos_en([self.rol("Tutor")["id"]], texto["id"]), "VIEW_CHANNEL"))
        self.assertEqual(len(f.mensajes[texto["id"]]), 1)  # el canal conserva su contenido
        self.assertIn("Aula archivada", f.mensajes[f.canal_por_nombre("bitácora")["id"]][-1]["content"])

    def test_archivar_vencidas(self) -> None:
        f = self.falso
        # Un aula reservada hace 20 días cuya clase fue hace 10, y otra para la próxima semana.
        f.ahora_ms = int((time.time() - 20 * 86400) * 1000)
        codigo, vieja = self.crear("--sin-evento", "--miembros", "ana.perez", taller="github", dias=-10)
        self.assertEqual(codigo, 0, self.registro())
        f.ahora_ms = None
        codigo, nueva = self.crear("--miembros", "luis_x", dias=6)
        self.assertEqual(codigo, 0, self.registro())
        self.ejecutar("aula", "listar")
        self.assertIn("clase hace 9 días · VENCIDA", self.registro())
        codigo, _ = self.ejecutar("aula", "archivar", "--vencidas")
        self.assertEqual(codigo, 0, self.registro())
        self.assertEqual(self.nombres_hijos("Archivo"), [f"aula-github-{sufijo(vieja)}"])
        self.assertEqual(len(self.nombres_hijos("Aulas activas")), 2)
        self.assertEqual(len([r for r in f.roles.values() if r["name"].startswith("Aula · ")]), 1)


class SinServidor(Base):
    def test_el_bot_aun_no_esta_invitado(self) -> None:
        del self.falso.miembros[self.falso.bot["id"]]
        codigo, api = self.ejecutar("construir")
        self.assertEqual((codigo, api.escrituras), (2, 0))
        self.assertIn(f"https://discord.com/oauth2/authorize?client_id={self.falso.bot['id']}&scope=bot&permissions=8", self.registro())

    def test_el_bot_no_es_administrador(self) -> None:
        self.falso.roles[self.falso.rol_bot]["permissions"] = str(bits(["MANAGE_CHANNELS", "MANAGE_ROLES"]))
        codigo, api = self.ejecutar("construir")
        self.assertEqual((codigo, api.escrituras), (2, 0))
        self.assertIn("no tiene permiso de Administrador", self.registro())

    def test_token_invalido(self) -> None:
        api = servidor.Api("otro-token", base=self.url, dormir=lambda s: None)
        codigo = servidor.main(["construir"], carpeta=self.carpeta, api=api, silencio=True)
        self.assertEqual(codigo, 2)
        self.assertIn("El token no es válido", self.registro())


class Config(unittest.TestCase):
    def test_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            with self.assertRaises(servidor.ErrorDeUso):
                servidor.cargar_config(carpeta)
            (carpeta / ".env").write_text('# comentario\nDISCORD_TOKEN = "Bot abc.def.ghi"\nGUILD_ID=\n', encoding="utf-8")
            viejo = {k: os.environ.pop(k, None) for k in ("DISCORD_TOKEN", "GUILD_ID")}
            try:
                self.assertEqual(servidor.cargar_config(carpeta), ("abc.def.ghi", None))
                (carpeta / ".env").write_text("DISCORD_TOKEN=pega-aqui-el-token\n", encoding="utf-8")
                with self.assertRaises(servidor.ErrorDeUso):
                    servidor.cargar_config(carpeta)
            finally:
                for k, v in viejo.items():
                    if v is not None:
                        os.environ[k] = v


class Diseno(unittest.TestCase):
    """Límites de Discord que se pueden revisar sin conectarse."""

    def test_catalogo_completo(self) -> None:
        self.assertEqual(len(catalogo.TALLERES), 30)
        self.assertEqual(len({t["id"] for t in catalogo.TALLERES}), 30)
        self.assertEqual([len([t for t in catalogo.TALLERES if t["fase"] == f]) for f in (1, 2, 3, 4)], [4, 5, 6, 15])
        self.assertEqual([len([t for t in catalogo.TALLERES if t["nivel"] == n]) for n in (1, 2, 3)], [3, 15, 12])
        validas = set(catalogo.ETIQUETAS_TECNOLOGIA)
        for t in catalogo.TALLERES:
            self.assertTrue(set(t["etiquetas"]) <= validas, t["id"])
            self.assertLessEqual(len(catalogo.etiquetas_taller(t)), 5, t["id"])
            self.assertLessEqual(len(t["nombre"]), 100)
            self.assertLessEqual(len(f"Insignia · {t['insignia']}"), 100)
            # Con las menciones resueltas (unos 25 caracteres cada una) sigue cabiendo en un mensaje.
            self.assertLessEqual(len(catalogo.texto_taller(t)) + 200, 2000, t["id"])
        self.assertLessEqual(len(catalogo.texto_tutorias()) + 200, 2000)

    def test_precios(self) -> None:
        self.assertEqual(catalogo.por_persona(10), "1 persona $10 · 2 personas $5 · 3 personas $3,33 · 4 personas $2,50 · 5 personas $2")
        self.assertEqual(catalogo.por_persona(30), "1 persona $30 · 2 personas $15 · 3 personas $10 · 4 personas $7,50 · 5 personas $6")
        self.assertEqual(catalogo.dinero(20 / 3), "$6,67")

    def test_limites_de_discord(self) -> None:
        nombres = [r["nombre"] for r in diseno.roles(99)]
        self.assertEqual(len(nombres), len(set(nombres)))
        self.assertLess(len(nombres), 240)
        claves = [c["clave"] for c in diseno.canales()] + [c["clave"] for c in diseno.CATEGORIAS]
        self.assertEqual(len(claves), len(set(claves)))
        for canal in diseno.canales():
            self.assertLessEqual(len(canal.get("tema") or ""), 1024, canal["clave"])
            etiquetas = canal.get("etiquetas", [])
            self.assertLessEqual(len(etiquetas), 20, canal["clave"])
            for e in etiquetas:
                self.assertTrue(1 <= len(e["nombre"]) <= 20, e["nombre"])
        for clave, mensajes in diseno.MENSAJES.items():
            self.assertIn(clave, claves)
            for texto in mensajes:
                self.assertLessEqual(len(texto) + 300, 2000, clave)
        self.assertLessEqual(len(diseno.MENSAJE_AULA) + 400, 2000)
        self.assertLessEqual(len(diseno.AJUSTES["descripcion"]), 300)
        self.assertLessEqual(len(diseno.AUTOMOD_MENSAJE), 150)
        for pregunta in diseno.ONBOARDING:
            self.assertLessEqual(len(pregunta["titulo"]), 100)
            for o in pregunta["opciones"]:
                self.assertTrue(1 <= len(o["titulo"]) <= 50, o["titulo"])
                self.assertLessEqual(len(o.get("descripcion") or ""), 100, o["titulo"])
        todos = diseno.PERMISOS_BASE + diseno.PERMISOS_TUTOR + diseno.PERMISOS_AULA
        for categoria in diseno.CATEGORIAS:
            for regla in categoria["permisos"] + [r for c in categoria["canales"] for r in c.get("permisos", [])]:
                todos += regla.get("permite", []) + regla.get("niega", [])
        for permiso in todos:
            self.assertIn(permiso, servidor.PERMISOS)
        # Nadie fuera del Admin recibe permisos de administración del servidor.
        peligrosos = {"ADMINISTRATOR", "MANAGE_GUILD", "MANAGE_ROLES", "MANAGE_WEBHOOKS", "KICK_MEMBERS", "BAN_MEMBERS", "MENTION_EVERYONE"}
        self.assertFalse(peligrosos & set(diseno.PERMISOS_BASE))
        self.assertFalse((peligrosos - {"MENTION_EVERYONE"}) & set(diseno.PERMISOS_TUTOR))

    def test_utilidades(self) -> None:
        self.assertEqual(servidor.slug("Tutoría · Cálculo I"), "tutoria-calculo-i")
        self.assertEqual(servidor.normal("Prácticas y Empleos", TEXTO), "prácticas-y-empleos")
        self.assertEqual(servidor.normal("Sala de estudio", VOZ), "sala de estudio")
        self.assertEqual(servidor.horas_texto(1), "1 hora")
        self.assertEqual(servidor.horas_texto(1.5), "1,5 horas")
        fecha = servidor.leer_fecha("2026-10-17 10:00")
        self.assertEqual(fecha.isoformat(), "2026-10-17T10:00:00-05:00")
        self.assertEqual(servidor.fecha_larga(fecha), "sábado 17 de octubre, 10:00")
        self.assertEqual(servidor.leer_fecha("17/10/2026 10:00"), fecha)
        with self.assertRaises(servidor.ErrorDeUso):
            servidor.leer_fecha("mañana")
        e = servidor.ErrorApi(400, {"code": 50035, "message": "Invalid Form Body", "errors": {"available_tags": {"3": {"name": {"_errors": [{"code": "X", "message": "Muy largo"}]}}}}}, "POST", "/x")
        self.assertIn("available_tags.3.name: Muy largo", str(e))


if __name__ == "__main__":
    unittest.main()
