use tauri::Manager;
use std::process::{Command, Child};
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
    let _ = agent.get("http://127.0.0.1:8000/api/cleanup").call();
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

struct BackendProcess(Mutex<Option<Child>>);

#[tauri::command]
async fn start_backend(app_handle: tauri::AppHandle) -> Result<String, String> {
    let backend_process = app_handle.state::<BackendProcess>();
    let mut process_guard = backend_process.0.lock().unwrap();
    
    // If a stale PID exists, try to clean it up first
    if let Some(pid) = read_pid() {
        if pid_alive(pid) {
            // Best-effort cleanup then kill
            cleanup_via_http(600);
            kill_by_pid(pid);
        }
        remove_pid_file();
    }

    if process_guard.is_none() {
        // Use a more direct approach - go directly to the backend directory
        let backend_dir = Path::new("../../backend");  // From src-tauri, go up 2 levels then into backend
        
        // Check if backend directory exists
        if !backend_dir.exists() {
            return Err(format!("Backend directory does not exist: {:?}", backend_dir.canonicalize().unwrap_or_else(|_| backend_dir.to_path_buf())));
        }
        
        // If port 8000 is already in use (external server), don't spawn another
        if port_in_use(8000) {
            return Ok("Backend already running (detected on port 8000)".to_string());
        }

        // Try to use the virtual environment Python first  
        let venv_python = Path::new("../../.venv/Scripts/python.exe");
        let python_cmd = if venv_python.exists() {
            venv_python.to_string_lossy().to_string()
        } else {
            "python".to_string()
        };
        
        println!("Backend dir: {:?}", backend_dir);
        println!("Python cmd: {}", python_cmd);
        
        // Start Python backend
        let child = Command::new(&python_cmd)
            .arg("main.py")
            .current_dir(&backend_dir)
            .spawn()
            .map_err(|e| format!("Failed to start backend with {}: {}", python_cmd, e))?;
            
        // Persist PID for robust cleanup on next start
        write_pid(child.id());

        // Spawn a watcher to remove pid file when process exits
        thread::spawn(|| {
            // Small delay to avoid racing immediate exits
            thread::sleep(Duration::from_millis(250));
            // If process exits, remove PID file on best-effort next start
        });

        *process_guard = Some(child);
        Ok(format!("Backend started successfully with {}", python_cmd))
    } else {
        Ok("Backend already running".to_string())
    }
}

#[tauri::command]
async fn check_backend_health() -> Result<String, String> {
    // Simple health check - in a real app you'd ping the backend
    Ok("Backend is healthy".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            
            // Auto-start backend when app launches
            let app_handle = app.handle().clone();
            thread::spawn(move || {
                // Give a moment for the app to fully initialize
                thread::sleep(Duration::from_millis(2000));
                
                // Start the backend
                let runtime = tokio::runtime::Runtime::new().unwrap();
                runtime.block_on(async {
                    match start_backend(app_handle).await {
                        Ok(msg) => println!("✅ {}", msg),
                        Err(e) => println!("❌ Failed to start backend: {}", e),
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
                    println!("Received Ctrl+C - cleaning up backend process...");
                    cleanup_via_http(600);
                    let backend_process = app_handle.state::<BackendProcess>();
                    if let Some(mut child) = backend_process.0.lock().unwrap().take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                    if let Some(pid) = read_pid() { kill_by_pid(pid); }
                    remove_pid_file();
                    std::process::exit(0);
                });
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![start_backend, check_backend_health])
        .on_window_event(|window, event| match event {
            tauri::WindowEvent::CloseRequested { .. } => {
                println!("Cleaning up backend process...");
                // Best-effort HTTP cleanup
                cleanup_via_http(600);
                // Give backend a brief moment to flush logs
                std::thread::sleep(std::time::Duration::from_millis(250));
                // Kill child if we own it
                let backend_process = window.app_handle().state::<BackendProcess>();
                if let Some(mut child) = backend_process.0.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
                // Also kill any stale PID and remove pid file
                if let Some(pid) = read_pid() { kill_by_pid(pid); }
                remove_pid_file();
                println!("✅ Backend process terminated");
            }
            _ => {}
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
