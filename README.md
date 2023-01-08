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
## Usage

### Command Line

In most cases, you will only need to set either the files, URLs, or words argument.
You can typically keep the bitrate, threads, output directory, and max requests per second the same.
You may want to set the `--progress` flag so you can see how much time is remaining.
You may also want to set the language or locale (locales aren't compatible with every language).

A basic example which generates words from all three sources in UK English is shown below:

```shell
./tts --progress -f numbers.txt alphabet.txt -u example.com/1000_words.txt -w hello world --language en --locale co.uk
```

Full documentation can be found by running `./tts.py --help`.

```
usage: Text to Speech generator [-h] [-f FILES [FILES ...]] [-u URLS [URLS ...]]
                                [-w WORDS [WORDS ...]] [--bitrate BITRATE] [--progress]
                                [--overwrite] [-T THREADS] [-o OUTPUT_DIR]
                                [--max-per-second MAX_REQ_PER_SEC] [--language LANG]
                                [--locale LOCALE]

Uses Googles TTS service to generate mp3 files from a word list. Outputs files to output_dir
with the name word.mp3. The word is written to the filename exactly as it appears in the word
list, so this must be filtered beforehand where necessary.

optional arguments:
  -h, --help            show this help message and exit
  -f FILES [FILES ...], --files FILES [FILES ...]
                        File(s) to parse words from to generate audio. The words are case
                        sensitive. (default: None)
  -u URLS [URLS ...], --urls URLS [URLS ...]
                        URL(s) to parse words from to generate audio. The words are case
                        sensitive. (default: None)
  -w WORDS [WORDS ...], --words WORDS [WORDS ...]
                        Word(s) to generate audio for. The words are case sensitive. (default:
                        None)
  --bitrate BITRATE     The exported bitrate in any format supported by ffmpeg. (default: 16k)
  --progress            If set, will show a progress bar while running. (default: False)
  --overwrite           If set, any existing files will be generated again and overwritten.
                        (default: False)
  -T THREADS, --threads THREADS
                        The number of threads to run when generating audio. (default: 4)
  -o OUTPUT_DIR, --output OUTPUT_DIR
                        The directory to output the audio files to. (default: output/)
  --max-per-second MAX_REQ_PER_SEC
                        The maximum number of requests per second. The lower the number, the
                        more words that will be generated before requests are rejected.
                        (default: 5.0)
  --language LANG       The language to generate audio in. Options: ['af', 'ar', 'bg', 'bn',
                        'bs', 'ca', 'cs', 'da', 'de', 'el', 'en', 'es', 'et', 'fi', 'fr', 'gu',
                        'hi', 'hr', 'hu', 'id', 'is', 'it', 'iw', 'ja', 'jw', 'km', 'kn', 'ko',
                        'la', 'lv', 'ml', 'mr', 'ms', 'my', 'ne', 'nl', 'no', 'pl', 'pt', 'ro',
                        'ru', 'si', 'sk', 'sq', 'sr', 'su', 'sv', 'sw', 'ta', 'te', 'th', 'tl',
                        'tr', 'uk', 'ur', 'vi', 'zh-CN', 'zh-TW', 'zh'] (default: en)
  --locale LOCALE       The accent to generate audio in. More information here:
                        https://gtts.readthedocs.io/en/latest/module.html#localized-accents
                        (default: com)
```

Note that the files provided by the `--files` and `--urls` arguments should be plain text files formatted such that each line contains a word (or phrase) with no other character (i.e. no bullet points before the words or comments after the words).
An example of a valid file can be found [here](https://raw.githubusercontent.com/dolph/dictionary/master/popular.txt).

## Scripts

You can use the text to speech generator in scripts as well.
Simply place the `tts.py` file somewhere in your code and import it:

```python
import tts

tts_gen = tts.TextToSpeech(tts.TextToSpeechConfig())
tts_gen.add_words(["hello", "world"])
tts_gen.add_words_from_url("https://example.com/words.txt")
tts_gen.add_words_from_files(["words1.txt", "words2.txt"])

tts_gen.generate_mp3_files()
```

However, in most situations, you would be better off using the [`gTTS` library](https://pypi.org/project/gTTS/) instead.

## Checking Files

After running, you may want to check that all of the files are valid MP3 files.
You can do so with the `mp3val` tool which can be installed with:

```shell
sudo apt install mp3val
```

You can run it with:

```shell
mp3val output/*.mp3 -lresults.txt
```

Any errors will be found in results.txt.
You can find them by searching for `WARN` or `ERROR`.
You can safely ignore the `INFO`.

I'd also recommened running

```shell
find output/ -size 0
```

to find any files that are empty, because `mp3val` might miss these.

`mp3val` can fix invalid files by setting `-f`, but it may be better to just delete the corrupt files and run `./tts.py` again.
