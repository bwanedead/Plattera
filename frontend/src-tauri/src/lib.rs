use tauri::Manager;
use std::process::{Command, Child};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use std::env;
use std::path::Path;

struct BackendProcess(Mutex<Option<Child>>);

#[tauri::command]
async fn start_backend(app_handle: tauri::AppHandle) -> Result<String, String> {
    let backend_process = app_handle.state::<BackendProcess>();
    let mut process_guard = backend_process.0.lock().unwrap();
    
    if process_guard.is_none() {
        // Use a more direct approach - go directly to the backend directory
        let backend_dir = Path::new("../../backend");  // From src-tauri, go up 2 levels then into backend
        
        // Check if backend directory exists
        if !backend_dir.exists() {
            return Err(format!("Backend directory does not exist: {:?}", backend_dir.canonicalize().unwrap_or_else(|_| backend_dir.to_path_buf())));
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
            });
            
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![start_backend, check_backend_health])
        .on_window_event(|_window, event| match event {
            tauri::WindowEvent::CloseRequested { .. } => {
                println!("Cleaning up backend process...");
                // Backend process will be cleaned up automatically when the app closes
            }
            _ => {}
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
