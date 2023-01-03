#!/usr/bin/env python

import argparse
import io
import os
import requests
import threading
import time
import traceback

import gtts
import progressbar
import pydub
from strfseconds import strfseconds

N_THREADS = 4
OUTPUT_DIR = "output/"
BITRATE = "16k"
MAX_PER_SEC = 5.0

TIMEOUT_FSTRING = "%h:%m2:%s2"


def flatten_arglist(arguments: list):
    arguments_flattened = []
    if arguments:
        for argument_list in arguments:
            arguments_flattened.extend(argument_list)
    return arguments_flattened


def autoretry_request(word: str) -> io.BytesIO:
    request = gtts.gTTS(word)
    mp3_fp = io.BytesIO()
    success = False
    timeout = 5
    while not success:
        try:
            request.write_to_fp(mp3_fp)
            return mp3_fp
        except Exception as e:
            print(e)
            full_traceback = traceback.format_exc()
            ind = full_traceback.find("https://")
            requests_url = full_traceback[ind:].split("\n", 1)[0]
            if not requests_url:
                raise RuntimeError(
                    "TTS URL has changed. Full traceback below:\n" f"{full_traceback}"
                )
            print(f"Failed request. Reauthenticate at {requests_url}")
            timeout_str = strfseconds(timeout, formatstring=TIMEOUT_FSTRING, ndecimal=1)
            print(f"Retrying in {timeout_str}")
            time.sleep(timeout)
            timeout = round(timeout * 2, 2)  # double the timeout each loop


def process_words(
    words: list, bitrate: str, output_dir: str, timeout: float, progress: list
):
    for word in words:
        mp3_fp = autoretry_request(word)

        # Jump to start of mp3_fp so AudioSegment knows where to read
        mp3_fp.seek(0)
        audio = pydub.AudioSegment.from_mp3(mp3_fp)
        output_file = os.path.join(output_dir, f"{word}.mp3")
        audio.export(output_file, format="mp3", bitrate=bitrate)
        # Keep track of current progress
        progress[0] += 1
        time.sleep(timeout)


def update_progressbar(pbar, total_progress):
    while pbar.value < pbar.max_value:
        pbar.update(sum(prog[0] for prog in total_progress))
        time.sleep(1)


def generate_mp3_from_words(
    words,
    n_threads=N_THREADS,
    bitrate=BITRATE,
    progress_bar=True,
    output_dir=OUTPUT_DIR,
    max_per_second=MAX_PER_SEC,
):
    if not words:
        raise ValueError("No words to process")

    # The timeout for running each thread
    thread_timeout = n_threads / max_per_second

    # Split the word lists for each thread
    split_word_list = [words[i::n_threads] for i in range(n_threads)]

    threads = []
    # Create a mutable reference to the thread progress
    progress_values = [[0] for _ in range(n_threads)]

    if progress_bar:
        pbar = progressbar.ProgressBar(max_value=len(words))
        thread = threading.Thread(
            target=update_progressbar, daemon=True, args=(pbar, progress_values)
        )
        thread.start()
        threads.append(thread)

    for index, word_list in enumerate(split_word_list):
        thread = threading.Thread(
            target=process_words,
            daemon=True,
            args=(
                word_list,
                bitrate,
                output_dir,
                thread_timeout,
                progress_values[index],
            ),
        )
        thread.start()
        threads.append(thread)
        # Offset thread start times so they run at evenly spaced intervals
        time.sleep(1 / max_per_second)

    for thread in threads:
        thread.join()


def parse_word_list(words: list):
    split_words = words.split("\n")
    return [word.lower() for word in split_words if len(word)]


def main(args):
    filenames = flatten_arglist(args.files)
    urls = flatten_arglist(args.urls)
    user_words = flatten_arglist(args.words)
    bitrate = args.bitrate
    show_progress = args.show_progress
    overwrite = args.overwrite
    n_threads = args.threads
    output_dir = args.output_dir
    max_req_per_sec = args.max_req_per_sec

    # Create output directory if it doesn't already exist
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    all_words = set()

    # Add user words
    all_words.update(user_words)

    # Add words from local files
    for filename in filenames:
        try:
            with open(filename, "r") as file:
                all_words.update(parse_word_list(file.read()))
        except FileNotFoundError:
            print(f"File {filename} is not found")

    # Add words from URLs
    for url in urls:
        try:
            response = requests.get(url)
        except requests.exceptions.MissingSchema:
            print(f"URL {url} is invalid")
            continue

        if response.status_code != 200:
            print(f"URL {url} returned {response}")
            continue
        all_words.update(parse_word_list(response.content.decode()))

    if not overwrite:
        existing_files = os.listdir(output_dir)
        existing_files = set(file.rsplit(".", 1)[0] for file in existing_files)
        all_words.difference_update(existing_files)

    all_words = list(all_words)

    try:
        generate_mp3_from_words(
            all_words,
            n_threads=n_threads,
            bitrate=bitrate,
            progress_bar=show_progress,
            max_per_second=max_req_per_sec,
        )
    except ValueError:
        print("No words to process")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Text to Speech generator",
        description="Uses Googles TTS service to generate mp3 files from a word list",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-f",
        "--files",
        action="append",
        nargs="+",
        help="File(s) to parse words from to generate audio.",
    )
    parser.add_argument(
        "-u",
        "--urls",
        action="append",
        nargs="+",
        help="URL(s) to parse words from to generate audio.",
    )
    parser.add_argument(
        "-w",
        "--words",
        action="append",
        nargs="+",
        help="Word(s) to generate audio for.",
    )
    parser.add_argument(
        "--bitrate",
        action="store",
        default=BITRATE,
        help="The exported bitrate in any format supported by ffmpeg.",
    )
    parser.add_argument(
        "--progress",
        dest="show_progress",
        action="store_true",
        help="If set, will show a progress bar while running.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="If set, any existing files will be generated again and overwritten.",
    )
    parser.add_argument(
        "-T",
        "--threads",
        action="store",
        type=int,
        default=N_THREADS,
        help="The number of threads to run when generating audio.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_dir",
        action="store",
        type=str,
        default=OUTPUT_DIR,
        help="The directory to output the audio files to.",
    )
    parser.add_argument(
        "--max-per-second",
        dest="max_req_per_sec",
        action="store",
        type=float,
        default=MAX_PER_SEC,
        help="The maximum number of requests per second. Google supposedly limits to 5 per second.",
    )

    args = parser.parse_args()

    main(args)

    filenames = flatten_arglist(args.files)
    urls = flatten_arglist(args.urls)
    # main()
