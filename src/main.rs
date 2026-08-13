//! `hwt-tools` — installer and runtime helpers for window-move-resize.
//!
//! ```text
//! hwt-tools gsettings-strv append|remove <value>
//! hwt-tools accelerator <modifier+...+key>
//! hwt-tools conflicts <target-accelerator>
//! hwt-tools conflict-candidates
//! hwt-tools tiling resolve|xdotool-spec|convert <accel>|trigger
//! ```

mod accelerator;
mod conflicts;
mod gsettings_strv;
mod logging;
mod tiling;

fn main() {
    let mut args = std::env::args().skip(1);
    let Some(cmd) = args.next() else {
        eprintln!(
            "Usage: hwt-tools gsettings-strv|accelerator|conflicts|conflict-candidates|tiling ..."
        );
        std::process::exit(2);
    };
    let rest: Vec<String> = args.collect();
    let code = match cmd.as_str() {
        "gsettings-strv" => gsettings_strv::run(&rest),
        "accelerator" => accelerator::run(&rest),
        "conflicts" => conflicts::run_conflicts(&rest),
        "conflict-candidates" => conflicts::run_candidates(),
        "tiling" => tiling::run(&rest),
        _ => {
            eprintln!("Unknown command: {cmd}");
            2
        }
    };
    std::process::exit(code);
}
