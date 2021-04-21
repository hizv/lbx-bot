import asyncio
import requests
from pprint import pprint
import time
import sys

from aiohttp import ClientSession
from bs4 import BeautifulSoup

import pymongo
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from config import conn_url

def get_conn_url(db_name):
    return conn_url + db_name + '?retryWrites=true&w=majority'

async def fetch(url, session, input_data={}):
    async with session.get(url) as response:
        return await response.read(), input_data

def get_page_count(username):
    url = "https://letterboxd.com/{}/films/by/date"
    r = requests.get(url.format(username))

    soup = BeautifulSoup(r.text, "lxml")

    body = soup.find("body")
    if "error" in body["class"]:
        return -1

    try:
        page_link = soup.findAll("li", attrs={"class", "paginate-page"})[-1]
        num_pages = int(page_link.find("a").text.replace(',', ''))
    except IndexError:
        num_pages = 1

    return num_pages

async def get_page_counts(lb_ids, users_cursor):
    url = "https://letterboxd.com/{}/films/"
    tasks = []

    async with ClientSession() as session:
        for lb_id in lb_ids:
            task = asyncio.ensure_future(fetch(url.format(lb_id), session, {"lb_id": lb_id}))
            tasks.append(task)

        responses = await asyncio.gather(*tasks)

        for response in responses:
            soup = BeautifulSoup(response[0], "lxml")
            try:
                page_link = soup.findAll("li", attrs={"class", "paginate-page"})[-1]
                num_pages = int(page_link.find("a").text.replace(',', ''))
            except IndexError:
                num_pages = 1

            users_cursor.update_one({"lb_id": response[1]['lb_id']}, {"$set": {"num_ratings_pages": num_pages}})


async def generate_ratings_operations(response, send_to_db=True, return_unrated=False):

    # Parse ratings page response for each rating/review, use lxml parser for speed
    soup = BeautifulSoup(response[0], "lxml")
    reviews = soup.findAll("li", attrs={"class": "poster-container"})

    # Create empty array to store list of bulk operations or rating objects
    operations = []

    # For each review, parse data from scraped page and append an UpdateOne operation for bulk execution or a rating object
    for review in reviews:
        movie_id = review.find('div', attrs={"class", "film-poster"})['data-target-link'].split('/')[-2]

        rating = review.find("span", attrs={"class": "rating"})
        if not rating:
            if return_unrated == False:
                continue
            else:
                rating_id = -1
        else:
            rating_class = rating['class'][-1]
            rating_id = int(rating_class.split('-')[-1])
            if response[1]["lb_id"] in ['hizv', 'ketchupin']:
                rating_id *= 1.25

        rating_object = {
                    "movie_id": movie_id,
                    "rating_id": rating_id,
                    "lb_id": response[1]["lb_id"]
                }

        # If returning objects, just append the object to return list
        if not send_to_db:
            operations.append(rating_object)
        # Otherwise return an UpdateOne operation to bulk execute
        else:
            operations.append(UpdateOne({
                    "lb_id": response[1]["lb_id"],
                    "movie_id": movie_id
                },
                {
                    "$set": rating_object
                }, upsert=True))

    return operations


async def get_user_ratings(lb_id, db_cursor=None, mongo_db=None, store_in_db=True, num_pages=None, return_unrated=False):
    url = "https://letterboxd.com/{}/films/by/date/page/{}/"

    if not num_pages:
        # Find them in the MongoDB database and grab the number of ratings pages
        user = db_cursor.find_one({"lb_id": lb_id})
        num_pages = user["num_ratings_pages"]

    # Fetch all responses within one Client session,
    # keep connection alive for all requests.
    async with ClientSession() as session:
        tasks = []
        # Make a request for each ratings page and add to task queue
        for i in range(num_pages):
            task = asyncio.ensure_future(fetch(url.format(lb_id, i+1), session, {"lb_id": lb_id}))
            tasks.append(task)

        # Gather all ratings page responses
        scrape_responses = await asyncio.gather(*tasks)

    # Process each ratings page response, converting it into bulk upsert operations or output dicts
    tasks = []
    for response in scrape_responses:
        task = asyncio.ensure_future(generate_ratings_operations(response, send_to_db=store_in_db, return_unrated=return_unrated))
        tasks.append(task)

    parse_responses = await asyncio.gather(*tasks)

    # Concatenate each response's upsert operations/output dicts
    upsert_operations = []
    for response in parse_responses:
        upsert_operations += response

    if not store_in_db:
        return upsert_operations

    # Execute bulk upsert operations
    try:
        if len(upsert_operations) > 0:
            # Create/reference "ratings" collection in db
            ratings = mongo_db.ratings
            ratings.bulk_write(upsert_operations, ordered=False)
    except BulkWriteError as bwe:
        pprint(bwe.details)


async def get_ratings(lb_ids, db_cursor=None, mongo_db=None, store_in_db=True):
    start = time.time()

    # Loop through each user
    for i, lb_id in enumerate(lb_ids):
        print(i, lb_id, round((time.time() - start), 2))
        await get_user_ratings(lb_id, db_cursor=db_cursor, mongo_db=mongo_db, store_in_db=store_in_db, return_unrated=True)


def main():
    # Connect to MongoDB Client
    db_name = sys.argv[1]
    client = pymongo.MongoClient(get_conn_url(db_name))

    # Find letterboxd database and user collection
    db = client[db_name]
    users = db.users
    films = db.films
    ratings = db.ratings
    if len(sys.argv) < 3:
        all_users = users.find({})
        all_lb_ids = [x['lb_id'] for x in all_users]
        loop = asyncio.get_event_loop()
        # Find number of ratings pages for each user and add to their Mongo document (note: max of 128 scrapable pages)
        future = asyncio.ensure_future(get_page_counts(all_lb_ids, users))
        loop.run_until_complete(future)

        # Find and store ratings for each user
        future = asyncio.ensure_future(get_ratings(all_lb_ids, users, db))
        loop.run_until_complete(future)

    # Update rating avg
        for movie_id in ratings.distinct('movie_id'):
            total, r_count, ur_count = 0, 0, 0
            for rating in ratings.find({'movie_id': movie_id}):
                rating_id = rating['rating_id']
                if rating_id != -1:
                    total += rating_id
                    r_count += 1
                else:
                    ur_count += 1
            avg = total/r_count if r_count > 0 else 0
            film = {
                'movie_id': movie_id,
                'guild_avg': avg,
                'rating_count': r_count,
                'watch_count': (r_count + ur_count)
            }
            pprint(film)
            films.update_one({
                'movie_id': movie_id
            },
            {
                "$set": film
            }, upsert=True)

    else:
        lb_id = users.find({'uid': int(sys.argv[2])})[0]['lb_id']
        num_pages = get_page_count(lb_id)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        future = asyncio.ensure_future(get_user_ratings(lb_id, users, db, num_pages=num_pages))
        print(future)
        loop.run_until_complete(future)

        # Update rating avg
        for movie_id in ratings.find({'uid': int(sys.argv[2])}):
            total, r_count, ur_count = 0, 0, 0
            for rating in ratings.find({'movie_id': movie_id}):
                rating_id = rating['rating_id']
                if rating_id != -1:
                    total += rating_id
                    r_count += 1
                else:
                    ur_count += 1
            avg = total/r_count if r_count > 0 else 0
            film = {
                'movie_id': movie_id,
                'guild_avg': avg,
                'rating_count': r_count,
                'watch_count': (r_count + ur_count)
            }
            pprint(film)
            films.update_one({
                'movie_id': movie_id
            },
            {
                "$set": film
            }, upsert=True)


if __name__ == "__main__":
    main()
