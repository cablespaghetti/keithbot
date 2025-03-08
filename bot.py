import csv
import logging
import os
import urllib
from time import sleep

from atproto import Client, client_utils
from mastodon import Mastodon
from prometheus_client import Counter, start_http_server

logger = logging.getLogger(__name__)
logging.basicConfig(encoding="utf-8", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


def repost(bluesky_post):
    mastodon = get_mastodon()
    post_content = bluesky_post["text"]
    if bluesky_post["quote_post_url"]:
        post_content += "\n"
        post_content += f'Quoted Post: {bluesky_post["quote_post_url"]}'
    elif bluesky_post["link_url"]:
        post_content += "\n"
        post_content += bluesky_post["link_url"]

    media_ids = []

    if bluesky_post["image_urls"]:
        for image_url in bluesky_post["image_urls"]:
            logger.info(f"Downloading image from {image_url}")
            image_response = urllib.request.urlopen(image_url)
            image_mime_type = image_response.headers["Content-Type"]
            image_data = image_response.read()
            logger.debug("Posting image")
            image_media_id = mastodon.media_post(image_data, image_mime_type)
            media_ids.append(image_media_id)

    status_dict = mastodon.status_post(post_content, media_ids=media_ids)
    if status_dict:
        logger.info(
            f'Posted Bluesky post with id {bluesky_post["id"]} from {bluesky_post["timestamp"]} with content {post_content}'
        )
        field_names = ("id", "date")
        with open("posts.csv", "a") as post_log:
            writer = csv.DictWriter(post_log, field_names)
            new_row = {"id": bluesky_post["id"], "date": bluesky_post["timestamp"]}
            writer.writerow(new_row)
    return status_dict


def check_post_log(post_id):
    field_names = ("id", "date")
    with open("posts.csv", "r") as post_log:
        reader = csv.DictReader(post_log, field_names)
        for row in reader:
            if row["id"] == str(post_id):
                logger.debug("Already posted " + str(post_id))
                return True
    return False


def get_mastodon() -> Mastodon:
    """Creates an instance of the Mastodon Class

    Returns:
        Mastodon: The instance of the Mastodon Class
    """
    access_token = os.environ.get("MASTODON_ACCESS_TOKEN", "banana")
    api_base_url = os.environ.get("MASTODON_BASE_URL", "https://social.running.cafe")

    if not access_token or not api_base_url:
        logger.error(
            "You must set both a MASTODON_ACCESS_TOKEN and MASTODON_BASE_URL environment variable"
        )
        exit(1)

    return Mastodon(access_token=access_token, api_base_url=api_base_url)


if __name__ == "__main__":
    start_http_server(10000)
    posts_scraped_counter = Counter(
        "keithbot_posts_scraped", "Posts downloaded from Twitter"
    )
    posts_posted_counter = Counter("keithbot_posts_posted", "Posts posted to Mastodon")
    posts_errors_counter = Counter(
        "keithbot_posts_errors", "Posts that failed to post to Mastodon"
    )

    while True:
        # try:
        client = Client()
        bluesky_username = os.environ.get("BLUESKY_USERNAME")
        bluesky_password = os.environ.get("BLUESKY_PASSWORD")

        if not bluesky_username or not bluesky_password:
            logger.error(
                "You must set both a BLUESKY_USERNAME and BLUESKY_PASSWORD environment variable"
            )
            exit(1)

        profile = client.login(bluesky_username, bluesky_password)
        logger.debug("Logged in as ", profile.display_name)
        handle = "keithdunn.bsky.social"
        profile_feed = client.get_author_feed(actor=handle, limit=100)
        post_list = []
        for feed_view in profile_feed.feed:
            # Skip replies
            if feed_view.post.record.reply:
                continue

            # Skips straight reposts
            if feed_view.post.author.handle != handle:
                continue

            text = feed_view.post.record.text
            # Skips posts without #BM100
            if "#BM100" not in text:
                continue

            id = feed_view.post.cid
            timestamp = feed_view.post.record.created_at

            post_dict = {
                "text": text,
                "id": id,
                "image_urls": [],
                "quote_post_url": None,
                "link_url": None,
                "timestamp": timestamp,
            }

            if feed_view.post.record.embed:
                embed = feed_view.post.embed
                if "app.bsky.embed.external" in embed.py_type:
                    embed_uri = embed.external.uri
                    post_dict["link_url"] = embed_uri
                elif "app.bsky.embed.record" in embed.py_type:
                    embed_post = client.get_posts([embed.record.uri]).posts[0]
                    embed_post_handle = embed_post.author.handle
                    embed_post_id = embed_post.uri.split("/")[-1]
                    embed_post_calculated_url = f"https://bsky.app/profile/{embed_post_handle}/post/{embed_post_id}"
                    post_dict["quote_post_url"] = embed_post_calculated_url
                elif "app.bsky.embed.images" in embed.py_type:
                    for image in feed_view.post.embed.images:
                        post_dict["image_urls"].append(image.fullsize)

            post_list.append(post_dict)

        post_list.sort(key=lambda post: post["timestamp"])
        logger.info(f"Got {len(post_list)} posts from BlueSky")
        posts_scraped_counter.inc(len(post_list))
        for post in post_list:
            if not check_post_log(post["id"]):
                status_dict = repost(post)
                if status_dict:
                    posts_posted_counter.inc()
                else:
                    posts_errors_counter.inc()

        sleep(60)
