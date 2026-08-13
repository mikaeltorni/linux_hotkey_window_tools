//! Resolve and trigger the automatic-window-tiling Super+T hotkey.

use crate::logging;
use std::env;
use std::path::PathBuf;
use std::process::Command;

const DEFAULT_SORT_ACCELERATOR: &str = "<Super>t";
const AWT_EXTENSION_ID: &str = "automatic-window-tiling@local";
const AWT_SCHEMA: &str = "org.gnome.shell.extensions.automatic-window-tiling";
const AWT_KEY: &str = "tile-focused-application-windows";
const ENV_SORT_HOTKEY: &str = "OPEN_KITTY_SORT_HOTKEY";

fn schema_dir() -> PathBuf {
    dirs_home()
        .join(".local/share/gnome-shell/extensions")
        .join(AWT_EXTENSION_ID)
        .join("schemas")
}

fn dirs_home() -> PathBuf {
    env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn first_quoted_gsettings_value(raw: &str) -> String {
    let mut parts = raw.splitn(3, '\'');
    parts.next();
    parts.next().unwrap_or("").trim().to_string()
}

/// Return the GTK accelerator for the automatic-window-tiling sort action.
pub fn resolve_sort_accelerator() -> String {
    let override_accel = env::var(ENV_SORT_HOTKEY).unwrap_or_default();
    let override_accel = override_accel.trim();
    if !override_accel.is_empty() {
        return override_accel.to_string();
    }
    let schema_path = schema_dir();
    if schema_path.is_dir() {
        let output = Command::new("gsettings")
            .args([
                "--schemadir",
                &schema_path.to_string_lossy(),
                "get",
                AWT_SCHEMA,
                AWT_KEY,
            ])
            .output();
        if let Ok(output) = output {
            let raw = String::from_utf8_lossy(&output.stdout);
            let first = first_quoted_gsettings_value(raw.trim());
            if !first.is_empty() {
                return first;
            }
        } else {
            logging::warn("gsettings read failed");
        }
    }
    DEFAULT_SORT_ACCELERATOR.to_string()
}

/// Convert a GTK accelerator to an xdotool key spec.
pub fn gtk_to_xdotool(accelerator: &str) -> String {
    accelerator
        .replace("<Primary>", "ctrl+")
        .replace("<Control>", "ctrl+")
        .replace("<Alt>", "alt+")
        .replace("<Meta>", "alt+")
        .replace("<Super>", "super+")
        .replace("<Shift>", "shift+")
}

fn trigger() -> bool {
    let xdotool = match which("xdotool") {
        Some(path) => path,
        None => {
            logging::warn("xdotool not available; automatic window tiling skipped");
            return false;
        }
    };
    let accel = resolve_sort_accelerator();
    let spec = gtk_to_xdotool(&accel);
    let status = Command::new(xdotool)
        .args(["key", &spec])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
    match status {
        Ok(st) if st.success() => {
            logging::info(format!(
                "triggered automatic window tiling accel={accel} spec={spec}"
            ));
            true
        }
        _ => {
            logging::warn(format!("xdotool key rejected accel={accel} spec={spec}"));
            false
        }
    }
}

fn which(name: &str) -> Option<PathBuf> {
    env::var_os("PATH").and_then(|paths| {
        env::split_paths(&paths).find_map(|dir| {
            let candidate = dir.join(name);
            candidate.is_file().then_some(candidate)
        })
    })
}

/// CLI: `tiling resolve|xdotool-spec|convert <accel>|trigger`.
pub fn run(args: &[String]) -> i32 {
    if args.is_empty() {
        eprintln!("Usage: hwt-tools tiling resolve|xdotool-spec|convert <accel>|trigger");
        return 2;
    }
    match args[0].as_str() {
        "resolve" => {
            println!("{}", resolve_sort_accelerator());
            0
        }
        "xdotool-spec" => {
            println!("{}", gtk_to_xdotool(&resolve_sort_accelerator()));
            0
        }
        "convert" => {
            if args.len() != 2 {
                eprintln!("Usage: hwt-tools tiling convert <gtk-accelerator>");
                return 2;
            }
            println!("{}", gtk_to_xdotool(&args[1]));
            0
        }
        "trigger" => {
            if trigger() {
                0
            } else {
                1
            }
        }
        other => {
            eprintln!("Unknown command: {other}");
            2
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gtk_to_xdotool_normalizes_modifiers() {
        assert_eq!(gtk_to_xdotool("<Super>t"), "super+t");
        assert_eq!(gtk_to_xdotool("<Control><Alt>t"), "ctrl+alt+t");
    }

    #[test]
    fn first_quoted_extracts_first_entry() {
        assert_eq!(first_quoted_gsettings_value("['<Super>t']"), "<Super>t");
        assert_eq!(first_quoted_gsettings_value("[]"), "");
    }
}
