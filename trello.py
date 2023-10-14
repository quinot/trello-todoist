import click
import requests
import pika
import json
import os

API_KEY = os.getenv("TRELLO_API_KEY")
API_TOKEN = os.getenv("TRELLO_API_TOKEN")
QUEUE = 'trello-cards'


class TrelloClient(object):

    def __init__(self, api_key, api_token):
        self._api_key = api_key
        self._api_token = api_token

    def active_cards_from_list(self, list_id):
        params = {
            'fields': 'id,name,due,desc,idChecklists,visible,dateLastActivity,shortUrl',
            'attachments': 'true',
            'attachment_fields': 'url,isUpload,date'
        }
        cards = self._get(f'/lists/{list_id}/cards', params)
        return cards

    def active_lists(self, board_to_migrate):
        if board_to_migrate is not None:
            board_ids = [board_to_migrate]
        else:
            board_ids = [board["id"] for board in self._active_boards()]

        for board_id in board_ids:
            lists = self._get(f'/boards/{board_id}/lists/')

            for list in lists:
                if not list['closed']:
                    yield list

    def actions_from_card(self, card_id):
        actions = self._get(f'/cards/{card_id}/actions')
        return actions

    def checklist(self, checklist_id):
        return self._get(f'/checklists/{checklist_id}')

    def _active_boards(self):
        boards = self._get('/members/me/boards')
        return filter(lambda b: not b['closed'], boards)

    def _get(self, path, params=None):
        params = {} if params is None else params
        params['key'] = self._api_key
        params['token'] = self._api_token
        r = requests.get('https://api.trello.com/1' + path, params=params)
        return r.json()


def should_migrate(prompt):
    answer = input(prompt)
    answer = 'y' if answer == '' else answer
    return answer.lower() == 'y'


def trello_lists_to_migrate(trello, board):
    for list in trello.active_lists(board):
        if should_migrate(f'Do you want to migrate {list["name"]}? [y]/n '):
            yield (list['id'], list['name'])


def trello_card_to_todoist_comments(trello, card):
    # Attachments

    if card['attachments'] is not None:
        for attachment in card['attachments']:
            if not attachment['isUpload']:
                yield {
                    "content": attachment['url'],
                    "posted_at": attachment["date"],
                }

    # Card comments

    for action in trello.actions_from_card(card['id']):
        if action['type'] == 'commentCard':
            yield {
                "content": action['data']['text'],
                "posted_at": action["date"],
            }


def trello_checklists_to_todoist_subtasks(trello, card):
    if "idChecklists" not in card:
        print(card)
        raise Exception("No checklists found")
    for checklist_id in card["idChecklists"]:
        checklist = trello.checklist(checklist_id)
        prefix = f'{checklist["name"]}: ' if len(card["idChecklists"]) > 1 else ''

        for item in checklist["checkItems"]:
            yield {
                "name": f'{prefix}{item["name"]}',
                "is_completed": item["state"] == "complete",
                "due": item["due"]
            }

@click.command()
@click.option('--board', type=str, default=None, help='Board ID')
def main(board):
    trello = TrelloClient(API_KEY, API_TOKEN)
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE, durable=True)

    lists = list(trello_lists_to_migrate(trello, board))

    for (id, name) in lists:
        print(f'Migrating cards from {name}')

        cards = trello.active_cards_from_list(id)
        for card in cards:
            print('Migrating', card)
            message = {
                'id': card['id'],
                'name': card['name'],
                'due': card['due'],
                'desc': card['desc'],
                'origin': f"*From [Trello]({card['shortUrl']})*",
                'list_name': name,
                'list_id': id,
                'comments': list(trello_card_to_todoist_comments(trello, card)),
                'subtasks': list(trello_checklists_to_todoist_subtasks(trello, card)),
            }
            message = json.dumps(message)
            channel.basic_publish(exchange='',
                        routing_key=QUEUE,
                        body=message,
                        properties=pika.BasicProperties(
                            delivery_mode=2
                        ))

    connection.close()


if __name__ == '__main__':
    main()
