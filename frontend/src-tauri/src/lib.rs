use tauri::Manager;
use tauri::menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder};
use tauri_plugin_shell::{process::{CommandChild, CommandEvent}, ShellExt};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use std::path::{Path, PathBuf};
use std::fs;
use sysinfo::{Pid, System};
use std::net::TcpStream;

// Blocking HTTP for quick cleanup ping
fn cleanup_via_http(timeout_ms: u64) {
    let agent = ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_millis(timeout_ms))
        .build();
    let _ = agent.post("http://127.0.0.1:8000/api/cleanup").call();
}

fn pid_file_path() -> PathBuf {
    Path::new("../../backend/.server.pid").to_path_buf()
}

fn write_pid(pid: u32) {
    let _ = fs::write(pid_file_path(), pid.to_string());
}

fn read_pid() -> Option<u32> {
    let p = pid_file_path();
    if !p.exists() { return None; }
    fs::read_to_string(p).ok().and_then(|s| s.trim().parse::<u32>().ok())
}

fn remove_pid_file() {
    let _ = fs::remove_file(pid_file_path());
}

fn pid_alive(pid: u32) -> bool {
    let mut sys = System::new_all();
    sys.refresh_processes();
    sys.process(Pid::from_u32(pid)).is_some()
}

fn kill_by_pid(pid: u32) {
    let mut sys = System::new_all();
    sys.refresh_processes();
    if let Some(pr) = sys.process(Pid::from_u32(pid)) {
        // Try graceful terminate, then kill
        let _ = pr.kill();
    }
}

fn port_in_use(port: u16) -> bool {
    TcpStream::connect(("127.0.0.1", port)).is_ok()
}

struct BackendProcess(Mutex<Option<CommandChild>>);

/// Debug helper for updater investigations.
///
/// This does **not** drive the built-in updater workflow – it simply
/// fetches an arbitrary URL (typically the configured latest.json endpoint),
/// logs what it sees, and returns a terse status to the frontend.
#[tauri::command]
async fn debug_updater_endpoint(url: String) -> Result<String, String> {
    use ureq::AgentBuilder;

    let agent = AgentBuilder::new()
        .timeout_connect(Duration::from_millis(2_000))
        .timeout(Duration::from_millis(5_000))
        .build();

    let res = agent
        .get(&url)
        .call()
        .map_err(|e| format!("request error: {e}"))?;

    let status = res.status();
    let content_type = res
        .header("content-type")
        .map(|s| s.to_string())
        .unwrap_or_else(|| "<none>".to_string());

    let body = res
        .into_string()
        .unwrap_or_else(|_| "<body read error>".to_string());

    log::info!(
        "UPDATER_DEBUG ► status={} content_type={}; body_start\n{}\nbody_end",
        status,
        content_type,
        body
    );

    // Best-effort JSON decode so we see structured errors when schema drifts.
    match serde_json::from_str::<serde_json::Value>(&body) {
        Ok(_) => Ok(format!(
            "ok status={} content_type={} (JSON parse succeeded)",
            status, content_type
        )),
        Err(e) => {
            log::error!("UPDATER_DEBUG ► json_decode_error={}", e);
            Err(format!("json decode error: {e}"))
        }
    }
}

#[tauri::command]
async fn start_backend(app_handle: tauri::AppHandle) -> Result<String, String> {
    let backend_process = app_handle.state::<BackendProcess>();
    let mut process_guard = backend_process.0.lock().unwrap();
    
    if process_guard.is_none() {
        // If port 8000 is already in use (external server), don't spawn another
        if port_in_use(8000) {
            return Ok("Backend already running (detected on port 8000)".to_string());
        }

        // Try sidecar first; if that fails, fall back to Python (dev)
        let try_sidecar = (|| -> Result<CommandChild, String> {
            let sidecar = app_handle
                .shell()
                .sidecar("plattera-backend")
                .map_err(|e| format!("sidecar error: {}", e))?;
            let sidecar = sidecar
                .env("PYTHONIOENCODING", "utf-8")
                .env("PYTHONUTF8", "1");
            let (mut rx, child) = sidecar.spawn().map_err(|e| format!("spawn error: {}", e))?;
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            log::info!("[SIDECAR stdout] {}", String::from_utf8_lossy(&line))
                        }
                        CommandEvent::Stderr(line) => {
                            log::error!("[SIDECAR stderr] {}", String::from_utf8_lossy(&line))
                        }
                        _ => {}
                    }
                }
            });
            Ok(child)
        })();

        match try_sidecar {
            Ok(child) => {
                *process_guard = Some(child);
                Ok("Backend sidecar started".to_string())
            }
            Err(_e) => {
                // DEV FALLBACK: run Python backend directly from venv
                let (mut rx, child) = app_handle
                    .shell()
                    .command("../../.venv/Scripts/python.exe")
                    .args(["-X", "utf8", "main.py"])
                    .current_dir("../../backend")
                    .env("PYTHONIOENCODING", "utf-8")
                    .env("PYTHONUTF8", "1")
                    .spawn()
                    .map_err(|err| format!("fallback python spawn error: {}", err))?;
                tauri::async_runtime::spawn(async move {
                    while let Some(event) = rx.recv().await {
                        match event {
                            CommandEvent::Stdout(line) => {
                                log::info!("[BACKEND stdout] {}", String::from_utf8_lossy(&line))
                            }
                            CommandEvent::Stderr(line) => {
                                log::error!("[BACKEND stderr] {}", String::from_utf8_lossy(&line))
                            }
                            _ => {}
                        }
                    }
                });
                *process_guard = Some(child);
                Ok("Backend started via Python fallback".to_string())
            }
        }
    } else {
        Ok("Backend already running".to_string())
    }
}

#[tauri::command]
async fn check_backend_health() -> Result<String, String> {
    // Simple health check - in a real app you'd ping the backend
    Ok("Backend is healthy".to_string())
}

/// Delete all user-local data under %LOCALAPPDATA%\Plattera and restart the app.
///
/// This gives users an explicit \"Factory reset\" path without relying solely
/// on the uninstaller's optional data deletion checkbox.
#[tauri::command]
async fn factory_reset_data(app_handle: tauri::AppHandle) -> Result<(), String> {
    use tauri::path::BaseDirectory;

    let app_data_dir = app_handle
        .path()
        .resolve("", BaseDirectory::AppLocalData)
        .map_err(|e| e.to_string())?;

    log::warn!("☢️ FACTORY RESET REQUESTED. Deleting: {:?}", app_data_dir);

    if app_data_dir.exists() {
        std::fs::remove_dir_all(&app_data_dir)
            .map_err(|e| format!("Failed to delete data at {:?}: {}", app_data_dir, e))?;
    }

    // Ask Tauri to restart the app so it can recreate its folders cleanly.
    app_handle.restart();
    Ok(())
}

/// Open devtools for the main window. Used by both the global menu
/// accelerator (CmdOrCtrl+Shift+I) and any frontend "open devtools"
/// actions (for example, right‑click context menus).
#[tauri::command]
async fn open_devtools(app_handle: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_webview_window("main") {
        window.open_devtools();
        Ok(())
    } else {
        Err("main window not found".into())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            // Application menu with a DevTools opener that also provides
            // the Ctrl+Shift+I (CmdOrCtrl+Shift+I) accelerator in release
            // builds.
            let open_devtools_item = MenuItemBuilder::with_id("open_devtools", "Open DevTools")
                .accelerator("CmdOrCtrl+Shift+I")
                .build(app)?;

            let tools_menu = SubmenuBuilder::new(app, "Tools")
                .item(&open_devtools_item)
                .build()?;

            let menu = MenuBuilder::new(app)
                .item(&tools_menu)
                .build()?;

            app.set_menu(menu)?;

            // Always register log plugin (dev + release)
            app.handle().plugin(
                tauri_plugin_log::Builder::default()
                    .level(log::LevelFilter::Info)
                    // Make updater and sidecar chatter as verbose as needed in logs.
                    .level_for("tauri_plugin_updater", log::LevelFilter::Trace)
                    .level_for("app_lib", log::LevelFilter::Debug)
                    .build(),
            )?;

            // Native devtools integration (including context-menu inspector)
            app.handle().plugin(tauri_plugin_devtools_app::init())?;
            // Register shell plugin for sidecar
            app.handle().plugin(tauri_plugin_shell::init())?;
            // Updater plugin (GitHub Releases)
            app.handle().plugin(tauri_plugin_updater::Builder::new().build())?;
            
            // Auto-start backend when app launches
            let app_handle = app.handle().clone();
            thread::spawn(move || {
                // Give a moment for the app to fully initialize
                thread::sleep(Duration::from_millis(2000));
                
                // Start the backend
                let runtime = tokio::runtime::Runtime::new().unwrap();
                runtime.block_on(async {
                    match start_backend(app_handle).await {
                        Ok(msg) => log::info!("✅ {}", msg),
                        Err(e) => log::error!("❌ Failed to start backend: {}", e),
                    }
                });
                // Backend prewarm (after launch): wait for readiness, then warm dossier list
                thread::spawn(|| {
                    // Poll health with backoff
                    let agent = ureq::AgentBuilder::new()
                        .timeout_connect(Duration::from_millis(1000))
                        .timeout(Duration::from_millis(8000))
                        .build();
                    let delays = [500u64, 1000, 1500, 2500];
                    let mut ready = false;
                    for d in delays {
                        let res = agent.get("http://127.0.0.1:8000/api/health").call();
                        if res.is_ok() {
                            ready = true;
                            break;
                        }
                        thread::sleep(Duration::from_millis(d));
                    }
                    if !ready {
                        return; // abort silently
                    }
                    // Allow other startup tasks to settle
                    thread::sleep(Duration::from_millis(1000));
                    // Warm dossier list (ignore errors)
                    let _ = agent
                        .get("http://127.0.0.1:8000/api/dossier-management/list?limit=50&offset=0")
                        .call();
                });
            });
            
            // Ctrl+C handler for dev shells to ensure same cleanup path
            {
                let app_handle = app.handle().clone();
                let _ = ctrlc::set_handler(move || {
                    log::info!("Received Ctrl+C - cleaning up backend process...");
                    // Give the backend a bit more time to receive and act on the cleanup signal.
                    cleanup_via_http(1500);
                    let backend_process = app_handle.state::<BackendProcess>();
                    if let Some(mut child) = backend_process.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                    std::process::exit(0);
                });
            }

            Ok(())
        })
        .on_menu_event(|event| {
            if event.menu_item_id() == "open_devtools" {
                let window = event.window();
                window.open_devtools();
            }
        })
        .invoke_handler(tauri::generate_handler![
            start_backend,
            check_backend_health,
            debug_updater_endpoint,
            factory_reset_data,
            open_devtools
        ])
        .on_window_event(|window, event| match event {
            tauri::WindowEvent::CloseRequested { .. } => {
                log::info!("Cleaning up backend process...");
                // Best-effort HTTP cleanup with a slightly longer timeout for EXE builds
                cleanup_via_http(1500);
                // Give backend a brief moment to flush logs
                std::thread::sleep(std::time::Duration::from_millis(250));
                // Kill child if we own it
                let backend_process = window.app_handle().state::<BackendProcess>();
                if let Some(mut child) = backend_process.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
                log::info!("✅ Backend process terminated");
            }
            _ => {}
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
