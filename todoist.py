import requests
import json
import pika
import time
import os
from todoist_api_python.api import TodoistAPI

API_TOKEN = os.getenv("TODOIST_API_TOKEN")
QUEUE = 'trello-cards'

class TodoistClient(object):

    def __init__(self, api_token):
        self._api = TodoistAPI(api_token)
        self._project_cache = {}
        self._project_names = { p.name: p for p in self._api.get_projects() }
        print(f"Projects: {self._project_names}")

    def create_project(self, name, id):
        if id in self._project_cache:
            return self._project_cache[id]

        if name in self._project_names:
            self._project_cache[id] = self._project_names[name].id
            return self._project_cache[id]

        data = {'name': name}
        resp = self._api.add_project(**data)
        if resp is not None:
            self._project_cache[id] =  resp.id
            return self._project_cache[id]

        return None
        
    def create_task(self, task, id):
        resp = self._api.add_task(**task)
        return resp.id

    def create_comment(self, comment):
        self._api.add_comment(**comment)

def handle_card(todoist):
    def handle(ch, method, properties, body):
        time.sleep(5)
        print('Received', body)
        message = json.loads(body)

        try:
            create_on_todoist(todoist, message)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print('An error has ocurred', e)

    return handle


def create_on_todoist(todoist, message):
    project_id = todoist.create_project(message['project'], 
                                        message['project_id'])
        
    task_id = todoist.create_task({
        'content': message['name'],
        'project_id': project_id,
        'due_datetime': message['due']
    }, message['id'])

    for content in message['notes']:
        todoist.create_comment({
            'content': content,
            'task_id': task_id
        })

if __name__ == '__main__':
    todoist = TodoistClient(API_TOKEN)
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()

    channel.queue_declare(queue=QUEUE, durable=True)

    channel.basic_consume(QUEUE, handle_card(todoist))

    print("[*] Waiting for messages. To exit press CTRL+C")
    channel.start_consuming()
