#![cfg_attr(
    all(not(debug_assertions), feature = "desktop"),
    windows_subsystem = "windows"
)]
use pipedl::{
    api::{router, Api},
    engine::{Engine, Op},
    lock_and_token, root_dir,
};
use std::sync::Arc;

fn main() {
    if let Err(e) = run() {
        eprintln!("PipeDL: {e}");
        if let Ok(root) = root_dir() {
            let _ = std::fs::create_dir_all(root.join(".pipedl"));
            let _ = std::fs::write(root.join(".pipedl/startup-error.log"), e.to_string());
        }
        #[cfg(windows)]
        if !std::env::args().any(|a| a == "--headless") {
            let message: Vec<u16> = format!("PipeDL could not start:\n{e}\0")
                .encode_utf16()
                .collect();
            let title: Vec<u16> = "PipeDL\0".encode_utf16().collect();
            unsafe {
                windows_sys::Win32::UI::WindowsAndMessaging::MessageBoxW(
                    std::ptr::null_mut(),
                    message.as_ptr(),
                    title.as_ptr(),
                    0x10,
                );
            }
        }
        std::process::exit(1);
    }
}
fn run() -> Result<(), Box<dyn std::error::Error>> {
    let root = root_dir()?;
    let port = std::env::var("PIPEDL_PORT")
        .unwrap_or_else(|_| "48127".into())
        .parse::<u16>()?;
    if port == 0 {
        return Err("PIPEDL_PORT must be 1–65535".into());
    }
    let runtime = tokio::runtime::Runtime::new()?;
    // Bind before opening/migrating storage: an old desktop owner must be shut down first.
    let listener = runtime.block_on(tokio::net::TcpListener::bind((
        std::net::Ipv4Addr::LOCALHOST,
        port,
    )))?;
    let (lock, token) = lock_and_token(&root)?;
    let engine = Engine::start(&root, lock)?;
    let state = Arc::new(Api {
        engine: engine.clone(),
        token: token.clone(),
        root: root.to_string_lossy().to_string(),
        port,
    });
    runtime.spawn(async move {
        if let Err(e) = axum::serve(listener, router(state)).await {
            eprintln!("HTTP server: {e}");
        }
    });
    let headless = std::env::args().any(|arg| arg == "--headless");
    if headless || !cfg!(feature = "desktop") {
        engine.call(Op::Activate)?;
        println!(
            "PipeDL API ready at http://127.0.0.1:{port}; token: {}",
            root.join(".pipedl/api-token").display()
        );
        runtime.block_on(async {
            loop {
                tokio::signal::ctrl_c().await?;
                match engine.request(Op::Shutdown).await {
                    Ok(_) => break,
                    Err(e) => eprintln!("{e}"),
                }
            }
            Ok::<_, std::io::Error>(())
        })?;
    } else {
        #[cfg(feature = "desktop")]
        desktop::run(engine, format!("http://127.0.0.1:{port}"), token)?;
    }
    Ok(())
}

#[cfg(feature = "desktop")]
mod desktop {
    use super::*;
    use tauri::{Emitter, Manager};
    #[derive(Clone, serde::Serialize)]
    pub struct Bootstrap {
        url: String,
        token: String,
    }
    #[tauri::command]
    fn bootstrap(state: tauri::State<Bootstrap>) -> Bootstrap {
        state.inner().clone()
    }
    #[tauri::command]
    fn open_releases(app: tauri::AppHandle) -> Result<(), String> {
        use tauri_plugin_opener::OpenerExt;
        app.opener()
            .open_url("https://github.com/ReturnYG/PipeDL/releases", None::<&str>)
            .map_err(|e| e.to_string())
    }
    #[tauri::command]
    async fn quit(app: tauri::AppHandle, engine: tauri::State<'_, Engine>) -> Result<(), String> {
        engine.request(Op::Shutdown).await?;
        app.exit(0);
        Ok(())
    }
    pub fn run(engine: Engine, url: String, token: String) -> tauri::Result<()> {
        tauri::Builder::default()
            .plugin(tauri_plugin_opener::init())
            .manage(engine)
            .manage(Bootstrap { url, token })
            .invoke_handler(tauri::generate_handler![bootstrap, quit, open_releases])
            .setup(|app| {
                use tauri::{
                    menu::{Menu, MenuItem},
                    tray::TrayIconBuilder,
                };
                let show = MenuItem::with_id(app, "show", "打开 PipeDL", true, None::<&str>)?;
                let quit = MenuItem::with_id(
                    app,
                    "quit",
                    "退出（请先停止运行中的任务）",
                    true,
                    None::<&str>,
                )?;
                let menu = Menu::with_items(app, &[&show, &quit])?;
                TrayIconBuilder::new()
                    .icon(app.default_window_icon().unwrap().clone())
                    .tooltip("PipeDL — Experiment workspace")
                    .menu(&menu)
                    .on_menu_event(|app, event| {
                        if event.id.as_ref() == "show" {
                            if let Some(w) = app.get_webview_window("main") {
                                let _ = w.show();
                                let _ = w.set_focus();
                            }
                        }
                        if event.id.as_ref() == "quit" {
                            let app = app.clone();
                            let engine = app.state::<Engine>().inner().clone();
                            tauri::async_runtime::spawn(async move {
                                match engine.request(Op::Shutdown).await {
                                    Ok(_) => app.exit(0),
                                    Err(e) => {
                                        if let Some(w) = app.get_webview_window("main") {
                                            let _ = w.show();
                                            let _ = w.set_focus();
                                        }
                                        let _ = app.emit("quit-error", e);
                                    }
                                }
                            });
                        }
                    })
                    .build(app)?;
                app.state::<Engine>().call(Op::Activate)?;
                Ok(())
            })
            .on_window_event(|window, event| {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
            })
            .build(tauri::generate_context!())?
            .run(|app, event| {
                if let tauri::RunEvent::ExitRequested { api, code, .. } = event {
                    if code.is_none() {
                        api.prevent_exit();
                        let _ = app;
                    }
                }
            });
        Ok(())
    }
}
