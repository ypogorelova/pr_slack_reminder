"""
This script fetches opened pull requests from BitBucket repository, checks if they are not 
approved yet and title of a PR doesn't include some 'ignore' words and finally it
sends reminder to reviewers into slack channel. Required credentials for bitbucket, slack and 
words say that PR should be ignored (optional) in .env file.
"""
import argparse
import csv
import datetime
import json
import logging
import os
import requests
import sys

import functools
from dotenv import Dotenv

BB_URL = 'http://git.domain.net/rest/api/1.0/projects/{repo}/pull-requests'
REPO = ''
SLACK_CHANNEL = ''
PR_URL = 'http://git.domain.net/projects/{repo}/pull-requests/'
LOG_FILENAME = 'pr.log'
PR_LAST_UPDATED = 5*60*60

dotenv = Dotenv(os.path.join(os.path.dirname(__file__), ".env"))
os.environ.update(dotenv)

logging.basicConfig(filename=LOG_FILENAME, level=logging.INFO)
ignore = os.environ.get('IGNORE_WORDS')
IGNORE_WORDS = ignore.split(',') if ignore else []

try:
    SLACK_WEBHOOK_URL = os.environ['SLACK_WEBHOOK_URL']
    BB_USER = os.environ['BB_USER']
    BB_PASS = os.environ['BB_PASSWORD']
except KeyError as error:
    sys.stderr.write('Please set the environment variable {0}'.format(error))
    sys.exit(1)

INITIAL_MESSAGE = """
Hi! There's a few open pull requests waiting for your review. 
You should take a look at:
"""


def is_valid_title(title):
    """
    Checks if title doesn't include some 'ignore' words. Ignore words should be added into 
    .env file.
    :param title: pull request title
    """
    return not any(ignored_word.lower() in title.lower() for ignored_word in IGNORE_WORDS)


@functools.lru_cache(maxsize=1)
def match_emails_with_slack_names(filename):
    """
    Match emails of reviewers with their slack names
    :param filename: csv file that has accordance between emails and slack names
    :return: list of dicts with 'email' and 'slack' keys
    """
    users = []

    people = csv.DictReader(
        open(
            os.path.join(os.path.dirname(__file__), filename),
            'r'
        )
    )

    for person in people:
        slack = person.get('slack')
        email = person.get('email')
        if email and slack:
            users.append({'slack': slack, 'email': email})
    return users


def get_reviewers_list_if_not_approved(pull):
    """
    Fetches reviewers from pull request, checks if no one already approve the pull request and 
    returns reviewers list
    :param pull: bb pull request
    :return: list of reviewers emails
    """
    reviewers_names = []
    reviewers = pull['reviewers']

    for reviewer in reviewers:
        if reviewer['approved']:
            return None
        else:
            reviewers_names.append(reviewer['user']['emailAddress'])
    return reviewers_names


def get_pull_requests_info(pull_request):
    """
    Fetches pull request's author, title, url, last updated time and list of reviewers.
    :param pull_request: bb pull request
    :return: dict of pr details
    """
    pr_details = {}
    users = match_emails_with_slack_names('people.csv')
    users_slack = []
    reviewers = get_reviewers_list_if_not_approved(pull_request)
    if reviewers:
        for reviewer in reviewers:
            for user in users:
                if user['email'] == reviewer:
                    users_slack.append('@'+user['slack'])

        if is_valid_title(pull_request['title']):
            creator = pull_request['author']['user']['name']
            id = pull_request['id']
            pull_url = PR_URL.format(repo=REPO)+str(id)
            last_updated = pull_request['updatedDate']
            time = datetime.datetime.fromtimestamp(last_updated/1000).strftime('%Y-%m-%d %H:%M')
            dif = (datetime.datetime.now(datetime.timezone.utc) -
                   datetime.datetime.fromtimestamp(last_updated/1000, datetime.timezone.utc))
            if dif.total_seconds() > PR_LAST_UPDATED:
                logging.info('Last updated was {} sec ago'.format(dif.total_seconds()))
                pr_details.update({'author': creator,
                                   'pull_url': pull_url,
                                   'last_updated': time,
                                   'title': pull_request['title'],
                                   'reviewers': ', '.join(map(lambda u: '<{}>'.format(u),
                                                              users_slack))})
            else:
                logging.info('Last updated was recently. {} sec ago'.format(dif.total_seconds()))
                return None
        else:
            logging.info('PR title "{}" includes {} ignore words'.format(pull_request['title'],
                                                                         IGNORE_WORDS))
            return None
    return pr_details


def format_attachment(pr_details):
    """
    Formats pr's info into attachment for slack
    :param pr_details: dict of pr details
    :return: formatted attachment for slack
    """
    return {
        'text': ("Reviewers: {reviewers}\n Author: {author}\nLastUpdated: "
                 "{last_updated}".format(**pr_details)),
        'title': pr_details['title'],
        'title_link': pr_details['pull_url']
    }


def fetch_open_repo_pulls(repo):
    """
    Fetches open pull requests from bb repository.
    :param repo: repository name
    :return: json of pull requests
    """
    url = BB_URL.format(repo=repo)
    pulls = requests.get(url, auth=(BB_USER, BB_PASS), params={'state': 'open'})
    return pulls.json()


def send_to_slack(text, channel):
    """
    Sends formatted to slack channel. 
    :param text: text to be included in attachments section of slack message
    """
    payload = {
        'channel': channel,
        'username': 'Pull Request Reminder',
        'icon_emoji': ':bell:',
        'text': INITIAL_MESSAGE,
        'attachments': text
    }
    response = requests.post(SLACK_WEBHOOK_URL, data=json.dumps(payload))
    if not response.status_code == 200:
        raise Exception('Error sending slack message')


def cli():
    parser = argparse.ArgumentParser(description='Process slack channel and repository.')
    parser.add_argument('-c', '--channel', type=str,
                        help='slack channel', default=SLACK_CHANNEL, metavar='repo')
    parser.add_argument('-r', '--repo', type=str,
                        help='bitbucket repository', default=REPO, metavar='channel')
    args = parser.parse_args()

    pulls = fetch_open_repo_pulls(args.repo)
    logging.info('Fetching pull requests {}'.format(pulls))
    attachments = []
    if pulls['size']:
        for pull in pulls['values']:
            lines = get_pull_requests_info(pull)
            if lines:
                text = format_attachment(lines)
                attachments.append(text)
    if attachments:
        logging.info('Message is ready for slack {}'.format(attachments))
        send_to_slack(attachments, args.channel)


if __name__ == '__main__':
    cli()
