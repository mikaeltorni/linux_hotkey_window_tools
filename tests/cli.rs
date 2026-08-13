//! CLI contracts for the former Python helpers.

use std::io::Write;
use std::process::{Command, Stdio};

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_hwt-tools"))
}

#[test]
fn accelerator_prints_gtk_form() {
    let out = bin().args(["accelerator", "alt+super+w"]).output().unwrap();
    assert!(out.status.success());
    assert_eq!(String::from_utf8_lossy(&out.stdout).trim(), "<Alt><Super>w");
}

#[test]
fn gsettings_strv_append_remove() {
    let added = bin()
        .args(["gsettings-strv", "append", "window-move-resize@local"])
        .env("CURRENT", "['a']")
        .output()
        .unwrap();
    assert!(added.status.success());
    assert!(String::from_utf8_lossy(&added.stdout).contains("window-move-resize@local"));

    let removed = bin()
        .args(["gsettings-strv", "remove", "window-move-resize@local"])
        .env("CURRENT", "['a', 'window-move-resize@local']")
        .output()
        .unwrap();
    assert_eq!(String::from_utf8_lossy(&removed.stdout).trim(), "['a']");
}

#[test]
fn conflicts_prints_matching_rows() {
    let mut child = bin()
        .args(["conflicts", "alt+super+e"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .as_mut()
        .unwrap()
        .write_all(b"activate-window-menu ['<Super><Alt>E']\nclose ['<Alt>F4']\n")
        .unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(out.status.success());
    assert_eq!(
        String::from_utf8_lossy(&out.stdout).trim(),
        "activate-window-menu\t<Super><Alt>E"
    );
}

#[test]
fn tiling_convert() {
    let out = bin()
        .args(["tiling", "convert", "<Super>t"])
        .output()
        .unwrap();
    assert!(out.status.success());
    assert_eq!(String::from_utf8_lossy(&out.stdout).trim(), "super+t");
}
