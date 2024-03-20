import asyncio
from twscrape import API, gather, logger
from mastodon import Mastodon
import csv
from time import sleep


api = API()


def repost(tweet):
    field_names = ("id", "date")
    with open("tweets.csv", "a") as tweet_file:
        writer = csv.DictWriter(tweet_file, field_names)
        new_row = {"id": tweet.id, "date": tweet.date}
        writer.writerow(new_row)
    logger.info(
        f"Posting tweet with id {tweet.id} from {tweet.date} with content {tweet.rawContent}"
    )
    mastodon = get_mastodon()
    mastodon.status_post(tweet.rawContent)


def check_tweet_file(tweet_id):
    field_names = ("id", "date")
    with open("tweets.csv", "r") as tweet_file:
        reader = csv.DictReader(tweet_file, field_names)
        for row in reader:
            if row["id"] == str(tweet_id):
                logger.debug("Already tweeted " + str(tweet_id))
                return True
    return False


def get_mastodon() -> Mastodon:
    """Creates an instance of the Mastodon Class

    Returns:
        Mastodon: The instance of the Mastodon Class
    """
    access_token = os.environ.get("MASTODON_ACCESS_TOKEN", "")
    api_base_url = os.environ.get("MASTODON_BASE_URL", "https://social.running.cafe")

    if not access_token or not api_base_url:
        logger.error(
            "You must set both a MASTODON_ACCESS_TOKEN and MASTODON_BASE_URL environment variable"
        )
        exit(1)

    return Mastodon(access_token=access_token, api_base_url=api_base_url)


async def main():
    tweet_list = await gather(api.user_tweets(20826732, limit=20))
    return tweet_list


if __name__ == "__main__":
    while True:
        try:
            tweet_list = asyncio.run(main())
            tweet_list.sort(key=lambda tweet: tweet.id)
            logger.info(f"Got {len(tweet_list)} posts from Twitter")
            for tweet in tweet_list:
                if (
                    (not tweet.quotedTweet)
                    and (not tweet.retweetedTweet)
                    and ("keithdunn" in tweet.url)
                ):
                    if not check_tweet_file(tweet.id):
                        repost(tweet)
        except Exception as e:
            logger.error(e)
        sleep(30)
