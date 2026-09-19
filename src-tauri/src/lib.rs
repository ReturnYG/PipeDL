pub mod api;
pub mod engine;
pub mod process;
pub mod store;

use fs2::FileExt;
use std::{
    fs::{File, OpenOptions},
    io::{Read, Write},
    path::PathBuf,
};
use store::{err, Result};

pub fn root_dir() -> Result<PathBuf> {
    if let Some(root) = std::env::var_os("PIPEDL_ROOT") {
        let p = PathBuf::from(root);
        if !p.is_absolute() {
            return Err("PIPEDL_ROOT must be absolute".into());
        }
        return Ok(p);
    }
    let profile = std::env::var("PIPEDL_PROFILE").unwrap_or_else(|_| "default".into());
    if profile.is_empty()
        || !profile
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return Err("Invalid PIPEDL_PROFILE".into());
    }
    let suffix = if profile == "default" {
        String::new()
    } else {
        format!("-{profile}")
    };
    Ok(dirs::data_local_dir()
        .ok_or("Cannot find local data directory")?
        .join(format!(
            "{}{suffix}",
            if cfg!(windows) { "PipeDL" } else { "pipedl" }
        )))
}
pub fn lock_and_token(root: &std::path::Path) -> Result<(File, String)> {
    let state = root.join(".pipedl");
    std::fs::create_dir_all(&state).map_err(err)?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(state.join("owner.lock"))
        .map_err(err)?;
    lock.try_lock_exclusive()
        .map_err(|_| "This data directory already has a queue owner".to_string())?;
    let path = state.join("api-token");
    let token = if path.exists() {
        let mut value = String::new();
        File::open(&path)
            .map_err(err)?
            .read_to_string(&mut value)
            .map_err(err)?;
        value.trim().to_string()
    } else {
        let token = format!(
            "{}{}",
            uuid::Uuid::new_v4().simple(),
            uuid::Uuid::new_v4().simple()
        );
        let mut opts = OpenOptions::new();
        opts.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            opts.mode(0o600);
        }
        let mut f = opts.open(&path).map_err(err)?;
        f.write_all(token.as_bytes()).map_err(err)?;
        f.sync_all().map_err(err)?;
        token
    };
    if token.len() < 32 || token.chars().any(char::is_whitespace) {
        return Err("Invalid API token file".into());
    }
    Ok((lock, token))
}
