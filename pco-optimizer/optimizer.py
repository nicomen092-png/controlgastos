"""Motor de optimización de PCO OPTIMIZATION APP.

Cada ajuste (Tweak) sabe tres cosas:
  - backup():  leer el valor actual del sistema (para poder volver atrás)
  - apply():   aplicar el valor optimizado
  - restore(): volver a poner el valor guardado

Antes de optimizar se guarda una copia de seguridad en
%ProgramData%\\PCO Optimization\\backup.json y se crea una tarea programada que,
en el siguiente inicio de sesión (es decir, al reiniciar), ejecuta la app con
--restore para devolver todo a como estaba.

Solo se usan ajustes que actúan en caliente (sin reiniciar), porque al reiniciar
se revierten.
"""

import ctypes
import datetime
import json
import os
import re
import subprocess
import sys
import time

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import winreg
    from ctypes import wintypes

APP_NAME = "PCO OPTIMIZATION APP"
DATA_DIR = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "PCO Optimization")
BACKUP_FILE = os.path.join(DATA_DIR, "backup.json")
LOG_FILE = os.path.join(DATA_DIR, "pco.log")
TASK_NAME = r"PCO Optimization\Restaurar al reiniciar"

# Valor pedido para Win32PrioritySeparation (decimal 32 = 0x20).
# Si prefieres el valor más usado en la comunidad gamer, 38 (0x26), cámbialo aquí.
WIN32_PRIORITY_VALUE = 32

ULTIMATE_PERFORMANCE = "e9a42b02-d5df-448d-aa00-03f14749eb61"
HIGH_PERFORMANCE = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
# GUID fijo para la copia del plan "Máximo rendimiento" que crea la app,
# así no se duplica cada vez y se puede borrar al restaurar.
PCO_PLAN_GUID = "7c0f3a55-9c3e-4e1b-8f7a-5043f0a1c0de"

CREATE_NO_WINDOW = 0x08000000
GUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


# --------------------------------------------------------------------------- utilidades

def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    return line


def run(args):
    """Ejecuta un comando sin abrir ventana de consola y devuelve (código, salida)."""
    p = subprocess.run(args, capture_output=True, creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0)
    out = (p.stdout or b"") + (p.stderr or b"")
    return p.returncode, out.decode("mbcs" if IS_WINDOWS else "utf-8", errors="ignore")


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def reg_read(root, path, name):
    """Devuelve (valor, tipo) o None si no existe."""
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as k:
            return list(winreg.QueryValueEx(k, name))
    except FileNotFoundError:
        return None


def reg_write(root, path, name, value, kind):
    with winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, kind, value)


def reg_restore(root, path, name, saved):
    """Restaura un valor guardado con reg_read; si no existía, lo borra."""
    if saved is None:
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except FileNotFoundError:
            pass
        return
    value, kind = saved
    if kind == winreg.REG_BINARY and isinstance(value, str):
        value = bytes.fromhex(value)
    reg_write(root, path, name, value, kind)


def reg_snapshot(root, path, name):
    """Como reg_read pero serializable en JSON (binarios en hex)."""
    v = reg_read(root, path, name)
    if v and isinstance(v[0], (bytes, bytearray)):
        v[0] = bytes(v[0]).hex()
    return v


def broadcast_setting_change(area):
    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
    res = wintypes.DWORD()
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, ctypes.c_wchar_p(area), SMTO_ABORTIFHUNG, 2000, ctypes.byref(res))


# --- SystemParametersInfo

SPIF_UPDATE = 0x01 | 0x02  # SPIF_UPDATEINIFILE | SPIF_SENDCHANGE


class ANIMATIONINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("iMinAnimate", ctypes.c_int)]


def spi_get_bool(action):
    val = wintypes.BOOL()
    ctypes.windll.user32.SystemParametersInfoW(action, 0, ctypes.byref(val), 0)
    return bool(val.value)


def spi_set_bool_pv(action, value):
    # Para las acciones 0x10xx el valor BOOL va directamente en pvParam.
    ctypes.windll.user32.SystemParametersInfoW(action, 0, ctypes.c_void_p(1 if value else 0), SPIF_UPDATE)


def spi_get_min_animate():
    ai = ANIMATIONINFO(ctypes.sizeof(ANIMATIONINFO), 0)
    ctypes.windll.user32.SystemParametersInfoW(0x0048, ai.cbSize, ctypes.byref(ai), 0)  # SPI_GETANIMATION
    return ai.iMinAnimate


def spi_set_min_animate(value):
    ai = ANIMATIONINFO(ctypes.sizeof(ANIMATIONINFO), int(value))
    ctypes.windll.user32.SystemParametersInfoW(0x0049, ai.cbSize, ctypes.byref(ai), SPIF_UPDATE)  # SPI_SETANIMATION


# (GET, SET) de las animaciones de la interfaz que se desactivan.
UI_ANIMATIONS = {
    "client_area": (0x1042, 0x1043),   # animaciones dentro de ventanas
    "menu": (0x1002, 0x1003),          # menús que se deslizan / aparecen
    "combobox": (0x1004, 0x1005),      # listas desplegables
    "listbox_smooth": (0x1006, 0x1007),  # desplazamiento suave de listas
    "tooltip": (0x1016, 0x1017),       # tooltips animados
    "selection_fade": (0x1014, 0x1015),  # desvanecer selección de menús
}


# --------------------------------------------------------------------------- ajustes

class Tweak:
    id = ""
    title = ""
    description = ""
    required = False      # siempre se aplica (lo pidió PCO)
    default = True        # marcado por defecto (solo para extras)

    def backup(self):
        raise NotImplementedError

    def apply(self):
        raise NotImplementedError

    def restore(self, saved):
        raise NotImplementedError


class Win32Priority(Tweak):
    id = "win32_priority"
    title = f"Prioridad Win32 = {WIN32_PRIORITY_VALUE}"
    description = "Cambia cómo Windows reparte el CPU entre el juego y los procesos de fondo."
    required = True
    KEY = r"SYSTEM\CurrentControlSet\Control\PriorityControl"

    def backup(self):
        return reg_snapshot(winreg.HKEY_LOCAL_MACHINE, self.KEY, "Win32PrioritySeparation")

    def apply(self):
        reg_write(winreg.HKEY_LOCAL_MACHINE, self.KEY, "Win32PrioritySeparation", WIN32_PRIORITY_VALUE, winreg.REG_DWORD)

    def restore(self, saved):
        reg_restore(winreg.HKEY_LOCAL_MACHINE, self.KEY, "Win32PrioritySeparation", saved)


class UltimatePowerPlan(Tweak):
    id = "power_plan"
    title = "Plan de energía: Máximo rendimiento (Ultimate)"
    description = "CPU siempre a máxima frecuencia, sin aparcar núcleos ni ahorro de energía."
    required = True

    def backup(self):
        _, out = run(["powercfg", "/getactivescheme"])
        m = GUID_RE.search(out)
        return m.group(0).lower() if m else None

    def apply(self):
        _, listing = run(["powercfg", "/list"])
        if PCO_PLAN_GUID not in listing.lower():
            run(["powercfg", "-duplicatescheme", ULTIMATE_PERFORMANCE, PCO_PLAN_GUID])
        code, _ = run(["powercfg", "/setactive", PCO_PLAN_GUID])
        if code != 0:
            # Algunos portátiles (Modern Standby) no permiten Ultimate: usar Alto rendimiento.
            code, _ = run(["powercfg", "/setactive", HIGH_PERFORMANCE])
            if code != 0:
                raise RuntimeError("Este equipo no permite cambiar a Máximo/Alto rendimiento")
            return "Ultimate no disponible en este equipo; se activó Alto rendimiento"

    def restore(self, saved):
        if saved:
            run(["powercfg", "/setactive", saved])
        if saved != PCO_PLAN_GUID:
            run(["powercfg", "-delete", PCO_PLAN_GUID])


class NoAnimations(Tweak):
    id = "animations"
    title = "Quitar animaciones de Windows"
    description = "Ventanas, menús, listas y barra de tareas sin animaciones: todo responde al instante."
    required = True
    DESKTOP = r"Control Panel\Desktop"
    ADVANCED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    VISUALFX = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"

    def backup(self):
        return {
            "min_animate": spi_get_min_animate(),
            "spi": {k: spi_get_bool(get) for k, (get, _) in UI_ANIMATIONS.items()},
            "UserPreferencesMask": reg_snapshot(winreg.HKEY_CURRENT_USER, self.DESKTOP, "UserPreferencesMask"),
            "TaskbarAnimations": reg_snapshot(winreg.HKEY_CURRENT_USER, self.ADVANCED, "TaskbarAnimations"),
            "VisualFXSetting": reg_snapshot(winreg.HKEY_CURRENT_USER, self.VISUALFX, "VisualFXSetting"),
        }

    def apply(self):
        spi_set_min_animate(0)
        for _, set_ in UI_ANIMATIONS.values():
            spi_set_bool_pv(set_, False)
        reg_write(winreg.HKEY_CURRENT_USER, self.ADVANCED, "TaskbarAnimations", 0, winreg.REG_DWORD)
        reg_write(winreg.HKEY_CURRENT_USER, self.VISUALFX, "VisualFXSetting", 3, winreg.REG_DWORD)  # personalizado
        broadcast_setting_change("TraySettings")

    def restore(self, saved):
        spi_set_min_animate(saved["min_animate"])
        for k, (_, set_) in UI_ANIMATIONS.items():
            spi_set_bool_pv(set_, saved["spi"].get(k, True))
        reg_restore(winreg.HKEY_CURRENT_USER, self.DESKTOP, "UserPreferencesMask", saved["UserPreferencesMask"])
        reg_restore(winreg.HKEY_CURRENT_USER, self.ADVANCED, "TaskbarAnimations", saved["TaskbarAnimations"])
        reg_restore(winreg.HKEY_CURRENT_USER, self.VISUALFX, "VisualFXSetting", saved["VisualFXSetting"])
        broadcast_setting_change("TraySettings")


class RegistryTweak(Tweak):
    """Ajuste genérico: lista de (raíz, ruta, nombre, valor DWORD)."""
    values = []
    notify = None

    def backup(self):
        return [reg_snapshot(root, path, name) for root, path, name, _ in self.values]

    def apply(self):
        for root, path, name, value in self.values:
            reg_write(root, path, name, value, winreg.REG_DWORD)
        if self.notify:
            broadcast_setting_change(self.notify)

    def restore(self, saved):
        for (root, path, name, _), old in zip(self.values, saved):
            reg_restore(root, path, name, old)
        if self.notify:
            broadcast_setting_change(self.notify)


class GameMode(RegistryTweak):
    id = "game_mode"
    title = "Activar Modo Juego de Windows"
    description = "Windows da prioridad al juego y frena actualizaciones/tareas mientras juegas."
    if IS_WINDOWS:
        values = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AllowAutoGameMode", 1),
        ]


class NoGameDVR(RegistryTweak):
    id = "game_dvr"
    title = "Desactivar grabación en segundo plano (Game DVR)"
    description = "Evita que Xbox Game Bar grabe el juego de fondo: menos uso de GPU y menos stutter."
    if IS_WINDOWS:
        values = [
            (winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", "GameDVR_Enabled", 0),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0),
        ]


class NoTransparency(RegistryTweak):
    id = "transparency"
    title = "Quitar transparencias"
    description = "Menos trabajo para el compositor de Windows (DWM) mientras juegas."
    notify = "ImmersiveColorSet"
    if IS_WINDOWS:
        values = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
             "EnableTransparency", 0),
        ]


class PauseBackgroundServices(Tweak):
    id = "services"
    title = "Pausar servicios de fondo que usan disco/CPU"
    description = "Detiene SysMain (Superfetch), Windows Search y telemetría hasta reiniciar."
    SERVICES = ["SysMain", "WSearch", "DiagTrack"]

    @staticmethod
    def _running(name):
        _, out = run(["sc", "query", name])
        return bool(re.search(r"\b4\s+RUNNING", out))

    def backup(self):
        return [s for s in self.SERVICES if self._running(s)]

    def apply(self):
        for s in self.SERVICES:
            run(["sc", "stop", s])

    def restore(self, saved):
        for s in saved or []:
            run(["sc", "start", s])


class NoMouseAcceleration(Tweak):
    id = "mouse_accel"
    title = "Quitar aceleración del mouse"
    description = "Apuntado 1:1, más consistente. Cambia la sensación del mouse, por eso viene desmarcado."
    default = False

    def backup(self):
        arr = (ctypes.c_int * 3)()
        ctypes.windll.user32.SystemParametersInfoW(0x0003, 0, arr, 0)  # SPI_GETMOUSE
        return list(arr)

    def _set(self, values):
        arr = (ctypes.c_int * 3)(*values)
        ctypes.windll.user32.SystemParametersInfoW(0x0004, 0, arr, SPIF_UPDATE)  # SPI_SETMOUSE

    def apply(self):
        self._set([0, 0, 0])

    def restore(self, saved):
        self._set(saved)


REQUIRED_TWEAKS = [Win32Priority(), UltimatePowerPlan(), NoAnimations()]
EXTRA_TWEAKS = [GameMode(), NoGameDVR(), NoTransparency(), PauseBackgroundServices(), NoMouseAcceleration()]
ALL_TWEAKS = {t.id: t for t in REQUIRED_TWEAKS + EXTRA_TWEAKS}


# --------------------------------------------------------------------------- estado / reinicio

def load_backup():
    try:
        with open(BACKUP_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def is_optimized():
    return load_backup() is not None


def boot_time():
    """Momento (epoch) en que arrancó Windows."""
    ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    return time.time() - ctypes.windll.kernel32.GetTickCount64() / 1000.0


def rebooted_since_optimize():
    b = load_backup()
    return bool(b) and boot_time() > b.get("timestamp", 0) + 5


def restore_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --restore'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    script = os.path.abspath(sys.argv[0])
    return f'"{pythonw}" "{script}" --restore'


def create_restore_task():
    user = f'{os.environ.get("USERDOMAIN", "")}\\{os.environ.get("USERNAME", "")}'
    code, out = run(["schtasks", "/Create", "/F", "/TN", TASK_NAME, "/TR", restore_command(),
                     "/SC", "ONLOGON", "/RU", user, "/IT", "/RL", "HIGHEST"])
    if code != 0:
        raise RuntimeError(out.strip() or "no se pudo crear la tarea de restauración")


def delete_restore_task():
    run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME])


def optimize(extra_ids, report=print):
    """Guarda copia de seguridad (solo la primera vez), aplica ajustes y programa la restauración."""
    os.makedirs(DATA_DIR, exist_ok=True)
    backup = load_backup()
    first_time = backup is None
    if first_time:
        backup = {"timestamp": time.time(), "tweaks": {}}

    selected = REQUIRED_TWEAKS + [t for t in EXTRA_TWEAKS if t.id in extra_ids]
    ok = 0
    for t in selected:
        try:
            if t.id not in backup["tweaks"]:
                backup["tweaks"][t.id] = t.backup()
                # Guardar antes de tocar nada: si algo falla, igual se puede volver atrás.
                with open(BACKUP_FILE, "w", encoding="utf-8") as f:
                    json.dump(backup, f, indent=2)
            note = t.apply()
            ok += 1
            report(log(f"✔ {t.title}" + (f" ({note})" if note else "")))
        except Exception as e:  # noqa: BLE001 - seguimos con el resto de ajustes
            report(log(f"✖ {t.title}: {e}"))

    try:
        create_restore_task()
        report(log("✔ Restauración automática programada para el próximo reinicio"))
    except Exception as e:  # noqa: BLE001
        report(log(f"⚠ No se pudo programar la restauración automática ({e}). "
                   "Abre la app tras reiniciar o usa «Restaurar ahora»."))
    return ok, len(selected)


def restore(report=print):
    backup = load_backup()
    if not backup:
        delete_restore_task()
        report(log("No hay nada que restaurar"))
        return
    # Orden inverso al de aplicación.
    for tid, saved in reversed(list(backup["tweaks"].items())):
        t = ALL_TWEAKS.get(tid)
        if not t:
            continue
        try:
            t.restore(saved)
            report(log(f"↺ {t.title}: restaurado"))
        except Exception as e:  # noqa: BLE001
            report(log(f"✖ {t.title}: no se pudo restaurar ({e})"))
    os.remove(BACKUP_FILE)
    delete_restore_task()
    report(log("Configuración original restaurada"))
