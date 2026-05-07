use tauri::{
    menu::{Menu, MenuItem},
    tray::{TrayIconBuilder},
    Manager, Runtime,
};
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};

struct BackendState {
    child: Arc<Mutex<Option<Child>>>,
}

fn do_restart(state: &BackendState) -> Result<String, String> {
    let mut child_guard = state.child.lock().unwrap();
    
    // Kill existing backend process
    if let Some(mut child) = child_guard.take() {
        let _ = child.kill();
    }

    let new_child: std::io::Result<Child>;

    if cfg!(target_os = "windows") {
        // On Windows: look for bundled backend.exe next to our own executable
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()))
            .unwrap_or_else(|| std::path::PathBuf::from("."));

        let mut backend_exe = exe_dir.join("backend.exe");
        
        // If simple name doesn't exist, check for sidecar name
        if !backend_exe.exists() {
            let sidecar_name = exe_dir.join("backend-x86_64-pc-windows-msvc.exe");
            if sidecar_name.exists() {
                backend_exe = sidecar_name;
            }
        }
        
        if backend_exe.exists() {
            // Use the bundled PyInstaller backend
            new_child = Command::new(&backend_exe)
                .current_dir(&exe_dir)
                .spawn();
        } else {
            // Fallback: try system python (dev mode)
            new_child = Command::new("python")
                .arg("main.py")
                .current_dir(&exe_dir)
                .spawn();
        }
    } else {
        // On macOS/Linux: find Python and run main.py
        let mut python_cmd = "python3".to_string();
        let possible_pythons = vec![
            "/opt/homebrew/bin/python3",
            "/usr/bin/python3",
            "/usr/local/bin/python3",
        ];
        for py in &possible_pythons {
            if std::path::Path::new(py).exists() {
                python_cmd = py.to_string();
                break;
            }
        }

        // Smart path detection for main.py
        let mut main_py = "/Users/chintukumar/ceova_cctv/main.py".to_string();
        if !std::path::Path::new(&main_py).exists() {
            if std::path::Path::new("../main.py").exists() {
                main_py = "../main.py".to_string();
            } else if std::path::Path::new("main.py").exists() {
                main_py = "main.py".to_string();
            }
        }

        let work_dir = std::path::Path::new(&main_py)
            .parent()
            .unwrap_or(std::path::Path::new("."))
            .to_path_buf();

        new_child = Command::new(&python_cmd)
            .arg(&main_py)
            .current_dir(&work_dir)
            .spawn();
    }

    match new_child {
        Ok(child) => {
            *child_guard = Some(child);
            Ok("Backend started".into())
        }
        Err(e) => Err(format!("Failed to start backend: {}", e)),
    }
}

#[tauri::command]
fn restart_backend(state: tauri::State<BackendState>) -> Result<String, String> {
    do_restart(&state)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let child_state = Arc::new(Mutex::new(None));
    let state_for_setup = Arc::clone(&child_state);

    tauri::Builder::default()
        .manage(BackendState { child: child_state })
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(move |app| {
            // --- AUTO START BACKEND ---
            let initial_state = app.state::<BackendState>();
            let _ = do_restart(&initial_state);

            // --- SYSTEM TRAY SETUP ---
            let quit_i = MenuItem::with_id(app, "quit", "Quit Ceova", true, None::<&str>)?;
            let restart_i = MenuItem::with_id(app, "restart", "Restart Backend", true, None::<&str>)?;
            let open_i = MenuItem::with_id(app, "open", "Open Dashboard", true, None::<&str>)?;
            
            let menu = Menu::with_items(app, &[&open_i, &restart_i, &quit_i])?;

            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .on_menu_event(move |app, event| {
                    match event.id.as_ref() {
                        "quit" => {
                            let state = app.state::<BackendState>();
                            let mut guard = state.child.lock().unwrap();
                            if let Some(mut child) = guard.take() {
                                let _ = child.kill();
                            }
                            app.exit(0);
                        }
                        "open" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                        "restart" => {
                            let state = app.state::<BackendState>();
                            let _ = do_restart(&state);
                        }
                        _ => {}
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                window.hide().unwrap();
                api.prevent_close();
            }
        })
        .invoke_handler(tauri::generate_handler![restart_backend])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
