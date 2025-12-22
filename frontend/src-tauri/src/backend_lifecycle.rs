use crate::{
    cleanup_via_http, kill_by_pid, pid_alive, port_in_use, read_pid, remove_pid_file,
    BackendProcess,
};
use std::fs::OpenOptions;
use std::thread;
use std::time::{Duration, Instant};
use tauri::path::BaseDirectory;

/// Best-effort shutdown routine used by both the updater and normal window
/// closes. The goal is to release the backend's port and file lock before the
/// NSIS installer runs so updates don't fail with "file in use" errors.
pub fn shutdown_backend_for_update(app_handle: &tauri::AppHandle) {
    log::info!("UPDATER_SHUTDOWN ► requested backend shutdown");

    // 1) Ask the backend to perform its own cleanup (flush, close DBs, etc.).
    cleanup_via_http(1_500);

    // 2) Kill the child process we spawned, if any.
    {
        let backend = app_handle.state::<BackendProcess>();
        if let Some(mut child) = backend.0.lock().unwrap().take() {
            log::info!("UPDATER_SHUTDOWN ► killing tracked backend child");
            let _ = child.kill();
        }
    }

    // 3) Extra belt-and-suspenders: if the backend wrote a PID file, try to
    //    ensure that process is gone as well.
    if let Some(pid) = read_pid() {
        if pid_alive(pid) {
            log::info!("UPDATER_SHUTDOWN ► killing backend pid from pidfile: {}", pid);
            kill_by_pid(pid);
        }
    }

    // 4) Wait for invariants: port must be free and (on Windows) the backend
    //    binary should be unlocked for overwrite.
    const TIMEOUT_MS: u64 = 10_000;
    const POLL_MS: u64 = 250;
    let start = Instant::now();

    loop {
        let elapsed = start.elapsed();
        if elapsed.as_millis() as u64 >= TIMEOUT_MS {
            log::warn!(
                "UPDATER_SHUTDOWN ► timeout ({:?}) waiting for backend shutdown; proceeding anyway",
                elapsed
            );
            break;
        }

        let mut all_clear = true;

        if port_in_use(8000) {
            all_clear = false;
            log::debug!("UPDATER_SHUTDOWN ► port 8000 still in use; waiting…");
        }

        if !backend_exe_unlocked(app_handle) {
            all_clear = false;
        }

        if all_clear {
            log::info!(
                "UPDATER_SHUTDOWN ► backend shutdown verified in {:?}",
                elapsed
            );
            break;
        }

        thread::sleep(Duration::from_millis(POLL_MS));
    }

    // 5) Clean up pidfile; not strictly required but avoids stale diagnostics.
    remove_pid_file();
}

#[cfg(windows)]
fn backend_exe_unlocked(app_handle: &tauri::AppHandle) -> bool {
    // Try to open the backend binary in the AppLocalData directory for write.
    // If this succeeds, NSIS should be able to overwrite it.
    let path = match app_handle
        .path()
        .resolve("plattera-backend.exe", BaseDirectory::AppLocalData)
    {
        Ok(p) => p,
        Err(e) => {
            log::debug!(
                "UPDATER_SHUTDOWN ► could not resolve backend exe path: {}",
                e
            );
            return true;
        }
    };

    match OpenOptions::new().write(true).open(&path) {
        Ok(_) => {
            log::debug!(
                "UPDATER_SHUTDOWN ► backend exe appears unlocked at {:?}",
                path
            );
            true
        }
        Err(err) => {
            log::debug!(
                "UPDATER_SHUTDOWN ► backend exe still locked at {:?}: {}",
                path,
                err
            );
            false
        }
    }
}

#[cfg(not(windows))]
fn backend_exe_unlocked(_app_handle: &tauri::AppHandle) -> bool {
    // On non-Windows platforms we don't currently probe the filesystem lock;
    // rely on process + port checks only.
    true
}

