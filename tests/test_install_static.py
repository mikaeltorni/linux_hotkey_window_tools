"""Static checks for the component-framework installer wiring."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
COMPONENTS = ROOT / "installer" / "components.sh"
HOTKEY_TOOLS = ROOT / "lib" / "hotkey_tools.sh"
SCHEMA = ROOT / "schemas" / "org.gnome.shell.extensions.window-move-resize.gschema.xml"


def test_installer_loads_shared_component_framework():
    source = INSTALL.read_text(encoding="utf-8")
    assert "component_loader.sh" in source
    assert "isc_load_helpers" in source
    assert "isc_activate_components" in source
    assert 'source "$SCRIPT_DIR/installer/components.sh"' in source


def test_standalone_framework_bootstrap_supports_curl_or_wget():
    source = INSTALL.read_text(encoding="utf-8")
    assert "command -v curl" in source
    assert "command -v wget" in source
    assert "curl or wget is required" in source


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
    clear_idx = main_body.index("clear_component_hotkeys")
    component_idx = main_body.index("component_main")
    assert install_idx < clear_idx < component_idx


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
        "clear_component_hotkeys()",
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
