"""Interactive installation experience for KatalIArc."""
import os
import shutil
import sys
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

                         desarrollado por MrNeo44 (Diego Gatica)"""


def render_banner(stream=None, *, enabled: bool = True) -> None:
    stream = stream or sys.stdout
    if not enabled:
        return
    try:
        BANNER.encode(getattr(stream, "encoding", None) or "utf-8")
        stream.write(BANNER + "\n\n")
    except (UnicodeEncodeError, LookupError):
        stream.write("KATALIARC\n\n")


def _select(options, question, *, default=0, multiple=False, input_stream=None, output_stream=None):
    """Compact inline choice control shared by the installation wizard."""
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    selected = max(0, min(default, len(options) - 1))
    checked = set()

    def numbered():
        output_stream.write(question + "\n")
        for i, (_, label) in enumerate(options, 1):
            output_stream.write(f"  {i}. {label}\n")
        choice = input_stream.readline().strip()
        if not choice:
            return [options[i][0] for i in sorted(checked)] if multiple else options[selected][0]
        try:
            indices = [int(part.strip()) - 1 for part in choice.split(",")]
            if any(i < 0 or i >= len(options) for i in indices):
                raise ValueError
            return [options[i][0] for i in indices] if multiple else options[indices[0]][0]
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
            mark = index in checked if multiple else index == selected
            marker = ("●" if mark else "○") if unicode_markers else ("[x]" if mark else "[ ]")
            style = "class:selected" if index == selected else "class:option"
            lines.append((style, f"  {marker} {label}\n"))
        hint = ("Use ↑ ↓ to move, Space to toggle, Enter to continue." if multiple else "Use ↑ ↓ to navigate and Enter to select.") if unicode_markers else ("Use arrows, Space, and Enter." if multiple else "Use arrows and Enter to select.")
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

    @bindings.add("space")
    def toggle(event) -> None:
        if multiple:
            if selected in checked:
                checked.remove(selected)
            else:
                checked.add(selected)

    @bindings.add("enter")
    def choose(event) -> None:
        event.app.exit(result=[options[i][0] for i in sorted(checked)] if multiple else options[selected][0])

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


def select_choices(question, options, *, input_stream=None, output_stream=None):
    return _select(options, question, multiple=True, input_stream=input_stream, output_stream=output_stream)


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
