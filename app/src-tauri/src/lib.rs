use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use tauri::Manager;

/// 起動した FastAPI(uvicorn) 子プロセスを保持し、アプリ終了時に落とすための状態。
struct BackendProcess(Mutex<Option<Child>>);

const BACKEND_ADDR: &str = "127.0.0.1:8765";

/// すでに :8765 でサーバが動いているか（手動起動 or 前回の残り）を確認する。
fn backend_already_running() -> bool {
    match BACKEND_ADDR.parse() {
        Ok(addr) => TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok(),
        Err(_) => false,
    }
}

/// app/src-tauri（コンパイル時パス）からリポジトリルートを求める。
fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent() // app
        .and_then(|p| p.parent()) // repo root
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| PathBuf::from("."))
}

/// リポジトリの .venv を使って uvicorn を子プロセスとして起動する。
/// 既に起動済み、または venv が見つからない場合は None を返す（手動起動にフォールバック）。
fn spawn_backend() -> Option<Child> {
    if backend_already_running() {
        eprintln!("[backend] {BACKEND_ADDR} は既に応答しています。二重起動を回避します。");
        return None;
    }

    let root = repo_root();
    #[cfg(windows)]
    let python = root.join(".venv").join("Scripts").join("python.exe");
    #[cfg(not(windows))]
    let python = root.join(".venv").join("bin").join("python");

    if !python.exists() {
        eprintln!(
            "[backend] venv python が見つかりません: {}\n\
             手動で `uvicorn src.api_server:app --port 8765` を起動してください。",
            python.display()
        );
        return None;
    }

    let mut cmd = Command::new(&python);
    cmd.current_dir(&root).args([
        "-m",
        "uvicorn",
        "src.api_server:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]);
    // Windows のリリースビルドでコンソール窓が開かないようにする（CREATE_NO_WINDOW）。
    #[cfg(windows)]
    cmd.creation_flags(0x0800_0000);

    match cmd.spawn() {
        Ok(child) => {
            eprintln!("[backend] uvicorn を起動しました (pid {})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[backend] uvicorn の起動に失敗しました: {e}");
            None
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let child = spawn_backend();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendProcess(Mutex::new(child)))
        .build(tauri::generate_context!())
        .expect("error while running tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<BackendProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                            let _ = child.wait();
                            eprintln!("[backend] uvicorn を停止しました。");
                        }
                    }
                }
            }
        });
}
