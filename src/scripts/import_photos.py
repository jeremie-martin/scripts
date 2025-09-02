#!/usr/bin/env python3
"""
Photo Import and Organization Script

OVERVIEW:
This script imports and organizes photos from cameras or directories into a clean,
date-based structure optimized for photography workflows using Darktable and image viewers.

DIRECTORY STRUCTURE CREATED:
photos/
└── 2025-06-29/
    ├── 2025-06-29-raw/               # RAW files (.CR3, .CR2, etc.) + their .xmp sidecars
    │   ├── IMG_0001.CR3
    │   └── …
    ├── jpg/                          # Camera JPEGs (.JPG) + their .xmp sidecars
    │   ├── IMG_0001.JPG
    │   └── …
    └── edits/                        # Processed images (.jpg variants) + optional symlinks to original JPEGs
        ├── IMG_0001-edited.jpg
        ├── …
        ├── IMG_0001.JPG → ../jpg/IMG_0001.JPG  # (only with --symlinks flag)
        └── …

KEY FEATURES:
• Smart grouping: All files related to IMG_6670 get the same date (from RAW/camera JPG)
• File type separation: RAW, camera JPEGs, and processed images in separate folders
• XMP sidecar handling: Darktable .xmp files follow their corresponding images
• Conflict resolution: Keeps oldest files (most original) except .xmp (keeps newest edits)
• Date visibility: All folder names include dates for easy Darktable navigation
• Optional comparison symlinks: Easy access to originals when reviewing processed images (--symlinks flag)

USAGE EXAMPLES:
# Auto-detect camera and import to ~/photos
import_photos

# Preview what would happen (dry run)
import_photos --dry-run

# Import from specific directory
import_photos /path/to/source/photos

# Import to custom destination
import_photos --dest /media/photos

# Move files instead of copying
import_photos --move

# Create symlinks to camera JPEGs in edits folder for comparison
import_photos --symlinks

# Full example: import from SD card to external drive with symlinks
import_photos /media/sdcard/DCIM --dest /backup/photos --symlinks --dry-run

ARGUMENTS:
source          Source directory (optional, auto-detects camera if not specified)
--dest DIR      Destination directory (default: ~/photos)
--move          Move files instead of copying
--dry-run       Preview what would be done without making changes
--symlinks      Create symlinks to camera JPEGs in edits folder for comparison

DEPENDENCIES:
None - uses only Python standard library
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


class PhotoImporter:
    def __init__(
        self, photos_dir, dry_run=False, move_files=False, create_symlinks=False
    ):
        self.photos_dir = Path(photos_dir)
        self.dry_run = dry_run
        self.move_files = move_files
        self.create_symlinks = create_symlinks
        self.results = defaultdict(lambda: defaultdict(list))

    def log(self, level, msg):
        colors = {"INFO": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m"}
        print(f"{colors.get(level, '')}[{level}]\033[0m {msg}")

    def get_destination(self, filename):
        """Return destination folder name based on file type"""
        # Handle .xmp sidecar files - they follow their corresponding image file
        if filename.lower().endswith(".xmp"):
            # Remove .xmp extension and check where the base file would go
            base_filename = filename[:-4]  # Remove .xmp
            return self.get_destination(base_filename)

        # Original camera files
        if re.match(r"^IMG_\d+\.(JPG|CR3)$", filename) or re.match(
            r"^MVI_\d+\.MP4$", filename
        ):
            # RAW files go to raw folder
            if filename.upper().endswith(
                (".CR3", ".CR2", ".RAW", ".NEF", ".ARW", ".DNG")
            ):
                return "raw"
            # Camera JPEGs go to jpg folder
            elif filename.upper().endswith(".JPG"):
                return "jpg"
            # Videos go to raw folder for now (could be separate if needed)
            else:
                return "raw"
        # Other IMG_/MVI_ files go to post
        elif filename.upper().startswith(("IMG_", "MVI_")):
            return "post"
        return None

    def get_date(self, file_path):
        """Get date from file modification time"""
        try:
            timestamp = file_path.stat().st_mtime
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        except:
            return "unknown-date"

    def create_camera_symlinks(self, date_str):
        """Create symlinks to camera JPEGs in edits directory for comparison"""
        if self.dry_run or not self.create_symlinks:
            return

        date_dir = self.photos_dir / date_str
        jpg_dir = date_dir / "jpg"
        edits_dir = date_dir / "edits"

        # Only create symlinks if both directories exist and have files
        if not (jpg_dir.exists() and edits_dir.exists()):
            return

        camera_jpegs = list(jpg_dir.glob("*.JPG")) + list(jpg_dir.glob("*.jpg"))
        if not camera_jpegs:
            return

        # Create symlinks for comparison directly in edits directory
        for jpeg_file in camera_jpegs:
            symlink_path = edits_dir / jpeg_file.name
            if not symlink_path.exists():
                try:
                    # Create relative symlink
                    relative_target = Path("..") / "jpg" / jpeg_file.name
                    symlink_path.symlink_to(relative_target)

                    # Set symlink date to match the original JPG file
                    jpeg_stat = jpeg_file.stat()
                    os.utime(
                        symlink_path,
                        (jpeg_stat.st_atime, jpeg_stat.st_mtime),
                        follow_symlinks=False,
                    )

                    self.log("INFO", f"Created symlink: {jpeg_file.name}")
                except OSError as e:
                    self.log(
                        "WARN", f"Failed to create symlink for {jpeg_file.name}: {e}"
                    )

    def process_file(self, file_path, date_str):
        """Process a single file"""
        destination = self.get_destination(file_path.name)
        if not destination:
            return False

        dest_dir = self.photos_dir / date_str

        # Map destination to actual folder names
        if destination == "raw":
            dest_subdir = dest_dir / f"{date_str}-raw"
        elif destination == "jpg":
            dest_subdir = dest_dir / "jpg"
        elif destination == "post":
            dest_subdir = dest_dir / "edits"
        else:
            return False

        dest_file = dest_subdir / file_path.name

        if self.dry_run:
            self.results[date_str][destination].append(file_path.name)
            return True

        # Create all required directories
        dest_subdir.mkdir(parents=True, exist_ok=True)

        # Ensure all subdirectories exist
        (dest_dir / f"{date_str}-raw").mkdir(exist_ok=True)
        (dest_dir / "jpg").mkdir(exist_ok=True)
        (dest_dir / "edits").mkdir(exist_ok=True)

        # Handle file conflicts
        if dest_file.exists():
            source_mtime = file_path.stat().st_mtime
            dest_mtime = dest_file.stat().st_mtime

            # Special handling for .xmp sidecar files - always keep the newest
            if file_path.name.lower().endswith(".xmp"):
                if source_mtime > dest_mtime:
                    self.log(
                        "INFO", f"Updating .xmp with newer version: {file_path.name}"
                    )
                elif source_mtime == dest_mtime:
                    self.log("WARN", f"Skipping identical .xmp file: {file_path.name}")
                    return True
                else:
                    self.log(
                        "WARN",
                        f"Keeping newer .xmp file, skipping older: {file_path.name}",
                    )
                    return True
            else:
                # For regular files: keep the one with oldest modification time (most original)
                if source_mtime < dest_mtime:
                    self.log(
                        "INFO",
                        f"Replacing with older (more original) version: {file_path.name}",
                    )
                elif source_mtime == dest_mtime:
                    self.log("WARN", f"Skipping identical file: {file_path.name}")
                    return True
                else:
                    self.log(
                        "WARN",
                        f"Keeping older (more original) file, skipping newer: {file_path.name}",
                    )
                    return True

        if self.move_files:
            shutil.move(str(file_path), str(dest_file))
            action = "Moved"
        else:
            # Use copy2 to preserve all metadata (timestamps, permissions, etc.)
            shutil.copy2(str(file_path), str(dest_file))
            action = "Copied"

        # Update log message to show actual folder names
        folder_name = f"{date_str}-raw" if destination == "raw" else destination
        if destination == "post":
            folder_name = "edits"
        self.log("INFO", f"{action}: {file_path.name} → {date_str}/{folder_name}/")
        return True

    def show_summary(self):
        """Show dry run results"""
        if not self.results:
            self.log("WARN", "No files would be organized.")
            return

        print("\n\033[32m[INFO]\033[0m Directory structure that would be created:\n")

        total_counts = defaultdict(int)
        ext_map = {
            ".cr3": "raw",
            ".cr2": "raw",
            ".raw": "raw",
            ".jpg": "jpg",
            ".jpeg": "jpg",
            ".mp4": "video",
            ".mov": "video",
            ".xmp": "xmp",
        }

        for date_dir in sorted(self.results.keys()):
            print(f"  📁 {date_dir}/")

            for folder in ["raw", "jpg", "post"]:
                files = self.results[date_dir][folder]
                if files:
                    counts = defaultdict(int)
                    for f in files:
                        ext = Path(f).suffix.lower()
                        counts[ext_map.get(ext, "other")] += 1

                    parts = [
                        f"{count} {type_}"
                        for type_, count in counts.items()
                        if count > 0
                    ]
                    desc = f": {', '.join(parts)}" if parts else ""

                    # Map to actual folder names for display
                    if folder == "raw":
                        folder_display = f"{date_dir}-raw"
                    elif folder == "jpg":
                        folder_display = "jpg"
                    elif folder == "post":
                        folder_display = "edits"

                    print(f"     ├── {folder_display}/ ({len(files)} files{desc})")

                    # Add to totals
                    total_counts["files"] += len(files)
                    for type_, count in counts.items():
                        total_counts[type_] += count
                else:
                    # Map to actual folder names for display
                    if folder == "raw":
                        folder_display = f"{date_dir}-raw"
                    elif folder == "jpg":
                        folder_display = "jpg"
                    elif folder == "post":
                        folder_display = "edits"
                    print(f"     ├── {folder_display}/")

            # Show edits symlinks if jpg files exist and symlinks are enabled
            if self.results[date_dir]["jpg"] and self.create_symlinks:
                print("     └── edits/ (symlinks to camera JPEGs for comparison)")

            print()

        # Show totals
        action = "move" if self.move_files else "copy"
        parts = [
            f"{total_counts[t]} {t}"
            for t in ["raw", "jpg", "video", "xmp", "other"]
            if total_counts[t] > 0
        ]
        desc = f" ({', '.join(parts)})" if parts else ""
        print(f"📊 Total: Would {action} {total_counts['files']} files{desc}")
        if self.create_symlinks:
            print(
                "📋 Camera JPEG symlinks will be created in edits/ for easy comparison\n"
            )
        else:
            print()

    def find_files(self, source_dir):
        """Find all relevant files"""
        files = []
        for file_path in Path(source_dir).rglob("*"):
            if file_path.is_file() and self.get_destination(file_path.name):
                files.append(file_path)
        return files

    def group_files_by_date(self, files):
        """Group files by base name, then get date from RAW file (or camera JPG if RAW missing)"""
        # First, group by basic image number (IMG_6670, IMG_6670_01, etc. all group together)
        groups = defaultdict(list)
        for f in files:
            # Extract base image number (IMG_6670 from IMG_6670_01.jpg)
            base_match = re.match(r"^(IMG_\d+|MVI_\d+)", f.stem)
            if base_match:
                base_name = base_match.group(1)
                groups[base_name].append(f)
            else:
                # Fallback to original stem
                groups[f.stem].append(f)

        file_dates = {}
        for base_name, group_files in groups.items():
            # Find RAW file in the group to use as date master
            raw_file = None
            camera_jpg = None

            for f in group_files:
                if f.suffix.lower() in {".cr3", ".cr2", ".raw", ".nef", ".arw", ".dng"}:
                    # Prefer the exact base name RAW (IMG_6670.CR3 over IMG_6670_01.CR3)
                    if f.stem == base_name:
                        raw_file = f
                        break
                    elif raw_file is None:  # Use any RAW if exact match not found
                        raw_file = f
                elif f.suffix.lower() == ".jpg" and f.stem == base_name:  # Camera JPG
                    camera_jpg = f

            # Get date from RAW file first, then camera JPG if RAW missing
            best_date = None
            date_source = None

            if raw_file:
                best_date = self.get_date(raw_file)
                date_source = "RAW"
                if best_date == "unknown-date":
                    best_date = None

            if not best_date and camera_jpg:
                best_date = self.get_date(camera_jpg)
                date_source = "camera JPG"
                if best_date == "unknown-date":
                    best_date = None

            # Fallback: try other files in group if no valid RAW or camera JPG date
            if not best_date:
                sorted_files = sorted(
                    group_files,
                    key=lambda f: f.suffix.lower() not in {".cr3", ".cr2", ".raw"},
                )
                for f in sorted_files:
                    date = self.get_date(f)
                    if date != "unknown-date":
                        best_date = date
                        date_source = "fallback"
                        break

            # Final fallback: use newest file modification time
            if not best_date:
                try:
                    newest = max(group_files, key=lambda f: f.stat().st_mtime)
                    best_date = datetime.fromtimestamp(newest.stat().st_mtime).strftime(
                        "%Y-%m-%d"
                    )
                    date_source = "file time"
                except Exception:
                    best_date = "unknown-date"
                    date_source = "unknown"

            # Log the date source for debugging if multiple files in group
            # if len(group_files) > 1 and date_source and best_date != 'unknown-date':
            # self.log('INFO', f"Group {base_name}: using date {best_date} from {date_source}")

            # Apply same date to ALL files in group
            for f in group_files:
                file_dates[f] = best_date

        return file_dates

    def find_camera(self):
        """Find a DCIM directory under common mount points (no sudo)."""
        candidates = [Path("/media"), Path("/run/media"), Path("/Volumes")]
        # Windows drive roots (A: to Z:)
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            candidates.append(Path(f"{letter}:/"))
        for base in candidates:
            if not base.exists():
                continue
            try:
                for p in base.glob("**/DCIM"):
                    if p.is_dir():
                        return str(p)
            except Exception:
                continue
        return None

    def _parse_size(self, size_str):
        """Deprecated; retained for compatibility."""
        try:
            if size_str.endswith("G"):
                return float(size_str[:-1])
            if size_str.endswith("M"):
                return float(size_str[:-1]) / 1024
            if size_str.endswith("T"):
                return float(size_str[:-1]) * 1024
        except Exception:
            return 0
        return 0

    def run(self, source_dir=None):
        """Main entry point"""
        # Determine source
        if not source_dir:
            source_dir = self.find_camera()
            if not source_dir:
                self.log("ERROR", "No camera found. Connect camera or specify directory.")
                return False
            self.log("INFO", f"Using camera DCIM: {source_dir}")

        if not Path(source_dir).exists():
            self.log("ERROR", f"Directory not found: {source_dir}")
            return False

        # Process files
        action = "Moving" if self.move_files else "Importing"
        mode = " (DRY RUN)" if self.dry_run else ""
        self.log("INFO", f"{action} from: {source_dir}{mode}")
        self.log("INFO", f"Destination: {self.photos_dir}")

        files = self.find_files(source_dir)
        if not files:
            self.log("WARN", f"No matching files found in: {source_dir}")
            return True

        file_dates = self.group_files_by_date(files)
        processed = sum(1 for f in files if self.process_file(f, file_dates[f]))

        if not self.dry_run:
            # Create symlinks for each date processed (if enabled)
            if self.create_symlinks:
                dates_processed = set(file_dates.values())
                for date_str in dates_processed:
                    if date_str != "unknown-date":
                        self.create_camera_symlinks(date_str)

        if self.dry_run:
            self.show_summary()
        else:
            action_word = "moved" if self.move_files else "copied"
            self.log("INFO", f"Successfully {action_word} {processed} files.")

        return True


def main():
    parser = argparse.ArgumentParser(description="Import and organize photos")
    parser.add_argument(
        "source", nargs="?", help="Source directory (auto-detect if not specified)"
    )
    parser.add_argument(
        "--dest",
        default=str(Path.home() / "photos"),
        help="Destination photos directory (default: ~/photos)",
    )
    parser.add_argument(
        "--move", action="store_true", help="Move files instead of copying"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview what would be done"
    )
    parser.add_argument(
        "--symlinks",
        action="store_true",
        help="Create symlinks to camera JPEGs in edits folder for comparison",
    )

    args = parser.parse_args()
    importer = PhotoImporter(
        args.dest,
        dry_run=args.dry_run,
        move_files=args.move,
        create_symlinks=args.symlinks,
    )

    return 0 if importer.run(args.source) else 1


if __name__ == "__main__":
    sys.exit(main())
