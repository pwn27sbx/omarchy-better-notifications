#!/usr/bin/env python3
import os
import sys
import glob
import json

def main():
    if len(sys.argv) < 2:
        print("[]")
        return
        
    history_dir = sys.argv[1]
    MAX_FILES = 100
    MAX_FILE_BYTES = 50 * 1024 # 50KB per file
    MAX_TOTAL_BYTES = 2 * 1024 * 1024 # 2MB total
    
    try:
        files = glob.glob(os.path.join(history_dir, "*.json"))
        # Sort by mtime descending
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        files = files[:MAX_FILES]
    except Exception:
        print("[]")
        return

    total_bytes = 0
    results = []

    for fpath in files:
        try:
            size = os.path.getsize(fpath)
            if size > MAX_FILE_BYTES:
                continue
                
            if total_bytes + size > MAX_TOTAL_BYTES:
                break
                
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                results.append(data)
                total_bytes += size
        except Exception:
            pass

    print(json.dumps(results))

if __name__ == "__main__":
    main()
