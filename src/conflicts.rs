//! Find GNOME default bindings that shadow a chosen hotkey.

use std::io::{self, Read};

use crate::accelerator::normalize_accelerator;
use crate::gsettings_strv::parse_strv;
use crate::logging;

/// Yield `(key, stored)` pairs whose accelerator matches `target`.
pub fn iter_conflicts(
    lines: &[String],
    target: &(std::collections::HashSet<String>, String),
) -> Vec<(String, String)> {
    let mut out = Vec::new();
    for line in lines {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Some((key, raw_value)) = line.split_once(' ') else {
            continue;
        };
        if key.is_empty() || raw_value.is_empty() {
            continue;
        }
        for stored in parse_strv(Some(raw_value)) {
            match normalize_accelerator(&stored) {
                Ok(normalized) if &normalized == target => {
                    logging::debug(format!("conflict on key {key}: stored {stored}"));
                    out.push((key.to_string(), stored));
                }
                Ok(_) => {}
                Err(_) => {
                    logging::debug(format!("skipping unparsable stored accelerator {stored}"))
                }
            }
        }
    }
    out
}

/// CLI: `conflicts <target>` reading list-recursively rows (schema stripped) on stdin.
pub fn run_conflicts(args: &[String]) -> i32 {
    if args.len() != 1 {
        logging::error(format!("invalid conflict_finder usage: {args:?}"));
        eprintln!("Usage: hwt-tools conflicts <target-accelerator>");
        return 2;
    }
    let target = match normalize_accelerator(&args[0]) {
        Ok(t) => t,
        Err(error) => {
            logging::error(format!("invalid target accelerator: {error}"));
            eprintln!("Invalid accelerator: {error}");
            return 2;
        }
    };
    let mut stdin = String::new();
    let _ = io::stdin().read_to_string(&mut stdin);
    let lines: Vec<String> = stdin.lines().map(str::to_string).collect();
    for (key, stored) in iter_conflicts(&lines, &target) {
        println!("{key}\t{stored}");
    }
    0
}

/// CLI: `conflict-candidates` reading full `schema key value` rows on stdin.
pub fn run_candidates() -> i32 {
    let mut stdin = String::new();
    let _ = io::stdin().read_to_string(&mut stdin);
    for line in stdin.lines() {
        let line = line.trim_end();
        if line.is_empty() {
            continue;
        }
        let mut parts = line.splitn(3, ' ');
        let Some(schema) = parts.next() else { continue };
        let Some(key) = parts.next() else { continue };
        let Some(raw) = parts.next() else { continue };
        for accel in parse_strv(Some(raw)) {
            if !accel.is_empty() {
                println!("{schema} {key}\t{accel}");
            }
        }
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::accelerator::normalize_accelerator;

    #[test]
    fn finds_conflict_regardless_of_order_and_case() {
        let rows = vec![
            "toggle-maximized ['<Alt>F10']".into(),
            "activate-window-menu ['<Super><Alt>E']".into(),
            "switch-to-workspace-left ['<Super>Page_Up', '<Control><Alt>Left']".into(),
        ];
        let target = normalize_accelerator("alt+super+e").unwrap();
        assert_eq!(
            iter_conflicts(&rows, &target),
            vec![("activate-window-menu".into(), "<Super><Alt>E".into())]
        );
    }

    #[test]
    fn returns_each_matching_array_element() {
        let rows = vec!["some-key ['<Alt><Super>w', '<Super><Alt>W']".into()];
        let target = normalize_accelerator("alt+super+w").unwrap();
        assert_eq!(
            iter_conflicts(&rows, &target),
            vec![
                ("some-key".into(), "<Alt><Super>w".into()),
                ("some-key".into(), "<Super><Alt>W".into()),
            ]
        );
    }
}
