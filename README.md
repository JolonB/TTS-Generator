# Text-to-Speech Generator

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/JolonB/TTS-Generator/main.svg)](https://results.pre-commit.ci/latest/github/JolonB/TTS-Generator/main)

## Setup

Set up your Python3 environment with:

```shell
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

You also need to have `ffmpeg` installed.
You can do this by running:

```shell
sudo apt install ffmpeg
```

## Running

```
usage: Text to Speech generator [-h] [-f FILES [FILES ...]] [-u URLS [URLS ...]]
                                [-w WORDS [WORDS ...]] [--bitrate BITRATE] [--progress]
                                [--overwrite] [-T THREADS] [-o OUTPUT_DIR]
                                [--max-per-second MAX_REQ_PER_SEC]

Uses Googles TTS service to generate mp3 files from a word list

optional arguments:
  -h, --help            show this help message and exit
  -f FILES [FILES ...], --files FILES [FILES ...]
                        File(s) to parse words from to generate audio. (default: None)
  -u URLS [URLS ...], --urls URLS [URLS ...]
                        URL(s) to parse words from to generate audio. (default: None)
  -w WORDS [WORDS ...], --words WORDS [WORDS ...]
                        Word(s) to generate audio for. (default: None)
  --bitrate BITRATE     The exported bitrate in any format supported by ffmpeg. (default: 16k)
  --progress            If set, will show a progress bar while running. (default: False)
  --overwrite           If set, any existing files will be generated again and overwritten.
                        (default: False)
  -T THREADS, --threads THREADS
                        The number of threads to run when generating audio. (default: 4)
  -o OUTPUT_DIR, --output OUTPUT_DIR
                        The directory to output the audio files to. (default: output/)
  --max-per-second MAX_REQ_PER_SEC
                        The maximum number of requests per second. Google supposedly limits to 5 per
                        second. (default: 5.0)
```
