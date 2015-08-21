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
import pprint
import json
import logging
import sys
import time
import requests
from os import environ
from os.path import basename, expanduser, isfile
from subprocess import Popen, PIPE
from ochopod.core.fsm import diagnostic
from ochopod.core.utils import retry, shell
from pykka import ThreadingActor, ThreadingFuture, Timeout, ActorRegistry
from pykka.exceptions import ActorDeadError

logger = logging.getLogger('ochopod')

class Cleaner(ThreadingActor):

    def __init__(self, remote, cluster, period=60.0, wait=10.0):

            super(Cleaner, self).__init__() 

            self.remote = remote
            self.cluster = cluster
            self.period = period
            self.wait = wait

    def on_start(self):

        logger.info('Starting Cleaner for %s...' % self.cluster)
        self.actor_ref.tell({'action': 'clean'})

    def on_receive(self, msg):

        if 'action' in msg and msg['action'] == 'clean':

            try:

                _clean(remote=self.remote, 
                        cluster=self.cluster, 
                        period=self.period,
                        wait=self.wait) 

            except Exception as e:

                logger.warning('Cleaner actor for %s exception: %s' % (self.cluster, e))
            
            self.actor_ref.tell({'action': 'clean'})

    def on_stop(self):

        logger.info('Stopping Cleaner actor for %s' % self.cluster)

def _clean(remote, cluster, period=60.0, wait=10.0):
    """
        Cleans dead pods from designated cluster.
    """ 

    print 'Cleaning cluster %s...' % cluster

    #
    # - Check now if there are dead/stopped pods in this cluster
    #
    js = remote('grep %s -j' % cluster)

    if not js['ok']:

        logger.warning('Cleaner: communication with portal during dead check failed (could not grep %s).' % cluster)
        return
       
    data = json.loads(js['out'])

    dead = [key.split(' #')[-1] for key, val in data.iteritems() if val['process'] == 'dead']

    stopped = [key.split(' #')[-1] for key, val in data.iteritems() if val['process'] == 'stopped']

    #
    # - Check again after wait, and take still-dead/stopped pods
    #
    time.sleep(wait)

    js = remote('grep %s -j' % cluster)

    if not js['ok']:

        logger.warning('Cleaner: communication with portal during dead check failed (could not grep %s).' % cluster)
        return
       
    data = json.loads(js['out'])

    dead = list(set(dead) & set([key.split(' #')[-1] for key, val in data.iteritems() if val['process'] == 'dead']))

    stopped = list(set(stopped) & set([key.split(' #')[-1] for key, val in data.iteritems() if val['process'] == 'stopped']))

    #
    # - Kill dead pods
    #
    if dead:

        js = remote('kill %s -i %s -j' % (cluster, ' '.join(dead)))

        if not js['ok']:

            logger.warning('Cleaner: could not kill %s -i %s.' % (cluster, ' '.join(dead)))
            return
        
        data = json.loads(js['out'])

        left = set(map(int, dead)) - set(data[cluster]['down'])

        if not left:

            logger.info('Cleaned (KILLED) %d dead pods for %s SUCCESS. Report:\n%s' % (len(dead), cluster, pprint.pformat(data)))

        else:

            logger.warning('Cleaning dead pods for %s FAILED. Report:\n%s' % (cluster, pprint.pformat(data)))

    #
    # - Reset stopped pods
    #
    if stopped:

        js = remote('reset %s -i %s -j' % (cluster, ' '.join(stopped)))

        if not js['ok']:

            logger.warning('Cleaner: could not reset %s -i %s.' % (cluster, ' '.join(stopped)))
            return
        
        data = json.loads(js['out'])

        if data[cluster]['ok']:

            logger.info('Cleaned (RESET) %d stopped pods for %s SUCCESS. Report:\n%s' % (len(stopped), cluster, pprint.pformat(data)))

        else:

            logger.warning('Cleaning stopped pods for %s FAILED. Report:\n%s' % (cluster, pprint.pformat(data)))

    time.sleep(period - wait)    

if __name__ == '__main__':

    cleaners = []

    try:

        #
        # - parse our ochopod hints
        # - enable CLI logging
        # - pass down the ZK ensemble coordinate
        #
        env = environ
        hints = json.loads(env['ochopod'])
        env['OCHOPOD_ZK'] = hints['zk']
        
        #
        # - Check for passed set of dirty clusters, haproxies, and time period in deployment yaml
        #
        cleaning = env['DIRTY'].split(',') if 'DIRTY' in env else []
        
        literal = env['LITERAL'] in ['True', 'true', 'T', '1', 't'] if 'LITERAL' in env else False

        period = float(env['PERIOD']) if 'PERIOD' in env else 60

        #
        # - Get the portal that we found during cluster configuration (see pod/pod.py)
        #
        _, lines = shell('cat /opt/cleaner/.portal')
        portal = lines[0]
        assert portal, '/opt/cleaner/.portal not found (pod not yet configured ?)'
        logger.debug('using proxy @ %s' % portal)

        #
        # - Remote for direct communication with the portal
        #
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
        # - Check for overlapping clusters matching all glob patterns
        #    
        clusters = []

        for cluster in cleaning:

            #
            # - if literal, don't bother grepping
            #
            if literal:

                clusters += [cluster]
                continue

            js = _remote('grep %s -j' % cluster)

            if not js['ok']:

                logger.warning('Cleaner: communication with portal during initialisation failed (could not grep %s).' % cluster)
                continue

            data = json.loads(js['out'])

            clusters += ['%s*' % ' #'.join(key.split(' #')[:-1]) for key in data.keys()]

        clusters = list(set(clusters))

        #
        # - Initialise the cleaner actors and start
        #
        cleaners = [[Cleaner(_remote, cluster, period), cluster] for cluster in clusters]
        refs = [cleaner.start(_remote, cluster, period) for cleaner, cluster in cleaners]

    except Exception as failure:

        logger.fatal('Error on line %s' % (sys.exc_info()[-1].tb_lineno))
        logger.fatal('unexpected condition -> %s' % diagnostic(failure))

    finally:

        for cleaner in cleaners:

            try:
                
                cleaner.stop()

            except Exception as e:

                pass

        sys.exit(1)