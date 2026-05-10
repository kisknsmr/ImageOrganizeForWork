use std::sync::{Arc, Mutex};
use tauri::Manager;
use tauri_plugin_shell::ShellExt;

struct ApiProcess(Arc<Mutex<Option<tauri_plugin_shell::process::CommandChild>>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let handle = app.handle().clone();

            // Python API サーバーをバックグラウンドで起動
            // プロジェクトルートを取得（app/src-tauri の2階層上）
            let _exe_dir = std::env::current_exe()
                .ok()
                .and_then(|p| p.parent().map(|p| p.to_path_buf()));

            // 開発時: cargo が実行されるディレクトリ = app/src-tauri
            // 本番時: exe のディレクトリ
            // CARGO_MANIFEST_DIR は app/src-tauri なので2階層上がプロジェクトルート
            // 実行時は current_dir() = app/ なので1階層上
            let project_root = std::env::var("CARGO_MANIFEST_DIR")
                .ok()
                .map(|d| {
                    std::path::PathBuf::from(d)
                        .parent().and_then(|p| p.parent())
                        .map(|p| p.to_path_buf())
                        .unwrap_or_default()
                })
                .or_else(|| {
                    std::env::current_dir().ok().and_then(|d| {
                        d.parent().map(|p| p.to_path_buf())
                    })
                })
                .unwrap_or_default();

            let project_root_str = project_root.to_string_lossy().to_string();

            tauri::async_runtime::spawn(async move {
                // ポートが既に使われているか確認（既存の Python サーバーが動いている場合はスキップ）
                if is_port_open(8765).await {
                    log::info!("API server already running on port 8765, skipping launch");
                    return;
                }

                log::info!("Starting Python API server from: {}", project_root_str);

                match handle
                    .shell()
                    .command("python")
                    .args([
                        "-m", "uvicorn",
                        "src.api_server:app",
                        "--host", "127.0.0.1",
                        "--port", "8765",
                        "--no-access-log",
                    ])
                    .current_dir(&project_root_str)
                    .spawn()
                {
                    Ok((mut rx, child)) => {
                        // プロセスをアプリステートに保存
                        handle.manage(ApiProcess(Arc::new(Mutex::new(Some(child)))));

                        // 起動ログを drain（エラーがあればログ出力）
                        while let Some(event) = rx.recv().await {
                            use tauri_plugin_shell::process::CommandEvent;
                            match event {
                                CommandEvent::Stderr(line) => {
                                    let msg = String::from_utf8_lossy(&line);
                                    if msg.contains("ERROR") || msg.contains("error") {
                                        log::error!("API: {}", msg.trim());
                                    }
                                }
                                CommandEvent::Terminated(_) => {
                                    log::warn!("API server process terminated");
                                    break;
                                }
                                _ => {}
                            }
                        }
                    }
                    Err(e) => {
                        log::error!("Failed to start Python API server: {}", e);
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            // アプリ終了時に Python プロセスを kill
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<ApiProcess>() {
                    let mut guard = state.0.lock().unwrap();
                    if let Some(child) = guard.take() {
                        let _ = child.kill();
                        log::info!("API server stopped");
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

async fn is_port_open(port: u16) -> bool {
    tokio::net::TcpStream::connect(format!("127.0.0.1:{}", port))
        .await
        .is_ok()
}
