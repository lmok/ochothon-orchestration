#
# Copyright (c) 2015 Autodesk Inc.
# All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# docker run -itd --name linked-mailer lmok/pod-mailer
# docker run -itd --link linked-mailer:mailer lmok/pod-gossip
#
import json
import logging
import sys
import time
import requests
import random
from logging import DEBUG, INFO, Formatter
from logging.config import fileConfig
from logging.handlers import RotatingFileHandler
from os import environ
from ochopod.core.fsm import diagnostic
from pykka import ThreadingActor, ThreadingFuture, Timeout, ActorRegistry

#: the location on disk used for reporting back to the CLI (e.g. our rotating file log)
LOG = '/var/log/ochopod.log'

#
# - load our logging configuration from resources/log.cfg
# - make sure to not reset existing loggers
#
fileConfig('/opt/gossip/log.cfg', disable_existing_loggers=False)

"""
Taken verbatim from Ochopod. Enabels file logging from the mailer; inaccessible through cli.
"""

#
# - add a small capacity rotating log
# - this will be persisted in the container's filesystem and retrieved via /log requests
# - an IOError here would mean we don't have the permission to write to /var/log for some reason (just skip)
#
logger = logging.getLogger('ochopod')
try:
    handler = RotatingFileHandler(LOG, maxBytes=32764, backupCount=3)
    handler.setLevel(INFO)
    handler.setFormatter(Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

except IOError:
    pass

def random_sentence():
    """
    From http://pythonfiddle.com/random-sentence-generator/
    """
    s_nouns = ["A dude", "My mom", "The king", "Some guy", "A cat with rabies", "A sloth", "Your homie", "This cool guy my gardener met yesterday", "Superman"]
    p_nouns = ["These dudes", "Both of my moms", "All the kings of the world", "Some guys", "All of a cattery's cats", "The multitude of sloths living under your bed", "Your homies", "Like, these, like, all these people", "Supermen"]
    s_verbs = ["eats", "kicks", "gives", "treats", "meets with", "creates", "hacks", "configures", "spies on", "retards", "meows on", "flees from", "tries to automate", "explodes"]
    p_verbs = ["eat", "kick", "give", "treat", "meet with", "create", "hack", "configure", "spy on", "retard", "meow on", "flee from", "try to automate", "explode"]
    infinitives = ["to make a pie.", "for no apparent reason.", "because the sky is green.", "for a disease.", "to be able to make toast explode.", "to know more about archeology."]

    return random.choice(s_nouns), random.choice(s_verbs), random.choice(s_nouns).lower() or random.choice(p_nouns).lower(), random.choice(infinitives)

class Gossip(ThreadingActor):

    def __init__(self, mailer):

            super(Gossip, self).__init__() 

            self.mailer = mailer

    def on_start(self):

        logger.info('Starting Gossip...')

        self.actor_ref.tell({'action': 'gossip'})

    def on_receive(self, msg):

        if 'action' in msg:

            if msg['action'] == 'gossip':

                #
                # - Will be used to update checkpoints
                #
                news = random_sentence()
                self.actor_ref.tell({'action': 'send', 'news': news})


            elif msg['action'] == 'send':

                #
                # - Send checkpoints to the mailbox
                #
                logger.info('Sending...')
                channel = random.choice(['a', 'b', 'c'])
                text = requests.post('%s/update' % self.mailer, data={channel: ' '.join(msg['news'])})
                logger.info(text.text)
                time.sleep(10)
                self.actor_ref.tell({'action': 'gossip'})

    def on_stop(self):

        logger.info('Stopping Gossip...')

if __name__ == '__main__':

    try:

        mailer = 'http://%s:%s' % (environ['MAILER_PORT_9000_TCP_ADDR'], environ['MAILER_PORT_9000_TCP_PORT']) if 'MAILER_PORT_9000_TCP_ADDR' in environ and 'MAILER_PORT_9000_TCP_PORT' in environ else 'http://localhost:9000'
        gossip = Gossip(mailer)
        ref = gossip.start(mailer)

        while not gossip.actor_stopped.is_set():

            time.sleep(2)

    except Exception as failure:

        logger.fatal('unexpected condition -> %s' % diagnostic(failure))

    finally:

        sys.exit(1)