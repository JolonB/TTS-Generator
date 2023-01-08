#!/usr/bin/env python

import argparse
import copy
import dataclasses
import io
import os
import threading
import time
import traceback

import gtts
import progressbar
import pydub
import requests
from strfseconds import strfseconds

# Defaults
DEFAULT_N_THREADS = 4
DEFAULT_OUTPUT_DIR = "output/"
DEFAULT_BITRATE = "16k"
DEFAULT_MAX_PER_SEC = 5.0
DEFAULT_LANGUAGE = "en"
DEFAULT_TLD = "com"

TIMEOUT_FSTRING = "%h:%m2:%s2"


@dataclasses.dataclass
class TextToSpeechConfig:
    bitrate: str = DEFAULT_BITRATE
    progress_bar: bool = True
    output_dir: str = DEFAULT_OUTPUT_DIR
    n_threads: int = DEFAULT_N_THREADS
    max_per_second: float = DEFAULT_MAX_PER_SEC
    language: str = DEFAULT_LANGUAGE
    locale: str = DEFAULT_TLD


class TextToSpeech:
    def __init__(self, config: TextToSpeechConfig, overwrite=False):
        self._config = copy.copy(config)  # copy so this can't be changed on the fly
        self.reset_words()
        self._reset_progress_tracker()

        if not overwrite:
            existing_files = os.listdir(self._config.output_dir)
            self._existing_files = set(
                file.rsplit(".", 1)[0] for file in existing_files
            )
        else:
            self._existing_files = []

    def generate_mp3_files(self):
        if not self._words:
            raise ValueError("No words to process")

        # Filter out words that we don't want to overwrite
        words = self._words.difference(self._existing_files)

        # Convert words to something indexable
        words = list(words)

        self._reset_progress_tracker()

        # The timeout for running each thread
        thread_timeout = self._config.n_threads / self._config.max_per_second

        # Split the word lists for each thread
        split_word_list = [
            words[i :: self._config.n_threads] for i in range(self._config.n_threads)
        ]

        threads = []

        self._create_progress_bar_thread(len(words), thread_timeout, threads)

        for index, word_list in enumerate(split_word_list):
            self._create_process_word_thread(word_list, thread_timeout, index, threads)
            # Offset thread start times so they run at evenly spaced intervals
            time.sleep(1 / self._config.max_per_second)

        for thread in threads:
            thread.join()

    def add_words_from_files(self, filenames: list):
        for filename in filenames:
            self.add_words_from_file(filename)

    def add_words_from_file(self, filename: str):
        try:
            with open(filename, "r", encoding="utf-8") as file:
                self.add_words(self._parse_word_list(file.read()))
        except FileNotFoundError:
            print(f"File {filename} is not found")

    def add_words_from_urls(self, urls: list):
        for url in urls:
            self.add_words_from_url(url)

    def add_words_from_url(self, url: str):
        try:
            response = requests.get(url)
        except requests.exceptions.MissingSchema:
            print(f"URL {url} is invalid")
            return

        if not response.ok:
            print(f"URL {url} returned {response}")
            return

        self.add_words(self._parse_word_list(response.content.decode()))

    def add_words(self, words: list):
        self._words.update(words)

    def reset_words(self):
        self._words = set()

    def _reset_progress_tracker(self):
        self._progress_tracker = [[0] for _ in range(self._config.n_threads)]

    def _create_progress_bar_thread(
        self, length: int, thread_timeout: float, thread_list: list
    ):
        if self._config.progress_bar:
            pbar = progressbar.ProgressBar(max_value=length)
            thread = threading.Thread(
                target=self._update_progressbar,
                daemon=True,
                args=(pbar, thread_timeout),
            )
            thread.start()
            thread_list.append(thread)

    def _create_process_word_thread(
        self,
        word_list: list,
        thread_timeout: float,
        thread_index: int,
        thread_list: list,
    ):
        thread = threading.Thread(
            target=self._process_words,
            daemon=True,
            args=(word_list, thread_timeout, thread_index),
        )
        thread.start()
        thread_list.append(thread)

    @staticmethod
    def _autoretry_request(request: gtts.gTTS) -> io.BytesIO:
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
                        ) from response_error
                    print(f"Failed request. Reauthenticate at {requests_url}")
                timeout_str = strfseconds(
                    timeout, formatstring=TIMEOUT_FSTRING, ndecimal=1
                )
                print(f"Retrying in {timeout_str}")
                time.sleep(timeout)
                timeout = round(timeout * 2, 2)  # double the timeout each loop

    def _process_words(self, words: list, timeout: float, thread_index: int):
        for word in words:
            request = gtts.gTTS(
                word, lang=self._config.language, tld=self._config.locale
            )
            mp3_fp = self._autoretry_request(request)

            # Jump to start of mp3_fp so AudioSegment knows where to read
            mp3_fp.seek(0)
            audio = pydub.AudioSegment.from_mp3(mp3_fp)
            output_file = os.path.join(self._config.output_dir, f"{word}.mp3")
            audio.export(output_file, format="mp3", bitrate=self._config.bitrate)
            # Keep track of current progress
            self._progress_tracker[thread_index][0] += 1
            time.sleep(timeout)

    def _update_progressbar(self, pbar, timeout):
        while pbar.value < pbar.max_value:
            pbar.update(sum(prog[0] for prog in self._progress_tracker))
            time.sleep(timeout)

    @staticmethod
    def _parse_words(words: list) -> list:
        return [word for word in words if len(word)]

    @staticmethod
    def _parse_word_list(words: str) -> list:
        split_words = words.split("\n")
        return TextToSpeech._parse_words(split_words)


def flatten_arglist(arguments: list):
    arguments_flattened = []
    if arguments:
        for argument_list in arguments:
            arguments_flattened.extend(argument_list)
    return arguments_flattened


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

    tts_runner = TextToSpeech(
        TextToSpeechConfig(
            bitrate=bitrate,
            progress_bar=show_progress,
            output_dir=output_dir,
            n_threads=n_threads,
            max_per_second=max_req_per_sec,
            language=language,
            locale=locale,
        ),
        overwrite=overwrite,
    )

    # Add words from local files
    tts_runner.add_words_from_files(filenames)
    # Add words from URLs
    tts_runner.add_words_from_urls(urls)
    # Add user words
    tts_runner.add_words(user_words)
    try:
        tts_runner.generate_mp3_files()
    except ValueError:
        print("No words to process")


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog="Text to Speech generator",
        description="Uses Googles TTS service to generate mp3 files from a"
        " word list. Outputs files to output_dir with the name word.mp3. The"
        " word is written to the filename exactly as it appears in the word"
        " list, so this must be filtered beforehand where necessary.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-f",
        "--files",
        action="append",
        nargs="+",
        help="File(s) to parse words from to generate audio. The words are case sensitive.",
    )
    parser.add_argument(
        "-u",
        "--urls",
        action="append",
        nargs="+",
        help="URL(s) to parse words from to generate audio. The words are case sensitive.",
    )
    parser.add_argument(
        "-w",
        "--words",
        action="append",
        nargs="+",
        help="Word(s) to generate audio for. The words are case sensitive.",
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
    main(parse_arguments())
