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

# Defaults
DEFAULT_N_THREADS = 4
DEFAULT_OUTPUT_DIR = "output/"
DEFAULT_BITRATE = "16k"
DEFAULT_MAX_PER_SEC = 5.0
DEFAULT_LANGUAGE = "en"
DEFAULT_TLD = "com"

TIMEOUT_FSTRING = "%h:%m2:%s2"


class TextToSpeech:
    def __init__(
        self,
        n_threads=DEFAULT_N_THREADS,
        bitrate=DEFAULT_BITRATE,
        progress_bar=True,
        output_dir=DEFAULT_OUTPUT_DIR,
        max_per_second=DEFAULT_MAX_PER_SEC,
        language=DEFAULT_LANGUAGE,
        locale=DEFAULT_TLD,
    ):
        self.n_threads = n_threads
        self.bitrate = bitrate
        self.progress_bar = progress_bar
        self.output_dir = output_dir
        self.max_per_second = max_per_second
        self.language = language
        self.locale = locale
        self.reset_words()
        self.reset_progress_tracker()

    def reset_progress_tracker(self):
        self.progress_tracker = [[0] for _ in range(self.n_threads)]

    def create_progress_bar_thread(
        self, length: int, thread_timeout: float, thread_list: list
    ):
        if self.progress_bar:
            pbar = progressbar.ProgressBar(max_value=length)
            thread = threading.Thread(
                target=self.update_progressbar, daemon=True, args=(pbar, thread_timeout)
            )
            thread.start()
            thread_list.append(thread)

    def create_process_word_thread(
        self,
        word_list: list,
        thread_timeout: float,
        thread_index: int,
        thread_list: list,
    ):
        thread = threading.Thread(
            target=self.process_words,
            daemon=True,
            args=(word_list, thread_timeout, thread_index),
        )
        thread.start()
        thread_list.append(thread)

    def generate_mp3_from_words(self, words):
        if not words:
            raise ValueError("No words to process")

        self.reset_progress_tracker()

        # The timeout for running each thread
        thread_timeout = self.n_threads / self.max_per_second

        # Split the word lists for each thread
        split_word_list = [words[i :: self.n_threads] for i in range(self.n_threads)]

        threads = []

        self.create_progress_bar_thread(len(words), thread_timeout, threads)

        for index, word_list in enumerate(split_word_list):
            self.create_process_word_thread(word_list, thread_timeout, index, threads)
            # Offset thread start times so they run at evenly spaced intervals
            time.sleep(1 / self.max_per_second)

        for thread in threads:
            thread.join()

    def process_words(
        self,
        words: list,
        timeout: float,
        thread_index: int,
    ):
        for word in words:
            request = gtts.gTTS(word, lang=self.language, tld=self.locale)
            mp3_fp = autoretry_request(request)

            # Jump to start of mp3_fp so AudioSegment knows where to read
            mp3_fp.seek(0)
            audio = pydub.AudioSegment.from_mp3(mp3_fp)
            output_file = os.path.join(self.output_dir, f"{word}.mp3")
            audio.export(output_file, format="mp3", bitrate=self.bitrate)
            # Keep track of current progress
            self.progress_tracker[thread_index][0] += 1
            time.sleep(timeout)

    def update_progressbar(self, pbar, timeout):
        while pbar.value < pbar.max_value:
            pbar.update(sum(prog[0] for prog in self.progress_tracker))
            time.sleep(timeout)

    def add_words_from_file(self, filename: str):
        pass

    def add_words_from_url(self, url: str):
        pass

    def add_words(self, words: list):
        pass

    def reset_words(self):
        self.words = set()


def flatten_arglist(arguments: list):
    arguments_flattened = []
    if arguments:
        for argument_list in arguments:
            arguments_flattened.extend(argument_list)
    return arguments_flattened


def autoretry_request(request: gtts.gTTS) -> io.BytesIO:
    mp3_fp = io.BytesIO()
    success = False
    timeout = 5
    while not success:
        try:
            request.write_to_fp(mp3_fp)
            return mp3_fp
        except gtts.tts.gTTSError as response_error:
            print(response_error)
            if not response_error.rsp.ok:
                full_traceback = traceback.format_exc()
                ind = full_traceback.find("https://")
                requests_url = full_traceback[ind:].split("\n", 1)[0]
                if not requests_url and not response_error.ok:
                    raise RuntimeError(
                        "TTS URL has changed. Full traceback below:\n"
                        f"{full_traceback}"
                    )
                print(f"Failed request. Reauthenticate at {requests_url}")
            timeout_str = strfseconds(timeout, formatstring=TIMEOUT_FSTRING, ndecimal=1)
            print(f"Retrying in {timeout_str}")
            time.sleep(timeout)
            timeout = round(timeout * 2, 2)  # double the timeout each loop


def parse_word_list(words: list) -> list:
    split_words = words.split("\n")
    return [word.lower() for word in split_words if len(word)]


def parse_files(files: list) -> list:
    output = set()
    for filename in files:
        try:
            with open(filename, "r") as file:
                output.update(parse_word_list(file.read()))
        except FileNotFoundError:
            print(f"File {filename} is not found")
    return output


def parse_urls(urls: list) -> list:
    output = set()
    for url in urls:
        try:
            response = requests.get(url)
        except requests.exceptions.MissingSchema:
            print(f"URL {url} is invalid")
            continue

        if not response.ok:
            print(f"URL {url} returned {response}")
            continue
        output.update(parse_word_list(response.content.decode()))
    return output


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
    language = args.language
    locale = args.locale

    # Create output directory if it doesn't already exist
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    all_words = set()

    # Add user words
    all_words.update(user_words)

    # Add words from local files
    all_words.update(parse_files(filenames))

    # Add words from URLs
    all_words.update(parse_urls(urls))

    if not overwrite:
        existing_files = os.listdir(output_dir)
        existing_files = set(file.rsplit(".", 1)[0] for file in existing_files)
        all_words.difference_update(existing_files)

    all_words = list(all_words)

    tts_runner = TextToSpeech(
        n_threads=n_threads,
        bitrate=bitrate,
        progress_bar=progressbar,
        output_dir=output_dir,
        max_per_second=max_req_per_sec,
        language=language,
        locale=locale,
    )
    try:
        tts_runner.generate_mp3_from_words(all_words)
    except ValueError:
        print("No words to process")


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog="Text to Speech generator",
        description="Uses Googles TTS service to generate mp3 files from a"
        " word list",
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
        default=DEFAULT_BITRATE,
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
        default=DEFAULT_N_THREADS,
        help="The number of threads to run when generating audio.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_dir",
        action="store",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="The directory to output the audio files to.",
    )
    parser.add_argument(
        "--max-per-second",
        dest="max_req_per_sec",
        action="store",
        type=float,
        default=DEFAULT_MAX_PER_SEC,
        help="The maximum number of requests per second. The lower the number,"
        " the more words that will be generated before requests are rejected.",
    )
    languages = list(gtts.lang.tts_langs().keys())
    parser.add_argument(
        "--language",
        action="store",
        type=str,
        default=DEFAULT_LANGUAGE,
        choices=languages,
        help=f"The language to generate audio in. Options: {languages}",
        metavar="LANG",
    )
    parser.add_argument(
        "--locale",
        action="store",
        type=str,
        default=DEFAULT_TLD,
        help="The accent to generate audio in. More information here:"
        " https://gtts.readthedocs.io/en/latest/module.html#localized-accents",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    main(args)
