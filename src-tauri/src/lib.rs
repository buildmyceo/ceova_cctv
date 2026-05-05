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
    
    // Kill existing
    if let Some(mut child) = child_guard.take() {
        let _ = child.kill();
    }

    // Start new
    let cmd = if cfg!(target_os = "windows") { "python" } else { "python3" };
    
    // Smart path detection
    let mut final_path = "main.py".to_string();
    let mut found = false;

    // Check common locations
    let possible_locations = vec![
        "main.py".to_string(),
        "../main.py".to_string(),
        "../../main.py".to_string(),
        "../../../main.py".to_string(),
        "/Users/chintukumar/ceova_cctv/main.py".to_string(), // Absolute fallback for your machine
    ];

    for loc in possible_locations {
        if std::path::Path::new(&loc).exists() {
            final_path = loc;
            found = true;
            break;
        }
    }

    if !found {
        println!("WARNING: could not find main.py. Backend auto-start may fail.");
    }

    match Command::new(cmd)
        .arg(final_path) 
        .spawn() 
    {
        Ok(child) => {
            *child_guard = Some(child);
            Ok("Backend restarted".into())
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
