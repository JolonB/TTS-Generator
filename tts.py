#!/usr/bin/env python

import argparse
import io
import os
import requests
import threading
import time

import gtts
import progressbar
import pydub

N_THREADS = 4
OUTPUT_DIR = "output"
BITRATE = "16k"


def flatten_arglist(arguments: list):
    arguments_flattened = []
    if arguments:
        for argument_list in arguments:
            arguments_flattened.extend(argument_list)
    return arguments_flattened


def process_words(words: list, bitrate: str, output_dir: str, progress: list):
    for word in words:
        mp3_fp = io.BytesIO()
        success = False
        request = gtts.gTTS(word)
        while not success:
            try:
                request.write_to_fp(mp3_fp)
                break
            except gtts.tts.gTTSError:
                print("Failed request")
                time.sleep(600)  # Wait 10 minutes before trying again

        # Jump to start of mp3_fp so AudioSegment knows where to read
        mp3_fp.seek(0)
        audio = pydub.AudioSegment.from_mp3(mp3_fp)
        audio.export(f"{output_dir}/{word}.mp3", format="mp3", bitrate=bitrate)
        # Keep track of current progress
        progress[0] += 1


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
):

    split_word_list = [words[i::n_threads] for i in range(n_threads)]

    threads = []
    # Create a mutable reference to the thread progress
    progress_values = [[0] for _ in range(n_threads)]

    if progress_bar:
        pbar = progressbar.ProgressBar(max_value=len(words))
        thread = threading.Thread(
            target=update_progressbar, args=(pbar, progress_values)
        )
        thread.start()
        threads.append(thread)

    for index, word_list in enumerate(split_word_list):
        thread = threading.Thread(
            target=process_words,
            args=(word_list, bitrate, output_dir, progress_values[index]),
        )
        thread.start()
        threads.append(thread)

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

    generate_mp3_from_words(
        all_words, n_threads=n_threads, bitrate=bitrate, progress_bar=show_progress
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="Text to Speech generator",
        description="Uses Googles TTS service to generate mp3 files from a word list",
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

    args = parser.parse_args()

    main(args)

    filenames = flatten_arglist(args.files)
    urls = flatten_arglist(args.urls)
    # main()
