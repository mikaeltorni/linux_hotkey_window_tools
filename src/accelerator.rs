//! Friendly `modifier+key` specs to GTK accelerators.

use std::collections::HashSet;

use crate::logging;

const MODIFIER_ORDER: [&str; 4] = ["Control", "Alt", "Super", "Shift"];

fn canonical_modifier(token: &str) -> Option<&'static str> {
    match token.to_ascii_lowercase().as_str() {
        "ctrl" | "control" => Some("Control"),
        "alt" | "meta" => Some("Alt"),
        "super" | "win" | "windows" | "cmd" => Some("Super"),
        "shift" => Some("Shift"),
        _ => None,
    }
}

/// Convert a friendly `modifier+key` spec to a GTK accelerator string.
///
/// # Errors
/// Returns a message when the spec is empty, malformed, or names an unknown
/// modifier.
pub fn to_gnome_accelerator(spec: &str) -> Result<String, String> {
    let raw = spec.trim();
    if raw.is_empty() {
        return Err("empty hotkey specification".into());
    }
    let tokens: Vec<&str> = raw.split('+').map(str::trim).collect();
    if tokens.iter().any(|token| token.is_empty()) {
        return Err(format!("malformed hotkey {spec:?}: empty modifier or key"));
    }
    let (key, modifier_tokens) = tokens
        .split_last()
        .ok_or_else(|| format!("hotkey {spec:?} has no key"))?;
    if key.is_empty() {
        return Err(format!("hotkey {spec:?} has no key"));
    }
    let mut seen = HashSet::new();
    for token in modifier_tokens {
        let canonical = canonical_modifier(token)
            .ok_or_else(|| format!("unknown modifier {token:?} in hotkey {spec:?}"))?;
        seen.insert(canonical);
    }
    let prefix: String = MODIFIER_ORDER
        .iter()
        .filter(|name| seen.contains(*name))
        .map(|name| format!("<{name}>"))
        .collect();
    Ok(format!("{prefix}{key}"))
}

/// Reduce any accelerator spec to a comparable (modifiers, key) pair.
///
/// # Errors
/// Returns a message when the spec is empty, has no key, or names an unknown
/// modifier.
pub fn normalize_accelerator(text: &str) -> Result<(HashSet<String>, String), String> {
    let value = text.trim();
    if value.is_empty() {
        return Err("empty accelerator".into());
    }
    let mut modifiers = HashSet::new();
    let key = if value.contains('<') {
        let mut rest = String::new();
        let mut chars = value.chars().peekable();
        while let Some(ch) = chars.next() {
            if ch == '<' {
                let mut token = String::new();
                let mut closed = false;
                for inner in chars.by_ref() {
                    if inner == '>' {
                        closed = true;
                        break;
                    }
                    token.push(inner);
                }
                if !closed {
                    return Err(format!(
                        "unknown modifier {token:?} in accelerator {text:?}"
                    ));
                }
                let canonical = canonical_modifier(&token)
                    .ok_or_else(|| format!("unknown modifier {token:?} in accelerator {text:?}"))?;
                modifiers.insert(canonical.to_string());
            } else {
                rest.push(ch);
                rest.extend(chars);
                break;
            }
        }
        rest
    } else {
        let parts: Vec<&str> = value
            .split('+')
            .map(str::trim)
            .filter(|p| !p.is_empty())
            .collect();
        if parts.is_empty() {
            return Err(format!("accelerator {text:?} has no key"));
        }
        let (key, modifier_tokens) = parts.split_last().unwrap();
        for token in modifier_tokens {
            let canonical = canonical_modifier(token)
                .ok_or_else(|| format!("unknown modifier {token:?} in accelerator {text:?}"))?;
            modifiers.insert(canonical.to_string());
        }
        (*key).to_string()
    };
    if key.is_empty() {
        return Err(format!("accelerator {text:?} has no key"));
    }
    Ok((modifiers, key.to_ascii_lowercase()))
}

/// CLI: `accelerator <modifier+...+key>`.
pub fn run(args: &[String]) -> i32 {
    if args.len() != 1 {
        logging::error(format!("invalid accelerator usage: {args:?}"));
        eprintln!("Usage: hwt-tools accelerator <modifier+...+key>");
        return 2;
    }
    match to_gnome_accelerator(&args[0]) {
        Ok(accel) => {
            println!("{accel}");
            0
        }
        Err(error) => {
            logging::error(format!("could not convert hotkey: {error}"));
            eprintln!("Invalid hotkey: {error}");
            2
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn converts_friendly_specs() {
        assert_eq!(to_gnome_accelerator("control+t").unwrap(), "<Control>t");
        assert_eq!(to_gnome_accelerator("ctrl+t").unwrap(), "<Control>t");
        assert_eq!(to_gnome_accelerator("super+u").unwrap(), "<Super>u");
        assert_eq!(to_gnome_accelerator("win+u").unwrap(), "<Super>u");
        assert_eq!(
            to_gnome_accelerator("alt+super+w").unwrap(),
            "<Alt><Super>w"
        );
        assert_eq!(
            to_gnome_accelerator("super+alt+w").unwrap(),
            "<Alt><Super>w"
        );
        assert_eq!(
            to_gnome_accelerator("shift+control+a").unwrap(),
            "<Control><Shift>a"
        );
        assert_eq!(to_gnome_accelerator("Print").unwrap(), "Print");
        assert_eq!(to_gnome_accelerator("alt+F4").unwrap(), "<Alt>F4");
    }

    #[test]
    fn rejects_invalid_specs() {
        for spec in ["", "   ", "control+", "alt++t", "foo+t"] {
            assert!(to_gnome_accelerator(spec).is_err(), "{spec}");
        }
    }

    #[test]
    fn normalize_matches_across_form_order_and_case() {
        assert_eq!(
            normalize_accelerator("alt+super+E").unwrap(),
            normalize_accelerator("<Super><Alt>e").unwrap()
        );
        assert_eq!(
            normalize_accelerator("<Alt><Super>e").unwrap(),
            normalize_accelerator("alt+super+e").unwrap()
        );
    }

    #[test]
    fn normalize_distinguishes_and_rejects() {
        assert_ne!(
            normalize_accelerator("<Alt><Super>e").unwrap(),
            normalize_accelerator("<Alt><Super>w").unwrap()
        );
        assert!(normalize_accelerator("<Hyper>e").is_err());
    }
}
