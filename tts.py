#!/usr/bin/env python

"""This module can be used to generate text to speech using Google Translate's
text-to-speech API in bulk.

This uses the gTTS library to generate audio and pydub to save it.
The reason you might use this module is to automatically generate a lot of words.
This module will automatically retry if anything goes wrong when generating audio.
"""

import argparse
import copy
import dataclasses
import io
import os
import threading
import time
import traceback
from typing import List

import gtts
import progressbar
import pydub
import requests
from strfseconds import strfseconds

# Defaults
_DEFAULT_N_THREADS = 4
_DEFAULT_OUTPUT_DIR = "output/"
_DEFAULT_FILETYPE = "mp3"
_DEFAULT_BITRATE = "16k"
_DEFAULT_MAX_PER_SEC = 5.0
_DEFAULT_LANGUAGE = "en"
_DEFAULT_TLD = "com"

# Timeout information formatting
_TIMEOUT_FSTRING = "%h:%m2:%s2"


@dataclasses.dataclass
class TextToSpeechConfig:  # pylint: disable=too-many-instance-attributes
    """
    Configuration for the TextToSpeech class.

    Args:
        bitrate (str): The bitrate of the generated audio.
        progress_bar (bool): Whether to show a progress bar while generating.
        output_dir (str): The directory to output the files to.
        filetype (str): The filetype to write.
        n_threads (int): The number of threads to run.
        max_per_second (float): The maximum number of requests per second.
        language (str): The langauge to generate audio in.
        locale (str): The locale/accent to generate audio in.
    """

    bitrate: str = _DEFAULT_BITRATE
    progress_bar: bool = True
    output_dir: str = _DEFAULT_OUTPUT_DIR
    filetype: str = _DEFAULT_FILETYPE
    n_threads: int = _DEFAULT_N_THREADS
    max_per_second: float = _DEFAULT_MAX_PER_SEC
    language: str = _DEFAULT_LANGUAGE
    locale: str = _DEFAULT_TLD


class TextToSpeech:
    """
    Text to Speech generator.

    Accepts words in the form of Python lists, URLs, and files.
    Generates mp3 files based on the config provided.
    """

    def __init__(self, config: TextToSpeechConfig, overwrite: bool = False):
        """Text to speech generator setup.

        Stores the config and initialises an empty word list.
        If overwrite is False, will create a list of words that have already been
        generated so they aren't generated again.

        Args:
            config (TextToSpeechConfig): The settings for this TextToSpeech instance.
            overwrite (bool, optional): Whether to overwrite existing files in
                                        the output directory. Defaults to False.
        """
        self._config = copy.copy(config)  # copy so this can't be changed on the fly
        self.reset_words()
        self._reset_progress_tracker()

        self._existing_files = []
        if not overwrite:
            filename_end = f".{self._config.filetype}"
            listed_files = os.listdir(self._config.output_dir)
            for filename in listed_files:
                if filename.endswith(filename_end):
                    filename_no_ext = filename.rsplit(filename_end, 1)[0]
                    self._existing_files.append(filename_no_ext)

    def run(self):
        """Run the text to speech generator.

        Send requests to the Google TTS server and write the output to files.
        Automatically retries if a request fails or gets blocked due to
        excessive requests.

        Raises:
            ValueError: If there are no words to process.
        """
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

    def add_words_from_files(self, filenames: List[str]):
        """Parse a list of files and add words from them.

        Args:
            filenames (List[str]): The filenames to add words from.
        """
        for filename in filenames:
            self.add_words_from_file(filename)

    def add_words_from_file(self, filename: str):
        """Parse a file and add words from it.

        Args:
            filename (str): The filename to add words from.
        """
        try:
            with open(filename, "r", encoding="utf-8") as file:
                self.add_words(self._parse_word_list(file.read()))
        except FileNotFoundError:
            print(f"File {filename} is not found")

    def add_words_from_urls(self, urls: List[str]):
        """Download files and add words from them.

        Args:
            urls (List[str]): The files to download and parse.
        """
        for url in urls:
            self.add_words_from_url(url)

    def add_words_from_url(self, url: str):
        """Download a file and add the words from it.

        Args:
            url (str): The file to download and parse.
        """
        try:
            response = requests.get(url)
        except requests.exceptions.MissingSchema:
            print(f"URL {url} is invalid")
            return

        if not response.ok:
            print(f"URL {url} returned {response}")
            return

        self.add_words(self._parse_word_list(response.content.decode()))

    def add_words(self, words: List[str]):
        """Add words from a list of words.

        Args:
            words (List[str]): The list of words to add.
        """
        self._words.update(words)

    def reset_words(self):
        """Remove all words."""
        self._words = set()

    @property
    def config(self) -> TextToSpeechConfig:
        """Get the configuration."""
        return copy.copy(self._config)

    @property
    def words(self) -> List[str]:
        """Get the added words."""
        return sorted(self._words)

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
        timeout = 5
        while True:
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
                    timeout, formatstring=_TIMEOUT_FSTRING, ndecimal=1
                )
                print(f"Retrying in {timeout_str}")
                time.sleep(timeout)
                timeout = round(timeout * 2, 2)  # double the timeout each loop

    def _process_words(self, words: list, timeout: float, thread_index: int):
        filetype = self._config.filetype
        for word in words:
            request = gtts.gTTS(
                word, lang=self._config.language, tld=self._config.locale
            )
            mp3_fp = self._autoretry_request(request)

            # Jump to start of mp3_fp so AudioSegment knows where to read
            mp3_fp.seek(0)
            audio = pydub.AudioSegment.from_mp3(mp3_fp)
            output_file = os.path.join(self._config.output_dir, f"{word}.{filetype}")
            audio.export(output_file, format=filetype, bitrate=self._config.bitrate)
            # Keep track of current progress
            self._progress_tracker[thread_index][0] += 1
            time.sleep(timeout)

    def _update_progressbar(self, pbar, timeout):
        while pbar.value < pbar.max_value:
            pbar.update(sum(prog[0] for prog in self._progress_tracker))
            time.sleep(timeout)

    @staticmethod
    def _parse_words(words: List[str]) -> List[str]:
        return [word for word in words if len(word)]

    @staticmethod
    def _parse_word_list(words: str) -> List[str]:
        split_words = words.split("\n")
        return TextToSpeech._parse_words(split_words)


def _flatten_arglist(arguments: List[List[str]]):
    arguments_flattened = []
    if arguments:
        for argument_list in arguments:
            arguments_flattened.extend(argument_list)
    return arguments_flattened


def _main(args: argparse.Namespace):
    filenames = _flatten_arglist(args.files)
    urls = _flatten_arglist(args.urls)
    user_words = _flatten_arglist(args.words)
    bitrate = args.bitrate
    show_progress = args.show_progress
    overwrite = args.overwrite
    n_threads = args.threads
    output_dir = args.output_dir
    filetype = args.filetype
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
            filetype=filetype,
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
        tts_runner.run()
    except ValueError:
        print("No words to process")


def _parse_arguments():
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
        default=_DEFAULT_BITRATE,
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
        default=_DEFAULT_N_THREADS,
        help="The number of threads to run when generating audio.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_dir",
        action="store",
        type=str,
        default=_DEFAULT_OUTPUT_DIR,
        help="The directory to output the audio files to.",
    )
    parser.add_argument(
        "-t",
        "--filetype",
        dest="filetype",
        action="store",
        type=str,
        default=_DEFAULT_FILETYPE,
        help="The file format of the audio in any format supported by ffmpeg.",
    )
    parser.add_argument(
        "--max-per-second",
        dest="max_req_per_sec",
        action="store",
        type=float,
        default=_DEFAULT_MAX_PER_SEC,
        help="The maximum number of requests per second. The lower the number,"
        " the more words that will be generated before requests are rejected.",
    )
    languages = list(gtts.lang.tts_langs().keys())
    parser.add_argument(
        "--language",
        action="store",
        type=str,
        default=_DEFAULT_LANGUAGE,
        choices=languages,
        help=f"The language to generate audio in. Options: {languages}",
        metavar="LANG",
    )
    parser.add_argument(
        "--locale",
        action="store",
        type=str,
        default=_DEFAULT_TLD,
        help="The accent to generate audio in. More information here:"
        " https://gtts.readthedocs.io/en/latest/module.html#localized-accents",
    )

    return parser.parse_args()


if __name__ == "__main__":
    _main(_parse_arguments())
