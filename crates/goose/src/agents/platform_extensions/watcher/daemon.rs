use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::sync::Mutex;

use super::index::{ChangedFile, WorkspaceIndex};

pub struct WatcherDaemon {
    working_dir: PathBuf,
    index: Arc<Mutex<WorkspaceIndex>>,
}

impl WatcherDaemon {
    pub fn new(working_dir: PathBuf) -> Self {
        let index = WorkspaceIndex::new(&working_dir);
        Self {
            working_dir,
            index: Arc::new(Mutex::new(index)),
        }
    }

    pub async fn get_changes_since_last_call(&self) -> Vec<ChangedFile> {
        let mut guard = self.index.lock().await;
        guard.scan()
    }

    pub fn working_dir(&self) -> &Path {
        &self.working_dir
    }
}
