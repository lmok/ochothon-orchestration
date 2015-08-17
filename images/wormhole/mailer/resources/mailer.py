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
import json
import logging
import sys
import time
import requests
import argparse
from logging import DEBUG, INFO, Formatter
from logging.config import fileConfig
from logging.handlers import RotatingFileHandler
from os import environ
from os.path import basename, expanduser, isfile, dirname
from ochopod.core.fsm import diagnostic
from ochopod.core.utils import retry, shell
from pykka import ThreadingActor, ThreadingFuture, Timeout, ActorRegistry
from flask import Flask, request, make_response

web = Flask(__name__)

#: the location on disk used for reporting back to the CLI (e.g. our rotating file log)
LOG = '/var/log/ochopod.log'

#
# - load our logging configuration from resources/log.cfg
# - make sure to not reset existing loggers
#
fileConfig('/opt/mailer/log.cfg', disable_existing_loggers=False)

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

#
# - switch all handlers to DEBUG if requested
#
if web.debug:
    for handler in logger.handlers:
        handler.setLevel(DEBUG)


class Mailer(ThreadingActor):

    def __init__(self, remote, cluster, checkpoints={}, period=1, on_update=True):

            super(Mailer, self).__init__() 

            self.cluster = cluster
            self.remote = remote
            self.checkpoints = checkpoints
            self.period = period
            self.on_update = on_update

    def on_start(self):

        logger.info('Starting Mailer...')
        
        #
        # TODO: ttell ocho* cluster mailer started
        #

    def on_receive(self, msg):

        if 'action' in msg:

            if msg['action'] == 'insert':

                #
                # - Will be used to update checkpoints
                #
                self.checkpoints.update(msg['data'])

                self.actor_ref.tell({'action' : 'send'} if self.on_update else {'action': 'spin'})

            elif msg['action'] == 'delete':

                #
                # - Will be used to delete checkpoints entirely
                #
                for key in msg['data'].keys():

                    del self.checkpoints[key]

                self.actor_ref.tell({'action' : 'send'} if self.on_update else {'action': 'spin'})

            elif msg['action'] == 'retrieve':

                return self.checkpoints

            elif msg['action'] == 'send':

                #
                # - Send checkpoints to the mailbox
                #
                logger.info('Sending...')
                #js = remote('ping %s %s-j' % (cluster, json.loads(self.checkpoints)))

            elif msg['action'] == 'spin':

                pass

    def on_stop(self):

        logger.info('Stopping Mailer...')

        #
        # TODO: tell ocho* cluster mailer stopped
        #

if __name__ == '__main__':

    try:

        parser = argparse.ArgumentParser()
        parser.add_argument('--portal', help='Portal IP for cluster', default=None)
        parser.add_argument('-p', '--period', help='seconds interval', default=1)
        parser.add_argument('-c', '--cluster', help='Regex to which messages are pinged')
        parser.add_argument('-a', '--auto', help='send updates whenever checkpoints are updated', default=True)
        args = parser.parse_args()

        portal = environ['PORTAL'] if 'PORTAL' in environ else args.portal

        def _remote(cmdline):

            #
            # - this block is taken from cli.py in ochothon
            # - in debug mode the verbatim response from the portal is dumped on stdout
            #
            now = time.time()
            tokens = cmdline.split(' ')
            files = ['-F %s=@%s' % (basename(token), expanduser(token)) for token in tokens if isfile(expanduser(token))]
            line = ' '.join([basename(token) if isfile(expanduser(token)) else token for token in tokens])
            logger.debug('"%s" -> %s' % (line, portal))
            snippet = 'curl -X POST -H "X-Shell:%s" %s %s/shell' % (line, ' '.join(files), portal)
            code, lines = shell(snippet)
            assert code is 0, 'i/o failure (is the proxy portal down ?)'
            js = json.loads(lines[0])
            elapsed = time.time() - now
            logger.debug('<- %s (took %.2f seconds) ->\n\t%s' % (portal, elapsed, '\n\t'.join(js['out'].split('\n'))))
            return js

        #
        # - Prepare mailer actor
        #
        mailer = Mailer(_remote, period=args.period, cluster=args.cluster, on_update=args.auto)
        ref = mailer.start(_remote, period=args.period, cluster=args.cluster, on_update=args.auto)

        @web.route('/update', methods=['POST'])
        def _update_checkpoint():
            """
            Update key, val pair in checkpoints
            """

            ref.tell({'action': 'insert', 'data': request.form})
            response = make_response(json.dumps({'success': True, 'message': 'Actor told to update'}))
            response.headers["Content-type"] = "application/json"
            return response

        @web.route('/delete', methods=['POST'])
        def _replace_checkpoint():
            """
            Delete a key, val pair from checkpoints
            """

            ref.tell({'action': 'delete', 'data': request.form})
            response = make_response(json.dumps({'success': True, 'message': 'Actor told to delete'}))
            response.headers["Content-type"] = "application/json"
            return response

        @web.route('/retrieve', methods=['GET'])
        def _retrieve_checkpoint():
            """
            Get checkpoints
            """

            fut = ref.ask(message={'action': 'retrieve'}, timeout=1)
            response = make_response(json.dumps({'success': True, 'message': fut}))
            response.headers["Content-type"] = "application/json"
            return response

        #
        # - run our flask endpoint on TCP 9000
        #
        web.run(host='0.0.0.0', port=9000, threaded=True)

    except Exception as failure:

        logger.info('unexpected condition -> %s' % diagnostic(failure))

    finally:

        sys.exit(1)