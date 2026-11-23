# lore-engine

> Third-space Hack club week 6&7!

a discord bot ai assistant built specifically for your friend group that acts like a sassy server historian and gameshow host

a wip website for this bot [here](https://katfishing.dev).

## To Reviewer

> ⚠️**TO REVIEWER**
>
> pls read the description for our latest third-space ship to test the bot. It is currently only available for our private server and hackclub nest application is still pending...


## Features
so far has:
- website, but like idk how to let it be accessible by people other than the host lol
- dc chat indexing
- and the ai works
- trivia (questions based on chat logs or fetched online)
- two truths one lie (based on chat logs or fetches questions online)
- game style update patch notes
- hall of shame thing (wip)
- hall of fame (leaderboard)
- totally not family feud
- higher or lower game (not implemented yet)
- ultra impossible wordle (sentencedle) [pls send help]

## Commands
- /ask = ask anything about the server/members
- /assess = assess members
- /impersonate = impersonate a members to reply to the topic given
- /leaderboard = vote leaderboard for the best quote of the month and year
- /lookup [Search query] [is special] [by user] = lookup a specific quote
- - search_query = specific quote
  - is_special = True is it has been saved, False if auto-logged
  - by_user = specific member
- /nerdle start = start impossible wordle
- /nerdle guess = guess nerdle with this command and MUST END WITH .
- /nerdle status = see the status of the nerdle
- /ping = no explanation needed
- /receipts = uno reverse someone
- /tldr = sum up latest messages (broken for now)
- /trivia - guess who said it
- /type = test your typing speed

## How to get this bot for yourself?
for now you have to self host it, probably won't publish this
1. clone the repo
2. install chromadb and fastapi
3. download and convert dc chat logs into json
4. put the json file into data/raw
5. run the cleanData.py let it do its thing then it should work
6. get urself a dc bot account, invite to your server then plug in the api key
7. also plug in ai api key, the code uses gemini sooo its forced unless u change it
8. Run src/lore-engine.py and your done!

