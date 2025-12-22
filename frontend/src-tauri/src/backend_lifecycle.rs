use crate::{cleanup_via_http, port_in_use, BackendProcess};
use std::fs;
use std::thread;
use std::time::{Duration, Instant};
use tauri::path::BaseDirectory;
use tauri::Manager;

/// Best-effort shutdown routine for the updater path. The goal is to release
/// the backend's port and file lock before the NSIS installer runs so updates
/// don't fail with "file in use" errors.
pub fn shutdown_backend_for_update(app_handle: &tauri::AppHandle) {
    log::info!("UPDATER_SHUTDOWN ► requested backend shutdown (update install)");
    shutdown_backend_inner(app_handle, true);
}

/// Best-effort shutdown routine for normal exits (window close, Ctrl+C). This
/// shares the same cleanup path as the updater but *does not* perform the
/// rename-based lock probe to avoid any chance of leaving the installed
/// backend exe in an unexpected name if a second rename were to fail.
pub fn shutdown_backend_for_exit(app_handle: &tauri::AppHandle) {
    log::info!("UPDATER_SHUTDOWN ► requested backend shutdown (normal exit)");
    shutdown_backend_inner(app_handle, false);
}

fn shutdown_backend_inner(app_handle: &tauri::AppHandle, check_file_lock: bool) {

    // 1) Ask the backend to perform its own cleanup (flush, close DBs, etc.).
    cleanup_via_http(1_500);

    // 2) Kill the child process we spawned, if any.
    {
        let backend = app_handle.state::<BackendProcess>();
        let mut guard = backend.0.lock().unwrap();
        if let Some(child) = guard.take() {
            log::info!("UPDATER_SHUTDOWN ► killing tracked backend child");
            let _ = child.kill();
        }
    }

    // 3) Wait for invariants: port must be free and (on Windows, update path)
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

        if check_file_lock && !backend_exe_unlocked(app_handle) {
            all_clear = false;
        }

        if all_clear {
            log::info!(
                "UPDATER_SHUTDOWN ► backend shutdown verified in {:?} (check_file_lock={})",
                elapsed,
                check_file_lock
            );
            break;
        }

        thread::sleep(Duration::from_millis(POLL_MS));
    }

    // 4) Best-effort cleanup of any legacy artifacts can be added here if needed.
}

#[cfg(windows)]
fn backend_exe_unlocked(app_handle: &tauri::AppHandle) -> bool {
    // Probe by attempting a rename‑and‑restore of the backend executable.
    // If either rename fails, we treat the file as still locked.
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

    let probe_path = path.with_extension("exe.__lockprobe__");

    // If the file doesn't exist yet, there's nothing to lock.
    if !path.exists() {
        return true;
    }

    match fs::rename(&path, &probe_path) {
        Ok(_) => {
            // Try to move it back; if this fails we still know the original
            // rename succeeded (i.e. the file wasn't locked).
            if let Err(err) = fs::rename(&probe_path, &path) {
                log::warn!(
                    "UPDATER_SHUTDOWN ► rename back from probe failed at {:?}: {}",
                    probe_path,
                    err
                );
            } else {
                log::debug!(
                    "UPDATER_SHUTDOWN ► backend exe appears rename‑unlocked at {:?}",
                    path
                );
            }
            true
        }
        Err(err) => {
            log::debug!(
                "UPDATER_SHUTDOWN ► backend exe still locked at {:?} (rename failed): {}",
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

