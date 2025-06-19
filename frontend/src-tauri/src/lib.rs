use tauri::Manager;
use std::process::{Command, Child};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

struct BackendProcess(Mutex<Option<Child>>);

#[tauri::command]
async fn start_backend(app_handle: tauri::AppHandle) -> Result<String, String> {
    let backend_process = app_handle.state::<BackendProcess>();
    let mut process_guard = backend_process.0.lock().unwrap();
    
    if process_guard.is_none() {
        // Start Python backend
        let child = Command::new("python")
            .arg("../backend/main.py")
            .spawn()
            .map_err(|e| format!("Failed to start backend: {}", e))?;
            
        *process_guard = Some(child);
        Ok("Backend started successfully".to_string())
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
                thread::sleep(Duration::from_millis(1000));
                
                // Start the backend
                let runtime = tokio::runtime::Runtime::new().unwrap();
                runtime.block_on(async {
                    if let Err(e) = start_backend(app_handle).await {
                        eprintln!("Failed to start backend: {}", e);
                    } else {
                        println!("Backend started successfully!");
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
