use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

#[derive(Debug, Clone, PartialEq)]
pub enum ChangeType {
    Modified,
    New,
}

#[derive(Debug, Clone)]
pub struct ChangedFile {
    pub path: PathBuf,
    pub modified: SystemTime,
    pub change_type: ChangeType,
}

pub struct WorkspaceIndex {
    root: PathBuf,
    previous_state: HashMap<PathBuf, SystemTime>,
}

impl WorkspaceIndex {
    pub fn new(path: &Path) -> Self {
        Self {
            root: path.to_path_buf(),
            previous_state: HashMap::new(),
        }
    }

    pub fn scan(&mut self) -> Vec<ChangedFile> {
        let mut changes = Vec::new();
        let mut current_state = HashMap::new();
        // Clone root to avoid borrow conflict (&mut self + &self.root)
        let root = self.root.clone();
        scan_dir(
            &root,
            &root,
            &self.previous_state,
            &mut current_state,
            &mut changes,
            0,
        );
        self.previous_state = current_state;
        changes
    }
}

fn scan_dir(
    dir: &Path,
    root: &Path,
    previous_state: &HashMap<PathBuf, SystemTime>,
    current_state: &mut HashMap<PathBuf, SystemTime>,
    changes: &mut Vec<ChangedFile>,
    depth: usize,
) {
    if depth > 4 {
        return;
    }

    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return,
    };

    for entry in entries.filter_map(Result::ok) {
        let path = entry.path();
        let metadata = match fs::metadata(&path) {
            Ok(m) => m,
            Err(_) => continue,
        };

        if metadata.is_dir() {
            if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                if matches!(name, ".git" | "target" | "node_modules") {
                    continue;
                }
            }
            scan_dir(
                &path,
                root,
                previous_state,
                current_state,
                changes,
                depth + 1,
            );
        } else {
            if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                if name.ends_with(".lock") {
                    continue;
                }
            }

            let modified = match metadata.modified() {
                Ok(t) => t,
                Err(_) => continue,
            };

            current_state.insert(path.clone(), modified);

            let rel_path = path.strip_prefix(root).unwrap_or(&path).to_path_buf();

            if let Some(&prev_time) = previous_state.get(&path) {
                if modified > prev_time {
                    changes.push(ChangedFile {
                        path: rel_path,
                        modified,
                        change_type: ChangeType::Modified,
                    });
                }
            } else {
                changes.push(ChangedFile {
                    path: rel_path,
                    modified,
                    change_type: ChangeType::New,
                });
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_scan_empty_dir() {
        let dir = std::env::temp_dir().join("gangus_test_index_empty");
        let _ = fs::create_dir_all(&dir);
        let mut index = WorkspaceIndex::new(&dir);
        let changes = index.scan();
        assert!(changes.is_empty());
    }

    #[test]
    fn test_scan_new_file_filtered() {
        let dir = std::env::temp_dir().join("gangus_test_index_new");
        let _ = fs::create_dir_all(&dir);
        let _ = fs::write(dir.join("test.rs"), "content");
        let _ = fs::write(dir.join("Cargo.lock"), "lock");
        let mut index = WorkspaceIndex::new(&dir);
        let changes = index.scan();
        // Only test.rs — Cargo.lock filtered
        assert_eq!(changes.len(), 1);
        assert_eq!(changes[0].change_type, ChangeType::New);
        assert!(changes[0].path.to_string_lossy().contains("test.rs"));
    }
}
