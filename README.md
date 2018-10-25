This script fetches opened pull requests from BitBucket repository, checks if they are not
approved yet and title of a PR doesn't include some 'ignore' words and finally
sends reminder to reviewers into slack channel. Required credentials for bitbucket, slack and
words say that PR should be ignored (optional) in .env file.

Run Script
===========

To run script you need to have Python 3 installed. Then do the following:

* `pip install -r requirements.txt`
* Copy .env-sample to .env (it's git-ignored) and fill values for keys in .env
* Run scripts `python <script name>`

As slack-pr-reminder only runs once and exits, it's recommended to run it regularly using for
example a cronjob.

Example that runs slack-pr-reminder every day at 10:00:

0 10 * * * slack-pr-reminder