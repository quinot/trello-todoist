# trello-todoist
This is a simple project to migrate Trello cards to Todoist tasks:
* Trello lists become Todoist projects (by default) or sections within a project (if using `--lists-as-sections`).
* Card names become task names
* Card description becomes task description
* Card attachment URLs and card comments become task notes
* Checklists become subtasks

RabbitMQ is used as an intermediate steps to separate the export from Trello from the import into Todoist.

First of all:
* Get a Trello API key and API token and set them in environment variables `TRELLO_API_KEY` and `TRELLO_API_TOKEN`
* Get a Todoist API token and set it in environment variable `TODOIST_API_TOKEN`
* Start a RabbitMQ (if you use Docker it could be something like `docker run -p 5672:5672 rabbitmq`)

Now, if you run `trello.py` if will prompt what lists do you want to migrate, for all active boards (or just for one board if using `--board <board-id>`).
Each card will be sent as a message to RabbitMQ.
When you run `todoist.py` it will handle all messages sent from `trello.py`.

Some issues:
* If there is a problem creating the project, it will create cards in *Inbox*.
* If any message fails, it will be `unacked` in RabbitMQ and `todoist.py` should be restarted to reprocess this message
* In the previous scenarion, the message will, probably, be sent to *Inbox*
* The original version had a 5 s delay to work around rate limits in the Todoist API, which I removed
