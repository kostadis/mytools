//! Which file chooser Open and Save As use: the system file dialog, or the
//! built-in chooser drawn inside the editor's own window. Pure: no egui.

/// The `--chooser` command-line option.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum ChooserPreference {
    /// Decide from the environment.
    #[default]
    Auto,
    /// Always try the system file dialog first.
    System,
    /// Always use the built-in chooser.
    Window,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChooserKind {
    System,
    Window,
}

/// Why a chooser was picked, shown to the user so a wrong guess can be spotted.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChooserReason {
    Override,
    LocalDisplay,
    SshSession,
    NetworkDisplay,
    Uncertain,
}

impl ChooserReason {
    pub fn describe(self) -> &'static str {
        match self {
            Self::Override => "set with --chooser",
            Self::LocalDisplay => "local display",
            Self::SshSession => "SSH session detected",
            Self::NetworkDisplay => "network display detected",
            Self::Uncertain => "display could not be identified",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ChooserDecision {
    pub kind: ChooserKind,
    pub reason: ChooserReason,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Platform {
    /// Linux, and any other non-macOS target: decided from `DISPLAY` and
    /// `WAYLAND_DISPLAY`, and uncertain without them.
    Linux,
    MacOs,
}

impl Platform {
    pub fn current() -> Self {
        if cfg!(target_os = "macos") {
            Self::MacOs
        } else {
            Self::Linux
        }
    }
}

/// The environment detection reads, captured so tests can build it by hand.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DisplayEnv {
    pub ssh: bool,
    pub display: Option<String>,
    pub wayland_display: Option<String>,
    pub platform: Platform,
}

impl DisplayEnv {
    pub fn from_env() -> Self {
        Self::from_vars(|name| std::env::var_os(name))
    }

    fn from_vars(var: impl Fn(&str) -> Option<std::ffi::OsString>) -> Self {
        let set = |name: &str| var(name).is_some_and(|v| !v.is_empty());
        // A value that isn't UTF-8 can't be parsed, so it counts as unset,
        // which leads to the uncertain (built-in chooser) case.
        let text = |name: &str| var(name).and_then(|v| v.into_string().ok());
        Self {
            ssh: ["SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"]
                .into_iter()
                .any(set),
            display: text("DISPLAY"),
            wayland_display: text("WAYLAND_DISPLAY"),
            platform: Platform::current(),
        }
    }
}

/// Pick the chooser for one Open or Save As. The system dialog is used only
/// when the display is confidently local; any doubt means the built-in
/// chooser (constitution II.5, FR-010).
pub fn decide(env: &DisplayEnv, preference: ChooserPreference) -> ChooserDecision {
    let (kind, reason) = match preference {
        ChooserPreference::System => (ChooserKind::System, ChooserReason::Override),
        ChooserPreference::Window => (ChooserKind::Window, ChooserReason::Override),
        ChooserPreference::Auto => detect(env),
    };
    ChooserDecision { kind, reason }
}

fn detect(env: &DisplayEnv) -> (ChooserKind, ChooserReason) {
    let local = (ChooserKind::System, ChooserReason::LocalDisplay);
    if env.ssh {
        return (ChooserKind::Window, ChooserReason::SshSession);
    }
    if env.platform == Platform::MacOs {
        return local;
    }
    if env
        .wayland_display
        .as_deref()
        .is_some_and(|w| !w.is_empty())
    {
        return local;
    }
    match env.display.as_deref().and_then(display_is_local) {
        Some(true) => local,
        Some(false) => (ChooserKind::Window, ChooserReason::NetworkDisplay),
        None => (ChooserKind::Window, ChooserReason::Uncertain),
    }
}

/// `:0`, `:1.0` and `unix:0` are local sockets; `localhost:10.0` (what
/// `ssh -X` sets) and `host:0` go over the network. `None` if unparseable.
fn display_is_local(display: &str) -> Option<bool> {
    let (host, number) = display.rsplit_once(':')?;
    if !number.starts_with(|c: char| c.is_ascii_digit()) {
        return None;
    }
    Some(host.is_empty() || host == "unix")
}

#[cfg(test)]
mod tests {
    use super::*;
    use ChooserKind::{System, Window};
    use ChooserReason::*;

    fn linux(display: Option<&str>, wayland: Option<&str>) -> DisplayEnv {
        DisplayEnv {
            ssh: false,
            display: display.map(str::to_owned),
            wayland_display: wayland.map(str::to_owned),
            platform: Platform::Linux,
        }
    }

    fn auto(env: &DisplayEnv) -> (ChooserKind, ChooserReason) {
        let d = decide(env, ChooserPreference::Auto);
        (d.kind, d.reason)
    }

    #[test]
    fn the_command_line_option_wins() {
        let mut env = linux(Some(":0"), None);
        env.ssh = true;
        let system = decide(&env, ChooserPreference::System);
        assert_eq!((system.kind, system.reason), (System, Override));
        let env = linux(Some(":0"), None);
        let window = decide(&env, ChooserPreference::Window);
        assert_eq!((window.kind, window.reason), (Window, Override));
    }

    #[test]
    fn an_ssh_session_uses_the_built_in_chooser() {
        for (display, wayland) in [(Some(":0"), None), (None, Some("wayland-0")), (None, None)] {
            let mut env = linux(display, wayland);
            env.ssh = true;
            assert_eq!(auto(&env), (Window, SshSession));
        }
        let mut mac = linux(None, None);
        mac.platform = Platform::MacOs;
        mac.ssh = true;
        assert_eq!(auto(&mac), (Window, SshSession));
    }

    #[test]
    fn only_non_empty_ssh_variables_count() {
        let env = |name: &'static str, value: &'static str| {
            DisplayEnv::from_vars(move |n| (n == name).then(|| value.into()))
        };
        assert!(env("SSH_CONNECTION", "10.0.0.2 5 10.0.0.1 22").ssh);
        assert!(env("SSH_CLIENT", "10.0.0.2 5 22").ssh);
        assert!(env("SSH_TTY", "/dev/pts/3").ssh);
        assert!(!env("SSH_TTY", "").ssh);
        assert_eq!(env("DISPLAY", ":0").display.as_deref(), Some(":0"));
    }

    #[test]
    fn wayland_is_local() {
        assert_eq!(
            auto(&linux(None, Some("wayland-0"))),
            (System, LocalDisplay)
        );
        assert_eq!(
            auto(&linux(Some("localhost:10.0"), Some("wayland-0"))),
            (System, LocalDisplay)
        );
    }

    #[test]
    fn local_x_displays_use_the_system_dialog() {
        for display in [":0", ":1.0", "unix:0"] {
            assert_eq!(
                auto(&linux(Some(display), None)),
                (System, LocalDisplay),
                "{display}"
            );
        }
    }

    #[test]
    fn network_x_displays_use_the_built_in_chooser() {
        for display in ["localhost:10.0", "host:0", "10.0.0.5:0", "[::1]:0"] {
            assert_eq!(
                auto(&linux(Some(display), None)),
                (Window, NetworkDisplay),
                "{display}"
            );
        }
    }

    #[test]
    fn anything_unclear_uses_the_built_in_chooser() {
        for display in [None, Some(""), Some("garbage"), Some("host:"), Some(":x")] {
            assert_eq!(
                auto(&linux(display, None)),
                (Window, Uncertain),
                "{display:?}"
            );
        }
        assert_eq!(auto(&linux(None, Some(""))), (Window, Uncertain));
    }

    #[test]
    fn macos_without_ssh_is_local() {
        let mut mac = linux(None, None);
        mac.platform = Platform::MacOs;
        assert_eq!(auto(&mac), (System, LocalDisplay));
    }
}
