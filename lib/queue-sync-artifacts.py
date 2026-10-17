#!/usr/bin/env python3
"""
Queue Sync: Connect autonomous-queue.yaml to completion artifacts
Fixes FM-8 (queue integration) and FM-9 (false completion detection)
"""

import yaml
import os
import glob
import re
from datetime import datetime, timedelta
from pathlib import Path

# Configurable paths via env (defaults to current working directory)
import os

WORKSPACE = os.environ.get("AVS_WORKSPACE", str(Path.cwd()))
QUEUE_FILE = os.environ.get("AVS_QUEUE_FILE", str(Path(WORKSPACE) / "autonomous-queue.yaml"))
ARTIFACT_DIR = os.environ.get("AVS_ARTIFACT_DIR", str(Path(WORKSPACE) / "OPERATIONAL" / "completion-artifacts"))
BLOCKED_LOG = os.environ.get("AVS_BLOCKERS_FILE", str(Path(WORKSPACE) / "BLOCKERS.md"))

def load_queue():
    """Load and parse the autonomous queue"""
    with open(QUEUE_FILE, 'r') as f:
        return yaml.safe_load(f)

def save_queue(queue):
    """Save queue back to disk"""
    with open(QUEUE_FILE, 'w') as f:
        yaml.dump(queue, f, default_flow_style=False, sort_keys=False)

def find_artifacts_for_task(task_id):
    """Find all completion artifacts for a specific task"""
    pattern = f"{ARTIFACT_DIR}/TASK_{task_id}_*.yaml"
    return glob.glob(pattern)

def parse_timestamp(ts_str):
    """Parse artifact timestamp"""
    try:
        # Format: 20260205_143000
        return datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
    except:
        return None

def is_task_stuck(task):
    """Check if task has been in progress too long (>2 hours)"""
    if task.get('status') != 'in_progress':
        return False
    
    started = task.get('started_at')
    if not started:
        return False
    
    try:
        start_time = datetime.fromisoformat(started.replace('Z', '+00:00'))
        return datetime.now() - start_time > timedelta(hours=2)
    except:
        return False

def verify_artifact_integrity(artifact_path):
    """Check if artifact is valid YAML with required fields"""
    try:
        with open(artifact_path, 'r') as f:
            artifact = yaml.safe_load(f)
        
        required = ['task_id', 'status', 'timestamp_end', 'outputs']
        for field in required:
            if field not in artifact:
                return False, f"Missing field: {field}"
        
        # Verify outputs exist
        for output in artifact.get('outputs', []):
            if output.get('type') == 'file':
                path = output.get('path')
                if path and not os.path.exists(path):
                    return False, f"Output file missing: {path}"
        
        return True, "Valid"
    except Exception as e:
        return False, f"Parse error: {e}"

def sync_task_status(task):
    """Sync a single task with its artifacts"""
    task_id = task['id']
    artifacts = find_artifacts_for_task(task_id)
    
    if not artifacts:
        # No artifacts found
        if is_task_stuck(task):
            task['status'] = 'blocked'
            task['blocker'] = 'Stuck for >2 hours, no artifact produced'
            return True, f"Task {task_id}: BLOCKED (stuck, no artifact)"
        return False, f"Task {task_id}: No artifacts yet (still pending/in_progress)"
    
    # Keep both date and time from the filename's YYYYMMDD_HHMMSS suffix.
    # Task IDs, artifact types, and parent directories may contain underscores.
    latest_artifact = max(
        artifacts,
        key=lambda p: parse_timestamp('_'.join(Path(p).stem.rsplit('_', 2)[-2:]))
        or datetime.min,
    )
    
    # Verify integrity
    valid, reason = verify_artifact_integrity(latest_artifact)
    if not valid:
        task['status'] = 'blocked'
        task['blocker'] = f"Artifact invalid: {reason}"
        return True, f"Task {task_id}: BLOCKED (artifact invalid: {reason})"
    
    # Load artifact status
    with open(latest_artifact, 'r') as f:
        artifact = yaml.safe_load(f)
    
    artifact_status = artifact.get('status')
    
    # Sync queue status to artifact status
    if artifact_status == 'complete' and task['status'] != 'complete':
        task['status'] = 'complete'
        task['completed_at'] = artifact.get('timestamp_end')
        return True, f"Task {task_id}: MARKED COMPLETE (artifact verified)"
    
    if artifact_status == 'failed' and task['status'] != 'failed':
        task['status'] = 'failed'
        task['failure_mode'] = artifact.get('failure_mode', 'Unknown')
        return True, f"Task {task_id}: MARKED FAILED (artifact: {artifact.get('failure_mode')})"
    
    if artifact_status == 'partial' and task['status'] == 'in_progress':
        next_steps = artifact.get('next_steps_if_partial')
        if next_steps:
            task['notes'] = f"Partial complete. Next: {next_steps}"
        return True, f"Task {task_id}: PARTIAL (next steps noted)"
    
    return False, f"Task {task_id}: No change needed"

def main():
    """Main sync process"""
    print(f"=== Queue Sync: {datetime.now().isoformat()} ===")
    
    # Ensure directories exist
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    
    # Load queue
    try:
        queue = load_queue()
    except Exception as e:
        print(f"ERROR: Could not load queue: {e}")
        return 1
    
    changes = []
    blocked_tasks = []
    
    for task in queue.get('tasks', []):
        original_status = task.get('status')
        
        if original_status in ['complete', 'cancelled']:
            continue  # Skip already done
        
        changed, message = sync_task_status(task)
        
        if changed:
            changes.append(message)
        
        if task.get('status') == 'blocked':
            blocked_tasks.append(task)
    
    # Save if changes made
    if changes:
        save_queue(queue)
        print("Changes made:")
        for c in changes:
            print(f"  - {c}")
    else:
        print("No changes needed")
    
    # Report blocked tasks
    if blocked_tasks:
        print(f"\nWARN: {len(blocked_tasks)} blocked tasks:")
        for t in blocked_tasks:
            print(f"  - Task {t['id']}: {t.get('blocker', 'Unknown blocker')}")
    
    # Summary stats
    all_tasks = queue.get('tasks', [])
    complete = sum(1 for t in all_tasks if t.get('status') == 'complete')
    pending = sum(1 for t in all_tasks if t.get('status') == 'pending')
    in_progress = sum(1 for t in all_tasks if t.get('status') == 'in_progress')
    blocked = sum(1 for t in all_tasks if t.get('status') == 'blocked')
    
    print(f"\nQueue status: {complete} complete / {pending} pending / {in_progress} in_progress / {blocked} blocked")
    
    return 0

if __name__ == "__main__":
    exit(main())
