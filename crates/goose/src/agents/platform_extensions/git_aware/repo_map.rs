use std::path::Path;
use std::process::Command;

#[derive(Debug, Clone)]
pub struct GitSummary {
    pub branch: String,
    pub staged: usize,
    pub unstaged: usize,
    pub untracked: usize,
    pub last_commit: String,
}

pub fn get_repo_summary(working_dir: &Path) -> Option<GitSummary> {
    if !working_dir.join(".git").exists() {
        return None;
    }

    let branch = get_current_branch(working_dir)?;
    let (staged, unstaged, untracked) = parse_git_status(working_dir)?;
    let last_commit = get_last_commit_message(working_dir).unwrap_or_default();

    Some(GitSummary {
        branch,
        staged,
        unstaged,
        untracked,
        last_commit,
    })
}

fn get_current_branch(working_dir: &Path) -> Option<String> {
    let output = Command::new("git")
        .current_dir(working_dir)
        .args(["rev-parse", "--abbrev-ref", "HEAD"])
        .output()
        .ok()?;

    if output.status.success() {
        Some(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        None
    }
}

fn parse_git_status(working_dir: &Path) -> Option<(usize, usize, usize)> {
    let output = Command::new("git")
        .current_dir(working_dir)
        .args(["status", "--porcelain"])
        .output()
        .ok()?;

    if !output.status.success() {
        return None;
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut staged = 0usize;
    let mut unstaged = 0usize;
    let mut untracked = 0usize;

    for line in stdout.lines() {
        if line.len() < 2 {
            continue;
        }
        let mut chars = line.chars();
        let index = chars.next().unwrap_or(' ');
        let work = chars.next().unwrap_or(' ');
        if index == '?' && work == '?' {
            untracked += 1;
        } else {
            if index != ' ' {
                staged += 1;
            }
            if work != ' ' && work != '?' {
                unstaged += 1;
            }
        }
    }

    Some((staged, unstaged, untracked))
}

fn get_last_commit_message(working_dir: &Path) -> Option<String> {
    let output = Command::new("git")
        .current_dir(working_dir)
        .args(["log", "-1", "--format=%s"])
        .output()
        .ok()?;

    if output.status.success() {
        Some(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_repo_summary_non_repo() {
        let dir = std::env::temp_dir();
        assert!(get_repo_summary(&dir).is_none());
    }
}
