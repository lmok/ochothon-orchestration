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
from os import environ
from os.path import basename, expanduser, isfile
from subprocess import Popen, PIPE
from ochopod.core.fsm import diagnostic
from ochopod.core.utils import retry, shell
from pykka import ThreadingActor, ThreadingFuture, Timeout, ActorRegistry
from pykka.exceptions import ActorDeadError

logger = logging.getLogger('ochopod')

class Scaler(ThreadingActor):

    def __init__(self, remote, cluster, haproxy, period=30.0, reps=5):

            super(Scaler, self).__init__() 

            self.remote = remote
            self.cluster = cluster
            self.haproxy = haproxy
            self.period = period
            self.reps = reps

    def on_start(self):

        logger.info('Starting Scaler for %s...' % self.cluster)
        self.actor_ref.tell({'action': 'scale'})

    def on_receive(self, msg):

        if 'action' in msg and msg['action'] == 'scale':

            try:

                _proxyscale(remote=self.remote, 
                            cluster=self.cluster, 
                            haproxy=self.haproxy, 
                            period=self.period, 
                            reps=self.reps)

            except Exception as e:

                logger.warning('Scaler actor exception: %s' % e)

            self.actor_ref.tell({'action': 'scale'})

    def on_stop(self):

        logger.info('Stopping Scaler actor for %s' % cluster)

def output(js, cluster, target):
    """
        Helper for logging results from scale requests.
        :param js: jsonified output returned from a request to the portal using shell().
        :param cluster: the glob pattern used to match a cluster
    """

    if not js['ok']:

        logger.warning('Communication with portal when trying to scale clusters under %s FAILED.' % cluster)
        return

    data = json.loads(js['out'])
    failed = any([not scaled['ok'] for key, scaled in data.iteritems()]) 
       
    import pprint

    if failed:

        logger.warning('Scaling %s FAILURE. Report:\n%s' % (cluster, pprint.pformat(data)))

    else:

        logger.info('Scaling %s to %d instances SUCCESS. Report:\n%s' % (cluster, target, pprint.pformat(data)))

def _proxyscale(remote, cluster, haproxy, period=300.0, reps=5):
    """
        Scales clusters under provided cluster glob patterns according to their load. This is checked through HAproxy pods.

        This example also uses user-defined metrics; the scalees have threaded Flask servers that keep track of the number of open 
        threaded requests at a /threads endpoint. The sanity_check() metrics are::

            from random import choice
            from ochopod.core.utils import merge, retry

            cwd = '/opt/flask'
            checks = 5
            check_every = 1
            metrics = True

            def sanity_check(self, pid):
                
                #
                # - Randomly decide to be stressed  
                # - Curl to Flask in the subprocess to check number of threaded requests running.
                #
                @retry(timeout=30.0, pause=0)
                def _self_curl():
                    reply = get('http://localhost:9000/threads')
                    code = reply.status_code
                    assert code == 200 or code == 201, 'Self curling failed'
                    return merge({'stressed': choice(['Very', 'Nope'])}, json.loads(reply.text))

                return _self_curl()

        General usage for this function:
        :param remote: function used to pass toolset commands to the portal
        :param clusters: list of glob patterns matching particular namespace/clusters for scaling
        :param haproxies: list of glob patterns matching haproxies corresponding to each scalee cluster
        :param period: period (secs) to wait before polling for metrics and scaling
        :param reps: int number of 1-second poll repetitions to get stats from HAProxy
    """ 

    assert period > reps, "A period of %d seconds doesn't allow for %d x 1 second polling repetitions." % (period, reps)

    #
    # - Unit and limits by and to which instance number is scaled
    #
    unit =  1
    lim =  40

    #
    # - Max and min acceptable session rate (sessions/second -- see HAProxy stats parameters) PER POD
    # - Max and min acceptable response rate (threaded response/second) per POD if using flask samples
    #
    ceiling_sessions = 15
    floor_sessions = 5
    ceiling_threads = 15
    floor_threads = 5

    #
    # - Check stats this many times to get an average of session rate (since HAProxy only uses 1 second intervals)
    # - I.e. 5 repetitions averages session rates 5 times with a 1 sec sleep between
    #
    reps = reps

    #
    # - If pods were recently scaled, sleep for half the time to re-poll cluster status quickly
    #
    recent = False

    #
    # - Find our HAProxy instance
    #
    js = remote('port 9002 %s -j' % haproxy)

    if not js['ok']:

        logger.warning('Communication with portal when looking for HAProxy %s FAILED' % haproxy)
        return

    outs = json.loads(js['out'])

    if not len(outs) == 1:

        logger.warning('Did not find 1 HAProxy under %s (found %d)' % (haproxy, len(outs)))
        return
    
    key = outs.keys()[0]

    url = '%s:%s' % (outs[key]['ip'], outs[key]['ports'])

    #
    # - Average sessions/second rate over reps # of repetitions
    #
    avg_sessions = 0
    
    #
    # - Average number of open threads in Flask servers over reps # of repetitions
    #
    avg_threads = 0
    
    #
    # - Number of Flasks
    #
    num = 0

    for i in range(reps):

        time.sleep(1)

        #
        # - Number of pods up & number of pods with running sub processes
        #
        js = remote('grep %s -j' % cluster)
        
        if not js['ok']:

            logger.warning('Communication with portal during pre-scale grep FAILED.')
            continue

        outs = json.loads(js['out'])
        ok = sum(1 for key, data in outs.iteritems() if data['process'] == 'running')
        num = len(outs)
        
        #
        # - Nothing is running yet, try again next time
        #
        if ok == 0:

            logger.warning('Did not find running scalees.')
            continue
        
        #
        # - Running average for threads
        #
        js = remote('poll %s -j' % cluster)
        
        if not js['ok']:

            logger.warning('Communication with portal during metrics gathering FAILED.')
            continue
        
        outs = json.loads(js['out'])
        threads = sum(item['threads'] for key, item in outs.iteritems() if 'threads' in item)
        avg_threads = avg_threads + (float(threads)/ok - avg_threads)/(i + 1)

        #
        # - Get the stats from HAproxy
        # - This will put the csv-formatted stats for the BACKEND servers into a nice little dict 
        # - Look at the haproxy pod for more info (frontend.cfg and local.cfg) 
        #
        @retry(timeout=30.0, pause=0)
        def _backend():   
            reply = requests.get('http://%s/;csv' % url, auth=('olivier', 'likeschinesefood'))
            code = reply.status_code
            assert code == 200 or code == 201, 'Polling HAProxy failed (HTTP %d)' % code
            lines = map(lambda x: x.split(','), reply.text.splitlines())
            return dict(zip(lines[0], filter(lambda x: x[0] == 'local' and x[1] == 'BACKEND', lines)[0]))

        #
        # - Running average for session rate
        #
        backend = _backend()
        avg_sessions = avg_sessions + (float(backend['rate'])/ok - avg_sessions)/(i + 1)

    logger.info('Scaler gathered metrics for %s --> average session rate: %d, average thread rate: %d' % (cluster, avg_sessions, avg_threads))

    #
    # - Scale up/down based on how stressed the cluster is and if resources
    # - are within the limits
    #
    js = {}
    target = 0

    if (avg_sessions > ceiling_sessions or avg_threads > ceiling_threads) and num + unit <= lim:

            target = num + unit
            js = remote('scale %s -f @%d -j' % (cluster, num + unit))
            recent = True

    elif avg_sessions < floor_sessions and avg_threads < floor_threads and num > unit:
            
            target = num - unit
            js = remote('scale %s -f @%d -j' % (cluster, num - unit))
            recent = True

    #
    # - Output for calls to scale
    #
    if not js == {}:

        output(js, cluster, target)

    #
    # - Wait for period minus polling reps
    #
    time.sleep(period - reps if not recent else period/2 - reps)

if __name__ == '__main__':

    scalers = []

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
        # - Check for passed set of scalee clusters, haproxies, and time period in deployment yaml
        #
        scalees = env['SCALEES'].split(',') if 'SCALEES' in env else []

        haproxies = env['HAPROXIES'].split(',') if 'HAPROXIES' in env else []
            
        period = float(env['PERIOD']) if 'PERIOD' in env else 60

        #
        # - Get the portal that we found during cluster configuration (see pod/pod.py)
        #
        _, lines = shell('cat /opt/scaler/.portal')
        portal = lines[0]
        assert portal, '/opt/scaler/.portal not found (pod not yet configured ?)'
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

        for cluster, haproxy in zip(scalees, haproxies):

            js = _remote('grep %s -j' % cluster)

            if not js['ok']:

                logger.warning('Scaler: communication with portal during initialisation failed (could not grep %s).' % cluster)
                continue

            data = json.loads(js['out'])

            clusters += [('%s*' % ' #'.join(key.split(' #')[:-1]), haproxy) for key in data.keys()]

        clusters = list(set(clusters))

        #
        # - Initialise the scaler actors and start
        #
        scalers = [[Scaler(_remote, cluster, haproxy, period), cluster, haproxy] for cluster, haproxy in clusters]
        refs = [scaler.start(_remote, cluster, haproxy, period) for scaler, cluster, haproxy in scalers]

    except Exception as failure:

        logger.fatal('Error on line %s' % (sys.exc_info()[-1].tb_lineno))
        logger.fatal('unexpected condition -> %s' % diagnostic(failure))

    finally:

        for scaler in scalers:

            try:
                
                scaler.stop()

            except Exception as e:

                pass

        sys.exit(1)