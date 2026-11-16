"""Interactive installation experience for KatalIArc."""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.styles import Style

AGENTS = [
    ("codex", "OpenAI Codex"),
    ("claude", "Claude Code"),
    ("gemini", "Google Gemini CLI"),
    ("copilot", "GitHub Copilot"),
]

BANNER = """██╗  ██╗ █████╗ ████████╗ █████╗ ██╗     ██╗ █████╗ ██████╗  ██████╗
██║ ██╔╝██╔══██╗╚══██╔══╝██╔══██╗██║     ██║██╔══██╗██╔══██╗██╔════╝
█████╔╝ ███████║   ██║   ███████║██║     ██║███████║██████╔╝██║
██╔═██╗ ██╔══██║   ██║   ██╔══██║██║     ██║██╔══██║██╔══██╗██║
██║  ██╗██║  ██║   ██║   ██║  ██║███████╗██║██║  ██║██║  ██║╚██████╗
╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝

                         Desarrollado por MODALS4SW@UV
                         Copyright © 2026"""


def clear_terminal(stream=None) -> bool:
    """Clear a real interactive terminal before showing the init banner."""
    stream = stream or sys.stdout
    if not getattr(stream, "isatty", lambda: False)() or os.environ.get("TERM") == "dumb":
        return False
    stream.write("\033[2J\033[H")
    stream.flush()
    return True


def render_banner(stream=None, *, enabled: bool = True) -> None:
    stream = stream or sys.stdout
    if not enabled:
        return
    try:
        BANNER.encode(getattr(stream, "encoding", None) or "utf-8")
        stream.write(BANNER + "\n\n")
    except (UnicodeEncodeError, LookupError):
        stream.write("KATALIARC\n\n")


def play_retro_music() -> bool:
    """Play a short generated 8-bit tune when a native local player is available."""
    winsound = None
    if sys.platform == "win32":
        try:
            import winsound as native_winsound
            winsound = native_winsound
        except ImportError:
            return False
        player = None
    else:
        player = shutil.which("afplay") if sys.platform == "darwin" else (shutil.which("paplay") or shutil.which("aplay"))
    if sys.platform != "win32" and not player:
        return False
    sample_rate = 22050
    notes = ((523, .12), (659, .12), (784, .12), (1047, .22), (784, .12), (1047, .28), (0, .05), (784, .12), (659, .12), (523, .24))
    samples = bytearray()
    for frequency, duration in notes:
        count = int(sample_rate * duration)
        for index in range(count):
            if frequency == 0:
                value = 0
            else:
                envelope = min(1.0, index / 100, (count - index) / 180)
                phase = (index * frequency / sample_rate) % 1.0
                value = int(600 * envelope * (1 if phase < .5 else -1))
            samples.extend(struct.pack("<h", value))
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as output:
            path = output.name
        with wave.open(path, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            audio.writeframes(samples)
        if winsound:
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return True
        result = subprocess.run([player, path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired, wave.Error):
        return False
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def _select(options, question, *, default=0, input_stream=None, output_stream=None):
    """Compact inline choice control shared by the installation wizard."""
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    selected = max(0, min(default, len(options) - 1))
    def numbered():
        output_stream.write(question + "\n")
        for i, (_, label) in enumerate(options, 1):
            output_stream.write(f"  {i}. {label}\n")
        choice = input_stream.readline().strip()
        if not choice:
            return options[selected][0]
        try:
            index = int(choice) - 1
            if index < 0 or index >= len(options):
                raise ValueError
            return options[index][0]
        except ValueError as exc:
            raise ValueError("Selección inválida") from exc

    if not getattr(input_stream, "isatty", lambda: False)() or os.environ.get("TERM") == "dumb":
        return numbered()

    unicode_markers = True
    try:
        "●○↑↓".encode(getattr(output_stream, "encoding", None) or "utf-8")
    except (UnicodeEncodeError, LookupError):
        unicode_markers = False

    bindings = KeyBindings()

    def render() -> FormattedText:
        lines = [("class:question", question + "\n")]
        for index, (_, label) in enumerate(options):
            mark = index == selected
            marker = ("●" if mark else "○") if unicode_markers else ("[x]" if mark else "[ ]")
            style = "class:selected" if index == selected else "class:option"
            lines.append((style, f"  {marker} {label}\n"))
        hint = "Use ↑ ↓ to navigate and Enter to select." if unicode_markers else "Use arrows and Enter to select."
        lines.append(("class:hint", hint))
        return FormattedText(lines)

    @bindings.add("up")
    def move_up(event) -> None:
        nonlocal selected
        selected = (selected - 1) % len(options)

    @bindings.add("down")
    def move_down(event) -> None:
        nonlocal selected
        selected = (selected + 1) % len(options)

    @bindings.add("enter")
    def choose(event) -> None:
        event.app.exit(result=options[selected][0])

    @bindings.add("c-c")
    def cancel(event) -> None:
        event.app.exit(exception=KeyboardInterrupt)

    style = None
    if "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb":
        style = Style.from_dict({
            "question": "bold",
            "selected": "fg:ansicyan bold",
            "option": "fg:ansibrightblack",
            "hint": "italic fg:ansibrightblack",
        })
    control = FormattedTextControl(text=render, focusable=True)
    app = Application(
        layout=Layout(Window(control, wrap_lines=True)),
        key_bindings=bindings,
        style=style,
        full_screen=False,
        erase_when_done=False,
        mouse_support=False,
    )
    return app.run()


def select_choice(question, options, *, default=0, input_stream=None, output_stream=None):
    return _select(options, question, default=default, input_stream=input_stream, output_stream=output_stream)


def select_agent(input_stream=None, output_stream=None) -> str:
    installed = detect_agents()
    options = [(key, f"{label} ({'installed' if installed.get(key) else 'not installed'})") for key, label in AGENTS]
    return _select(options, "Select your AI coding agent:", input_stream=input_stream, output_stream=output_stream)


def detect_agents() -> dict[str, str | None]:
    """Return executable paths for supported agents; None means unavailable."""
    commands = {"codex": "codex", "claude": "claude", "gemini": "gemini", "copilot": "copilot"}
    return {key: shutil.which(command) for key, command in commands.items()}


def select_language(input_stream=None, output_stream=None) -> str:
    return select_choice("Idioma de trabajo / Working language:", [("es", "Español"), ("en", "English")], input_stream=input_stream, output_stream=output_stream)
