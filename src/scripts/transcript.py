#!/usr/bin/env python3
"""
YouTube video transcript concatenation script.
"""

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import pyperclip
import yt_dlp
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

# Lock for thread-safe printing
print_lock = Lock()


def extract_video_id(url):
    # Handles https://youtu.be/XXXX, https://www.youtube.com/watch?v=XXXX, and similar formats
    patterns = [r"(?:v=|/)([0-9A-Za-z_-]{11})"]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_title(video_url):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return info.get("title", "(No Title Found)")
    except Exception as e:
        return f"(Title error: {e})"


def get_transcript_with_retry(video_id, lang="en", max_retries=10, base_sleep=0.5):
    """Get transcript with retry logic"""

    for attempt in range(max_retries):
        try:
            transcript = YouTubeTranscriptApi.get_transcript(
                video_id, languages=[lang, "en", "en-US"]
            )
            return " ".join([x["text"] for x in transcript])
        except (TranscriptsDisabled, NoTranscriptFound):
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                first = next(iter(transcript_list), None)
                if first:
                    transcript = first.fetch()
                    return " ".join([x["text"] for x in transcript])
                return "(Transcript unavailable or disabled)"
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(base_sleep * (2 ** attempt))
                    continue
                return "(Transcript unavailable or disabled)"
        except VideoUnavailable:
            return "(Video unavailable)"
        except Exception as e:
            if attempt < max_retries - 1:
                with print_lock:
                    print(f"Transcript attempt {attempt + 1} failed, retrying... ({e})", file=sys.stderr)
                time.sleep(base_sleep * (2 ** attempt))
                continue
            return f"(Transcript error after {max_retries} attempts: {e})"

    return "(Failed after maximum retries)"


def process_video(index, raw_url):
    """Process a single video and return results with index"""
    # Sanitize URL by removing backslashes
    url = raw_url.replace("\\", "")
    video_id = extract_video_id(url)

    if not video_id:
        result = f"{raw_url}:\n(Invalid YouTube URL)\n"
        with print_lock:
            print(f"[{index + 1}] Invalid YouTube URL")
        return index, result

    # Fetch title and transcript in parallel for this video
    with ThreadPoolExecutor(max_workers=2) as executor:
        title_future = executor.submit(get_title, url)
        transcript_future = executor.submit(get_transcript_with_retry, video_id)

        title = title_future.result()
        transcript = transcript_future.result()

    result = f"{title}:\n{transcript}\n"

    with print_lock:
        print(f"[{index + 1}] Completed: {title}")

    return index, result


def main():
    parser = argparse.ArgumentParser(
        description="Concatenate YouTube video transcripts and copy to clipboard."
    )
    parser.add_argument(
        "-t",
        "--terminal",
        action="store_true",
        help="Print to terminal instead of copying to clipboard.",
    )
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=2,
        help="Number of worker threads (default: 2).",
    )
    parser.add_argument(
        "urls", nargs="*", help="YouTube video URLs (if empty, reads from stdin)."
    )

    args = parser.parse_args()

    # Gather URLs from stdin if no args and input is piped
    if not args.urls and not sys.stdin.isatty():
        urls = [line.strip() for line in sys.stdin if line.strip()]
    else:
        urls = args.urls

    if not urls:
        print("No YouTube URLs provided.")
        sys.exit(1)

    print(f"Processing {len(urls)} video(s) with {args.workers} workers...")

    # Process videos in parallel
    results = [None] * len(urls)  # Pre-allocate list to maintain order

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        future_to_index = {
            executor.submit(process_video, i, url): i for i, url in enumerate(urls)
        }

        # Collect results as they complete
        for future in as_completed(future_to_index):
            index, result = future.result()
            results[index] = result

    # Combine results in original order
    final_result = "\n".join(results)

    if args.terminal:
        print("\n" + "=" * 50)
        print(final_result)
    else:
        pyperclip.copy(final_result)
        print("\nOutput copied to clipboard.")


if __name__ == "__main__":
    main()
