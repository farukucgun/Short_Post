import praw
import requests
from moviepy.video.io.VideoFileClip import VideoFileClip, AudioFileClip
from pytube import YouTube
from pytube.exceptions import AgeRestrictedError
import pyttsx3
import nltk
from nltk.tokenize import sent_tokenize
import subprocess
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import config
import random
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import random
import socket
import logging as log
nltk.download('punkt')

"""
** IMPORTANCE ORDER
- get posts from tiktok and instagram saved posts
- post on tiktok
- create cover image
- add variety of subreddits
- add variety of videos
- change voiceover voice
- add advanced subtitles using Submagic, equal lengths 
- use playwrigth instead of selenium
- automate it, control it using a terminal on mobile
- try more options for write video file
- better error handling
"""

######### GLOBAL VARIABLES ##########
CLIENT_SECRETS_FILE = 'client_secret.json'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/drive.file']
YOUTUBE_API_SERVICE_NAME = 'youtube'
DRIVE_API_SERVICE_NAME = 'drive'
API_VERSION = 'v3'
socket.setdefaulttimeout(300) # 5 minutes of timeout for large google drive file uploads
log.basicConfig(filename=log.log, level=log.INFO, format='%(asctime)s:%(levelname)s:%(message)s')
#####################################


def get_reddit_post(post_index = 1):
    reddit = praw.Reddit(client_id=config.CLIENT_ID, client_secret=config.CLIENT_SECRET, user_agent=config.USER_AGENT)

    subreddit_chosen = random.randint(0, len(config.SUBREDDIT_LIST) - 1)
    subreddit = reddit.subreddit(config.SUBREDDIT_LIST[subreddit_chosen])

    top_posts = list(subreddit.top(time_filter='day', limit=post_index))
    post = top_posts[post_index] if len(top_posts) > post_index else top_posts[-1]

    post_title = post.title
    post_content = post.selftext if hasattr(post, 'selftext') else None
    credit = f"Credit: u/{post.author} on Reddit" if post.author else None
    media_url = None
    duration = None

    if post and post.media and 'reddit_video' in post.media:
        duration = post.media['reddit_video']['duration']
        media_url = post.media['reddit_video']['fallback_url']

        res4 = requests.get(media_url)
        with open(config.REDDIT_VIDEO, 'wb') as f:
            f.write(res4.content)
        
        audio_urls = [
            media_url.split("DASH_")[0] + "DASH_AUDIO_128.mp4",
            media_url.split("DASH_")[0] + "DASH_AUDIO_64.mp4",
            media_url.split("DASH_")[0] + "DASH_audio.mp4"
        ]

        for audio_url in audio_urls:
            res = requests.get(audio_url)
            if res.status_code == 200:
                with open(config.REDDIT_AUDIO, 'wb') as f:
                    f.write(res.content)
                combine_reddit_video_and_audio()
                break

    log.info('Got a post from Reddit.')
    return post_title, post_content, media_url, duration, credit


def combine_reddit_video_and_audio():
    video_clip = VideoFileClip(config.REDDIT_VIDEO)
    audio_clip = AudioFileClip(config.REDDIT_AUDIO)
    
    min_duration = min(video_clip.duration, audio_clip.duration)
    video_clip = video_clip.set_audio(audio_clip.subclip(0, min_duration))

    video_clip = video_clip.set_audio(audio_clip)
    video_clip.write_videofile(config.COMBINED_REDDIT_VIDEO)
    log.info('Combined the reddit video and audio.')


def format_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds:.3f}"


def create_voiceover_and_subtitles(text):
    engine = pyttsx3.init()
    engine.setProperty('rate', config.WORDS_PER_MINUTE)
    engine.save_to_file(text, config.VOICEOVER_MEDIA)
    engine.runAndWait()

    total_duration = AudioFileClip(config.VOICEOVER_MEDIA).duration - 0.5
    total_words = len(text.split())
    start_time = 0
    subtitles = []
    wpm = total_words / total_duration * 60
    
    for sentence in sent_tokenize(text):
        words = len(sentence.split())
        duration = words / wpm * 60

        subtitle = f"{len(subtitles) + 1}\n"
        subtitle += f"{format_time(start_time)} --> {format_time(start_time + duration)}\n"
        subtitle += f"{sentence.strip()}\n\n"
        subtitles.append(subtitle)
        start_time += duration
    
    with open(config.SUBTITLES, 'w', encoding='utf-8') as f:
        f.writelines(subtitles)

    log.info('Created voiceover and subtitles.')
    return total_duration + 0.5


def download_youtube_video(video_url, youtube_video):
    max_trials = 3
    for _ in range(max_trials):
        try:
            youtube = YouTube(video_url)
            video_stream = youtube.streams.filter(file_extension="mp4", res="720p").first()
            video_stream.download('.', filename=youtube_video)
            log.info('Downloaded the youtube video.')
            return './' + youtube_video
        except AgeRestrictedError:
            log.error('The video is age restricted, trying another one.')
            video_url = config.VIDEO_LIST[random.randint(0, len(config.VIDEO_LIST) - 1)]
    return None


def create_base_video():
    video_chosen = random.randint(0, len(config.VIDEO_LIST) - 1)
    video_url = config.VIDEO_LIST[video_chosen]
    video_path = download_youtube_video(video_url, config.YOUTUBE_VIDEO)

    voiceover_clip = AudioFileClip(config.VOICEOVER_MEDIA)
    video_clip = VideoFileClip(video_path)

    start_time = random.randint(config.VIDEO_START_SEC[video_chosen], int(video_clip.duration - voiceover_clip.duration))
    video_clip = video_clip.subclip(start_time, voiceover_clip.duration + start_time)
    video_clip = video_clip.set_audio(voiceover_clip)
    video_clip.write_videofile(config.BASE_VIDEO)
    log.info('Created the base video.')


def add_subtitles(input_video = config.BASE_VIDEO, output_video = config.SUBTITLED_VIDEO):
    subprocess.run([
        "ffmpeg",
        "-i", input_video,
        "-vf", f"subtitles={config.SUBTITLES}:force_style='Alignment=10,Fontsize=20'",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-y", output_video
    ])
    log.info('Added subtitles to the video.')


def format_video_for_shorts(input_video):
    subprocess.run([
        "ffmpeg",
        "-i", input_video,
        "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-y", config.SHORTS_VIDEO
    ])
    log.info('Formatted the video for shorts.')


def get_authenticated_service():
    credentials = None
    if os.path.exists('token.json'):
        credentials = Credentials.from_authorized_user_file('token.json')
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(credentials.to_json())
    log.info('Authenticated the user.')
    return build(YOUTUBE_API_SERVICE_NAME, API_VERSION, credentials=credentials), build(DRIVE_API_SERVICE_NAME, API_VERSION, credentials=credentials)


def youtube_share(youtube, title, description, input_video, category_id='23'):
    request_body = {
        'snippet': {
            'title': title,
            'description': description,
        },
        'status': {
            'privacyStatus': 'public',
        }
    }

    insert_request = youtube.videos().insert(
        part='snippet,status',
        body=request_body,
        media_body=MediaFileUpload(input_video, chunksize=-1, resumable=True)
    )

    resumable_upload(insert_request)


def resumable_upload(request):
    response = None
    error = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if response is not None:
                if 'id' in response:
                    log.info('Video id "%s" was successfully uploaded.' % response['id'])
                else:
                    log.error('The upload failed with an unexpected response: %s' % response)
                    exit()

        except Exception as e:
            log.error('An error occurred: %s' % e)
            if error is None:
                error = e
            retry += 1
            if retry > 5:
                log.error('No longer attempting to retry.')
                exit()
            max_sleep = 2 ** retry
            sleep_seconds = random.random() * max_sleep
            log.error('Sleeping %f seconds and then retrying...' % sleep_seconds)
            time.sleep(sleep_seconds)


def instagram_sleep_get_elements(driver, selector, humanlike):
    time.sleep(random.randint(1, 4)) if humanlike else None
    max_retries = 3
    for _ in range(max_retries):
        try:
            WebDriverWait(driver, 30).until(lambda driver: driver.find_elements(By.CSS_SELECTOR, selector))
            break
        except:
            time.sleep(2)
    return driver.find_elements(By.CSS_SELECTOR, selector)


def instagram_sleep_get_element(driver, selector, humanlike):
    time.sleep(random.randint(1, 4)) if humanlike else None
    max_retries = 3
    for _ in range(max_retries):
        try:
            WebDriverWait(driver, 30).until(lambda driver: driver.find_element(By.CSS_SELECTOR, selector))
            break
        except:
            time.sleep(2)
    return driver.find_element(By.CSS_SELECTOR, selector)


def instagram_wait_until_elements_present(driver, selector, humanlike):
    time.sleep(random.randint(1, 4)) if humanlike else None
    max_retries = 3
    for _ in range(max_retries):
        try:
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            break
        except:
            time.sleep(2)
    return driver.find_elements(By.CSS_SELECTOR, selector)


def instagram_share(driver, description, humanlike, input_video):
    driver.get(config.INSTAGRAM_URL)

    time.sleep(random.randint(1, 4)) if humanlike else None
    WebDriverWait(driver, 20).until(lambda driver: driver.find_element(By.NAME, "username"))
    driver.find_element(By.NAME, "username").send_keys(config.USERNAME)

    time.sleep(random.randint(1, 4)) if humanlike else None
    WebDriverWait(driver, 20).until(lambda driver: driver.find_element(By.NAME, "password"))
    driver.find_element(By.NAME, "password").send_keys(config.PASSWORD)

    instagram_sleep_get_element(driver, "button[type='submit']", humanlike).click()

    # Giriş bilgilerin kaydedilsin mi --> şimdi değil
    instagram_sleep_get_elements(driver, "._ac8f", humanlike)[0].click()

    # Bildirimleri aç --> şimdi değil
    instagram_sleep_get_elements(driver, "._a9--._ap36._a9_1", humanlike)[0].click()

    # Oluştur 
    instagram_sleep_get_elements(driver, ".x9f619.xxk0z11.xii2z7h.x11xpdln.x19c4wfv.xvy4d1p", humanlike)[6].click()
    
    # Gönderi
    instagram_sleep_get_elements(driver, ".x9f619.x1n2onr6.x1ja2u2z.x78zum5.x2lah0s.x1qughib.x6s0dn4.xozqiw3.x1q0g3np", humanlike)[0].click()

    # Put in the file
    instagram_sleep_get_elements(driver, "._ac69", humanlike)[0].send_keys(input_video)

    # Reels popup --> Tamam
    instagram_wait_until_elements_present(driver, "._acan._acap._acaq._acas._acav._aj1-._ap30", humanlike)[0].click()

    # Kırpmayı seç
    instagram_wait_until_elements_present(driver, "._abfz._abg1", humanlike)[0].click()

    # Kırpmayı seç --> Orijinal
    instagram_wait_until_elements_present(driver, "._ac36._ac38 > div", humanlike)[0].click()

    # kırp --> ileri
    instagram_sleep_get_elements(driver, "._ac7b._ac7d", humanlike)[0].click()

    # düzenle --> ileri
    instagram_sleep_get_elements(driver, "._ac7b._ac7d", humanlike)[0].click()

    # yeni reels videosu --> açıklama yaz
    instagram_sleep_get_element(driver, ".xw2csxc.x1odjw0f.x1n2onr6.x1hnll1o.xpqswwc.xl565be.x5dp1im.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.x1w2wdq1.xen30ot.x1swvt13.x1pi30zi.xh8yej3.x5n08af.notranslate", humanlike).send_keys(description)

    # yeni reels videosu --> paylaş
    instagram_sleep_get_elements(driver, "._ac7b._ac7d", humanlike)[0].click()

    # close the pop-up
    WebDriverWait(driver, 10000000).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".x1lliihq.x1plvlek.xryxfnj.x1n2onr6.x193iq5w.xeuugli.x1fj9vlw.x13faqbe.x1vvkbs.x1s928wv.xhkezso.x1gmr53x.x1cpjm7i.x1fgarty.x1943h6x.x1i0vuye.x1ms8i2q.xo1l8bm.x5n08af.x2b8uid.x4zkp8e.xw06pyt.x10wh9bi.x1wdrske.x8viiok.x18hxmgj")))
    time.sleep(random.randint(1, 3)) if humanlike else None

    log.info('Shared the video on Instagram.')


def organize(today_date):
    files = [config.REDDIT_VIDEO, config.REDDIT_AUDIO, config.COMBINED_REDDIT_VIDEO, config.SUBTITLES, 
             config.VOICEOVER_MEDIA, config.BASE_VIDEO, config.SUBTITLED_VIDEO, config.SHORTS_VIDEO]

    if not os.path.exists(today_date):
        os.mkdir(today_date)

    for file in files:
        if os.path.exists(file):
            os.rename(file, today_date + '/' + file)
    
    log.info('Organized the files.')


def backup_to_cloud(folder_path, service):
    folder_name = os.path.basename(folder_path)
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [config.FOLDER_ID]
    }

    folder = service.files().create(body=file_metadata, fields='id').execute()

    for file in os.listdir(folder_path):
        file_metadata = {
            'name': file,
            'parents': [folder.get('id')]
        }

        media = MediaFileUpload(folder_path + '/' + file)
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    log.info('Backed up the files to the cloud.')


def clean_up(folder_path):
    for file in os.listdir(folder_path):
        os.remove(folder_path + '/' + file)
    os.rmdir(folder_path)
    os.remove('token.json')

    if os.path.exists(config.YOUTUBE_VIDEO):
        os.chmod(config.YOUTUBE_VIDEO, 0o777)
        os.remove(config.YOUTUBE_VIDEO)

    log.info('Cleaned up the files.')


def post(trial, max_trials, driver, youtube_service):
    post_title, post_content, media_url, duration, credit = get_reddit_post(trial)
    title_with_credit = post_title + '\n\n' + credit if credit else post_title
    print('Duration:', duration if duration else 'None')
    print('Media url:', media_url if media_url else 'None')
    if media_url:
        instagram_share(driver, title_with_credit, config.HUMANLIKE, config.COMBINED_REDDIT_VIDEO_PATH)
        if duration < 60:
            format_video_for_shorts(config.COMBINED_REDDIT_VIDEO)
            youtube_share(youtube_service, post_title, title_with_credit, config.SHORTS_VIDEO)
        else:
            youtube_share(youtube_service, post_title, title_with_credit, config.COMBINED_REDDIT_VIDEO)
    else:
        if not post_content:
            return False
        duration = create_voiceover_and_subtitles(post_title + '.\n' + post_content)
        create_base_video()
        add_subtitles()
        instagram_share(driver, title_with_credit, config.HUMANLIKE, config.SUBTITLED_VIDEO_PATH)
        if duration < 60:
            format_video_for_shorts(config.SUBTITLED_VIDEO)
            youtube_share(youtube_service, post_title, title_with_credit, config.SHORTS_VIDEO)
        else:
            youtube_share(youtube_service, post_title, title_with_credit, config.SUBTITLED_VIDEO)
    
    return True


if __name__ == '__main__':
    youtube_service, drive_service = get_authenticated_service()
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=chrome_options)

    trial = 1
    max_trials = config.MAX_TRIALS
    done = False

    while (trial <= max_trials) and not done:
        done = post(trial, max_trials, driver, youtube_service)
        trial += 1

    driver.quit()

    today_date = datetime.today().strftime('%Y-%m-%d')
    organize(today_date)

    folder_path = os.path.join(config.CURRENT_DIR, today_date)
    backup_to_cloud(folder_path, drive_service)

    clean_up(folder_path)