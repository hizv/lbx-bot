# Letterboxd Discord Bot

# Features
* Get information on a film from the Letterboxd database along with average rating for the guild if any
* Follow guild members' diary entries and post updates in the channel set by the moderator
* Get random film from your watchlist
* Get information on a crew member (director, actor, etc.) from Imdb
* Get random film from a Letterboxd list
* See all the people in the guild who know a film, and the ratings they gave it
* Get a list of the highest rated or most popular films in the guild

# Built with
* [discord.py](https://github.com/Rapptz/discord.py)
* [Python wrapper](https://github.com/bobtiki/letterboxd) for [Letterboxd API](http://api-docs.letterboxd.com)
* sqlite3 with [aiosqlite](https://github.com/omnilib/aiosqlite) for storing users' Letterboxd IDs
* imdbpie, imdbpy and wikipedia for crew information
* BeautifulSoup for scraping user ratings
* MongoDB for storing the user ratings, inspired by [Sam Learner](https://github.com/sdl60660/letterboxd_recommendations)
* fuzzywuzzy for list matching
* markdownify

# Previously used
* [Feedparser](https://github.com/kurtmckee/feedparser) for tracking diary activity using RSS
  * Later switched to its async version [feedparser-data](https://gitlab.com/foxmask/feedparser-data)
    * Currently using the Letterboxd API
    
