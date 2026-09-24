"""Static checks for the component-framework installer wiring."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
COMPONENTS = ROOT / "installer" / "components.sh"
HOTKEY_TOOLS = ROOT / "lib" / "hotkey_tools.sh"
SCHEMA = ROOT / "schemas" / "org.gnome.shell.extensions.window-move-resize.gschema.xml"
OPEN_KITTY_SORT_SCRIPT = ROOT / "scripts" / "open-kitty-and-sort.sh"
AUTOMATIC_WINDOW_TILING_SH = ROOT / "lib" / "automatic_window_tiling.sh"
HWT_TOOLS_SRC = ROOT / "src" / "main.rs"


def test_shell_wrapper_does_not_reimplement_unused_gtk_to_xdotool():
    """Callers use resolve/trigger; GTK conversion lives in hwt-tools."""
    source = AUTOMATIC_WINDOW_TILING_SH.read_text(encoding="utf-8")
    assert "gtk_to_xdotool()" not in source
    assert "resolve_sort_accel()" in source
    assert "trigger_automatic_window_tiling()" in source
    rust = HWT_TOOLS_SRC.read_text(encoding="utf-8")
    assert "tiling" in rust


def test_installer_loads_shared_component_framework():
    source = INSTALL.read_text(encoding="utf-8")
    assert "component_loader.sh" in source
    assert "isc_load_helpers" in source
    assert "isc_activate_components" in source
    assert 'source "$SCRIPT_DIR/installer/components.sh"' in source


def test_standalone_framework_bootstrap_clones_private_repository():
    source = INSTALL.read_text(encoding="utf-8")
    assert "GIT_TERMINAL_PROMPT=0 git clone" in source
    assert "ISC_FUNCTIONS_DIR=\"${__isc_framework_loader%/*}\"" in source
    assert "framework-${__isc_framework_key}" in source
    assert "raw.githubusercontent.com/mikaeltorni/linux_installation_scripts_functions" not in source


def test_installer_routes_through_component_main():
    source = INSTALL.read_text(encoding="utf-8")
    assert "component_main" in source


def test_listing_is_handled_before_core_install():
    # --list-components / --help must exit before main() installs the extension,
    # keeping listing side-effect free for the master installer.
    source = INSTALL.read_text(encoding="utf-8")
    list_idx = re.search(r"--list-components\|[^)]*\) component_main", source).start()
    main_call = re.search(r"^main \"\$@\"", source, re.MULTILINE)
    assert main_call is not None
    assert list_idx < main_call.start()


def test_listing_is_handled_before_target_user_initialization():
    # Component discovery is consumed by the master installer and must not
    # depend on SUDO_USER, a live desktop session, or gsettings availability.
    source = INSTALL.read_text(encoding="utf-8")
    list_idx = re.search(r"--list-components\|[^)]*\) component_main", source).start()
    main_call = re.search(r"^main \"\$@\"", source, re.MULTILINE)
    assert main_call is not None
    main_body = source[source.index("main() {"):main_call.start()]
    assert "initialize_target_user" in main_body
    assert list_idx < main_call.start()


def test_core_extension_install_is_unconditional():
    # The extension core installs in main() regardless of component selection so
    # the program is present no matter what the user chooses.
    source = INSTALL.read_text(encoding="utf-8")
    main_body = source[source.index("main() {"):]
    install_idx = main_body.index("install_extension_core")
    component_idx = main_body.index("component_main")
    assert install_idx < component_idx


def test_install_never_blanket_clears_component_bindings():
    # Regression: main() used to call a blanket clear_component_hotkeys before
    # component routing, so a narrower rerun (--select/--reconfigure of one
    # hotkey) wiped the accelerators of every other component and never
    # restored them. Install runs must only (re)write the bindings of the
    # components they name; removal is the framework's explicit uninstall path.
    install = INSTALL.read_text(encoding="utf-8")
    hotkey_tools = HOTKEY_TOOLS.read_text(encoding="utf-8")
    assert "clear_component_hotkeys" not in install
    assert "clear_component_hotkeys" not in hotkey_tools


def test_schema_defaults_do_not_bind_optional_components():
    # Optional hotkeys must be installed only by selected components. Schema
    # defaults stay empty so a core-only install has no implicit accelerators.
    source = SCHEMA.read_text(encoding="utf-8")
    assert "<key name=\"drag-active-window-with-pointer\" type=\"as\">\n      <default>[]</default>" in source
    assert "<key name=\"scale-active-window-from-center\" type=\"as\">\n      <default>[]</default>" in source


def test_components_manifest_declares_both_hotkeys_default_on():
    source = COMPONENTS.read_text(encoding="utf-8")
    assert 'ISC_REPO_NAME="linux_hotkey_window_tools"' in source
    assert re.search(r"^\s*\"move_hotkey\|[^|]+\|on\|configure_move_hotkey(\||\")", source, re.MULTILINE)
    assert re.search(r"^\s*\"resize_hotkey\|[^|]+\|on\|configure_resize_hotkey(\||\")", source, re.MULTILINE)


def test_hotkey_library_defines_core_and_component_functions():
    source = HOTKEY_TOOLS.read_text(encoding="utf-8")
    for fn in (
        "install_extension_core()",
        "configure_move_hotkey()",
        "configure_resize_hotkey()",
        "release_conflicting_bindings()",
        "resolve_hotkey_spec()",
    ):
        assert fn in source


def test_hotkeys_are_customizable_via_environment():
    source = HOTKEY_TOOLS.read_text(encoding="utf-8")
    assert "MOVE_HOTKEY" in source
    assert "RESIZE_HOTKEY" in source


def test_open_kitty_sort_component_is_declared_default_on():
    source = COMPONENTS.read_text(encoding="utf-8")
    assert re.search(
        r'^\s*"open_kitty_sort_hotkey\|[^|]+\|on\|configure_open_kitty_sort_hotkey(\||")',
        source,
        re.MULTILINE,
    )


def test_hotkey_library_defines_open_kitty_sort_functions():
    source = HOTKEY_TOOLS.read_text(encoding="utf-8")
    for fn in (
        "install_open_kitty_sort_script()",
        "configure_open_kitty_sort_hotkey()",
        "detect_open_kitty_sort_hotkey()",
        "uninstall_open_kitty_sort_hotkey()",
        "hwt_clear_custom_keybinding()",
    ):
        assert fn in source
    assert "hwt-tools" in source
    assert "python3" not in source


def test_open_kitty_sort_is_customizable_via_environment():
    source = HOTKEY_TOOLS.read_text(encoding="utf-8")
    assert "OPEN_KITTY_SORT_HOTKEY" in source


def test_open_kitty_sort_script_is_valid_bash_and_present():
    assert OPEN_KITTY_SORT_SCRIPT.is_file(), "open-kitty-and-sort.sh missing"
    assert AUTOMATIC_WINDOW_TILING_SH.is_file(), "automatic_window_tiling.sh missing"
    assert HWT_TOOLS_SRC.is_file(), "hwt-tools Rust source missing"
    source = OPEN_KITTY_SORT_SCRIPT.read_text(encoding="utf-8")
    assert "kitty" in source
    assert "xdotool" in source
    assert "OPEN_KITTY_SORT_DELAY" in source
    assert "automatic_window_tiling.sh" in source
    assert "trigger_automatic_window_tiling" in source
    result = subprocess.run(
        ["bash", "-n", str(OPEN_KITTY_SORT_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_open_kitty_sort_uses_custom_keybinding_not_schema():
    # The launch-kitty-and-sort hotkey is a GNOME custom keybinding, not a key on
    # this extension's schema, so it needs no GNOME Shell reload and the schema
    # stays limited to the pointer move/resize keys.
    schema = SCHEMA.read_text(encoding="utf-8")
    assert "open-kitty-sort" not in schema
    assert "open_kitty_sort" not in schema
    source = HOTKEY_TOOLS.read_text(encoding="utf-8")
    assert "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding" in source
    assert "/custom-keybindings/open-kitty-sort/" in source


def test_uninstall_open_kitty_sort_clears_custom_keybinding():
    # The custom keybinding is removed only by the component's own uninstall
    # function, never by a blanket clear during install.
    source = HOTKEY_TOOLS.read_text(encoding="utf-8")
    start = source.index("uninstall_open_kitty_sort_hotkey() {")
    body = source[start : start + 400]
    assert "hwt_clear_custom_keybinding" in body


def test_move_resize_uninstall_functions_clear_their_own_keys():
    source = HOTKEY_TOOLS.read_text(encoding="utf-8")
    assert re.search(
        r'uninstall_move_hotkey\(\).*hwt_clear_key "drag-active-window-with-pointer"', source
    )
    assert re.search(
        r'uninstall_resize_hotkey\(\).*hwt_clear_key "scale-active-window-from-center"', source
    )


def test_detect_routing_has_target_user_context():
    # --detect / --uninstall bypass main()/initialize_target_user(), so install.sh
    # must derive a best-effort TARGET_USER before that routing, or detect would
    # falsely report every component as absent.
    source = INSTALL.read_text(encoding="utf-8")
    ctx = re.search(r': "\$\{TARGET_USER:=', source)
    assert ctx is not None, "target-user default missing before detect routing"
    case = re.search(r"--list-components\|[^)]*\) component_main", source)
    assert case is not None
    assert ctx.start() < case.start()
