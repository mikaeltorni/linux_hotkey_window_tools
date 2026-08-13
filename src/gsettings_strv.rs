//! GSettings string-array helpers.

use std::collections::HashSet;
use std::env;

use crate::logging;

/// Parse `gsettings get` string-array output into normalized values.
pub fn parse_strv(raw: Option<&str>) -> Vec<String> {
    let mut value = raw.unwrap_or("").trim().to_string();
    if let Some(rest) = value.strip_prefix("@as ") {
        value = rest.trim().to_string();
    }
    if value.is_empty() {
        return Vec::new();
    }
    match pythonish_list(&value) {
        Some(items) => items,
        None => {
            logging::warn(format!("could not parse gsettings array: {raw:?}"));
            Vec::new()
        }
    }
}

fn pythonish_list(value: &str) -> Option<Vec<String>> {
    let value = value.trim();
    if !value.starts_with('[') || !value.ends_with(']') {
        return None;
    }
    let inner = value[1..value.len() - 1].trim();
    if inner.is_empty() {
        return Some(Vec::new());
    }

    let mut items = Vec::new();
    let mut chars = inner.chars().peekable();
    while let Some(&ch) = chars.peek() {
        if ch.is_whitespace() || ch == ',' {
            chars.next();
            continue;
        }
        let quote = chars.next()?;
        if quote != '\'' && quote != '"' {
            return None;
        }
        let mut out = String::new();
        let mut closed = false;
        while let Some(c) = chars.next() {
            if c == '\\' {
                let escaped = chars.next()?;
                out.push(escaped);
                continue;
            }
            if c == quote {
                closed = true;
                break;
            }
            out.push(c);
        }
        if !closed {
            return None;
        }
        items.push(out);
    }
    Some(items)
}

/// De-duplicate while preserving first appearance.
pub fn unique_values(values: Vec<String>) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for v in values {
        if seen.insert(v.clone()) {
            out.push(v);
        }
    }
    out
}

/// Append `value` when non-empty and not already present.
pub fn append_strv(raw: Option<&str>, value: &str) -> Vec<String> {
    let mut current = unique_values(parse_strv(raw));
    if !value.is_empty() && !current.iter().any(|item| item == value) {
        current.push(value.to_string());
    }
    current
}

/// Remove every occurrence of `value`.
pub fn remove_strv(raw: Option<&str>, value: &str) -> Vec<String> {
    parse_strv(raw)
        .into_iter()
        .filter(|item| item != value)
        .collect()
}

/// Serialize values for `gsettings set` (Python `repr` style single quotes).
pub fn format_strv(values: &[String]) -> String {
    let parts: Vec<String> = values
        .iter()
        .map(|item| format!("'{}'", item.replace('\\', "\\\\").replace('\'', "\\'")))
        .collect();
    format!("[{}]", parts.join(", "))
}

/// CLI: `gsettings-strv append|remove <value>` reading `CURRENT`.
pub fn run(args: &[String]) -> i32 {
    if args.len() != 2 || (args[0] != "append" && args[0] != "remove") {
        logging::error("Usage: hwt-tools gsettings-strv append|remove <value>");
        eprintln!("Usage: hwt-tools gsettings-strv append|remove <value>");
        return 2;
    }
    let action = &args[0];
    let value = &args[1];
    let current = env::var("CURRENT").unwrap_or_default();
    logging::info(format!(
        "applying {action} for gsettings strv value {value}"
    ));
    let result = if action == "append" {
        append_strv(Some(&current), value)
    } else {
        remove_strv(Some(&current), value)
    };
    println!("{}", format_strv(&result));
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn append_and_remove() {
        assert_eq!(
            append_strv(Some("['a']"), "b"),
            vec!["a".to_string(), "b".to_string()]
        );
        assert_eq!(remove_strv(Some("['a', 'b']"), "a"), vec!["b".to_string()]);
    }
}
