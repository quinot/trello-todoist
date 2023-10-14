import click
from collections import defaultdict
import json
import pika
import time
import os
from todoist_api_python.api import TodoistAPI, Project, Section

API_TOKEN = os.getenv("TODOIST_API_TOKEN")
QUEUE = 'trello-cards'

class Placeholder(object):
    def __init__(self, id):
        self.id = id
class TodoistClient(object):

    def __init__(self, api_token, dry_run, lists_as_sections, project):
        self._dry_run = dry_run
        self._api = TodoistAPI(api_token)
        self._cache = {
            "id": defaultdict(dict),
            "name": defaultdict(dict),
        }
        projects = self._api.get_projects()
        self._cache["name"]["project"] = {p.name: p for p in projects}

        if lists_as_sections:
            self._project_id = self.find_project(project, None)
            sections = self._api.get_sections(project_id=self._project_id)
            self._cache["name"]["section"] = {s.name: s for s in sections}

    def _find_cached(self, category, name, id):
        for key_type, key in  {"id": id, "name": name}.items():
            if key is not None and key in self._cache[key_type][category]:
                value = self._cache[key_type][category][key]
                if key_type == "name" and id is not None:
                    self._cache["id"][category][id] = value
                return value
        return None

    def _add_cached(self, category, name, id, value):
        self._cache["id"][category][id] = value
        self._cache["name"][category][name] = value

    def find_project(self, name, id):
        project = self._find_cached("project", name, id)
        if project is None:
            project = self._create_project(name, id)
        return project.id

    def find_section(self, name, id):
        section = self._find_cached("section", name, id)
        if section is None:
            section = self._create_section(name, id, self._project_id)
        return section.id

    def _create_section(self, name, id, project_id):
        data = {'name': name, 'project_id': project_id}
        if self._dry_run:
            return Placeholder(id=f"S{id}")
        resp = self._api.add_section(**data)
        print(f"Created section {resp}")
        if resp is not None:
            self._add_cached("section", name, id, resp)
            return resp

        return None

    def _create_project(self, name, id):
        data = {'name': name}
        if self._dry_run:
            return Placeholder(id=f"S{id}")
        resp = self._api.add_project(**data)
        print(f"Created project {resp}")
        if resp is not None:
            self._add_cached("project", name, id, resp)
            return resp

        return None

    def create_task(self, task):
        if self._dry_run:
            print(f"add_task: {task}")
            return f"T{task.__hash__}"
        else:
            resp = self._api.add_task(**task)
            return resp.id

    def create_comment(self, comment):
        if self._dry_run:
            print(f"add_comment: {comment}")
            return
        self._api.add_comment(**comment)

def handle_card(todoist, dry_run, lists_as_sections, project):
    def handle(ch, method, properties, body):
        print('Received', body)
        message = json.loads(body)
        try:
            create_on_todoist(todoist, message, lists_as_sections, project)
            if not dry_run:
                ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print('An error has ocurred', e)

    return handle


def create_on_todoist(todoist, message, list_as_sections, project):
    if list_as_sections:
        task_info = {
            "project_id": todoist.find_project(project, None),
            "section_id": todoist.find_section(message["list_name"], message['list_id'])
        }
    else:
        task_info = {
            "project_id": todoist.find_project(message['list_name'], message['list_id'])
        }

    task_description = message["desc"] or ""
    if task_description:
        task_description += "\n\n"
    task_description += message["origin"]
    task_info.update({
        'content': message['name'],
        'description': task_description,
        'due_datetime': message['due']
    })
    task_id = todoist.create_task(task_info)

    for comment in message['comments']:
        todoist.create_comment({
            'content': comment["content"],
            'task_id': task_id,
            'posted_at': comment["posted_at"],
        })
    for subtask in message['subtasks']:
        todoist.create_task({
            'content': subtask['name'],
            'parent_id': task_id,
            'due_datetime': subtask['due'],
            'is_completed': subtask['is_completed']
        })

@click.command()
@click.option('--dry-run', is_flag=True)
@click.option('--lists-as-sections', is_flag=True, default=False, help='Map lists to sections instead of projects')
@click.option('--project', type=str, default="Inbox", help='Project name (if mapping lists to sections)')
def main(dry_run, lists_as_sections, project):
    todoist = TodoistClient(API_TOKEN, dry_run, lists_as_sections, project)
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()

    channel.queue_declare(queue=QUEUE, durable=True)

    channel.basic_consume(QUEUE, handle_card(todoist, dry_run, lists_as_sections, project))

    print("[*] Waiting for messages. To exit press CTRL+C")
    channel.start_consuming()

if __name__ == '__main__':
    main()