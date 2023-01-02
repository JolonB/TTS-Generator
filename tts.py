#!/usr/bin/python3

import io
import threading
import time

import gtts
import progressbar
import pydub

THREADS = 8
FILENAME = "popular.txt"

def process_words(words: list, progress: list):
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
                time.sleep(600) # Wait 10 minutes before trying again
            
        # Jump to start of mp3_fp so AudioSegment knows where to read
        mp3_fp.seek(0)
        audio = pydub.AudioSegment.from_mp3(mp3_fp)
        audio.export(f"output/{word}.mp3", format="mp3", bitrate="16k")
        # Keep track of current progress
        progress[0] += 1

def update_progressbar(pbar, total_progress):
    while pbar.value < pbar.max_value:
        pbar.update(sum(prog[0] for prog in total_progress))
        time.sleep(1)

def main(filename=FILENAME, n_threads=THREADS, progress_bar=True):
    with open(filename, "r") as words_file:
        full_word_list = words_file.read().split("\n")
    
    split_word_list = [full_word_list[i::n_threads] for i in range(n_threads)]

    threads = []
    progress_values = [[0] for _ in range(THREADS)]

    if progress_bar:
        pbar = progressbar.ProgressBar(max_value=len(full_word_list))
        thread = threading.Thread(target=update_progressbar, args=(pbar, progress_values))
        thread.start()
        threads.append(thread)

    for index, word_list in enumerate(split_word_list):
        thread = threading.Thread(target=process_words, args=(word_list, progress_values[index]))
        thread.start()
        threads.append(thread)
    
    for thread in threads:
        thread.join()

if __name__ == "__main__":
    main()
