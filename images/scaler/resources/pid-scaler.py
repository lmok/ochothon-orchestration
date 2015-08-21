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

from fnamtch import fnmatch
from math import ceil
from os import environ
from os.path import basename, expanduser, isfile
from subprocess import Popen, PIPE

from ochopod.core.fsm import diagnostic
from ochopod.core.utils import retry, shell
from pykka import ThreadingActor, ThreadingFuture, Timeout, ActorRegistry
from flask import Flask, request, make_response

web = Flask(__name__)
logger = logging.getLogger('ochopod')

class Scaler(ThreadingActor):

    def __init__(self, remote, cluster, target=5, band=0.5, tuning={}, limit=35, period=30.0, reps=4):

            super(Scaler, self).__init__() 

            self.stopped = False
            self.remote = remote
            self.cluster = cluster
            self.period = period
            self.reps = reps
            self.target = target
            self.band = band
            self.tuning = tuning
            self.limit = limit
            self.prev = 0
            self.integ = 0

    def on_start(self):

        logger.info('Starting Scaler for %s at %ds periods...' % (self.cluster, self.period))
        self.actor_ref.tell({'action': 'scale'})

    def on_receive(self, msg):
               
        if 'action' not in msg:

            return

        if msg['action'] == 'scale':

            try:
            
                until = self._pid_control(remote=self.remote, 
                            cluster=self.cluster, 
                            target=self.target,
                            band= self.band
                            tuning=self.tuning,
                            limit=self.limit,
                            )
                
            except Exception as e:

                logger.warning('Scaler actor for %s exception: %s' % (self.cluster, diagnostic(e)))
                
            self.actor_ref.tell({'action': 'spin', 'until': until})

        elif msg['action'] == 'spin':

            if time.time() < msg['until']:

                time.sleep(0.1)
                self.actor_ref.tell({'action': spin, 'until': msg['until']})

            elif not self.stopped:

                self.actor_ref.tell({'action': 'scale'})

        elif msg['action'] == 'update':
            
            try:

                for key, val in msg['data']:

                    setattr(self, key, val)

                if self.stopped:

                    self.stopped = False
                    self.actor_ref.tell({'action': 'scale'})

            except Exception as e:

                logger.warning('Scaler actor for %s exception: %s' % (self.cluster, diagnostic(e)))

        elif msg['action'] == 'retrieve':

            return {'target': self.target, 
                    'band': self.band, 
                    'tuning': self.tuning, 
                    'limit': self.limit, 
                    'period': self.period,
                    'reps': self.reps
                    }

        elif msg['action'] == 'stop':

            self.stopped = True

        elif msg['action'] == 'reset':

            self.prev = 0
            self.integ = 0

    def on_stop(self):

        logger.info('Stopping Scaler actor for %s' % self.cluster)

    def _pid_control(self, remote, cluster, target, band, tuning, limit):
        """
        Tuning = {
            k_p: <proportional tuning param>,
            k_i: <intergal tuning param>,
            k_d: <derivative tuning param, usually < 0>
        }
       
        """ 

        assert self.period > self.reps, "A period of %d seconds doesn't allow for %d x 1 second polling repetitions." % (period, reps)
       
        #
        # - Average number of open threads in Flask servers over reps # of repetitions
        #
        avg_threads = 0
        
        #
        # - Number of Flasks; always the latest number after polling
        #
        num = 0

        for i in range(self.reps):

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

                logger.warning('Communication with portal during metrics poll FAILED.')
                continue
            
            outs = json.loads(js['out'])
            threads = sum(item['threads'] for key, item in outs.iteritems() if 'threads' in item)
            avg_threads = avg_threads + (float(threads)/ok - avg_threads)/(i + 1)

        if avg_threads < target - band or avg_threads > target + band:

            logger.info('Scaler gathered metrics for %s --> average thread rate: %d' % (cluster, avg_threads))

            #
            # - Calculated PID parameters
            # - dt (delta time, i.e. period) can be arbitrary due to arbitrary tuning parameters
            #

            error = target - avg_threads

            integ = self.integ + 0.5*self.period*(self.prev + error)

            grad = (error - self.prev)/self.period

            control = tuning['k_p']*error + tuning['k_i']*integ + tuning['k_d']*grad

            pods = int(ceil(control/target))

            # Ignore if pods not in limit
            if pods < 1 or pods > limit:

                continue

            #
            # - Update previous numbers
            #
            self.prev = error
            self.integ = integ

            #
            # - Scale up/down based on how stressed the cluster is and if resources
            # - are within the limits
            #
            js = remote('scale %s -f @%d -j' % (cluster, pods))

            #
            # - Output for calls to scale
            #
            if not js == {}:

                output(js, cluster, target)

        #
        # - Wait for period minus polling reps
        #
        return time.time() + self.period - self.reps

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
        # - Check for passed set of scalee clusters, and time period in deployment yaml
        #
        scalees = env['SCALEES'].split(',') if 'SCALEES' in env else []
        
        literal = env['LITERAL'] in ['True', 'true', 'T', '1', 't'] if 'LITERAL' in env else False
            
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

        for cluster in scalees:

            #
            # - if literal, don't bother grepping
            #
            if literal:

                clusters += [cluster]
                continue

            js = _remote('grep %s -j' % cluster)

            if not js['ok']:

                logger.warning('Scaler: communication with portal during initialisation failed (could not grep %s).' % cluster)
                continue

            data = json.loads(js['out'])

            clusters += ['%s*' % ' #'.join(key.split(' #')[:-1]) for key in data.keys()]

        clusters = list(set(clusters))

        #
        # - Initialise the scaler actors and start
        #
        scalers = [[Scaler(_remote, cluster, period), cluster] for cluster in clusters]
        refs = [[scaler.start(_remote, cluster, period), cluster] for scaler, cluster in scalers]

        def _action(regex, message):

            filtered = filter(lambda (ref, cluster): fnmatch(cluster, regex), refs)
            map(lambda (ref, cluster): ref.tell(message), filtered)
            response = make_response(json.dumps({'success': True, 'message': 'Actors for %s told to /%s' % (' '.join(filtered), message['action'])}))
            response.headers["Content-type"] = "application/json"
            return response

        @web.route('/reset/<regex>', methods=['POST'])
        def _reset(regex):

            return _action(regex, {'action': 'reset'})

        @web.route('/stop/<regex>', methods=['POST'])
        def _update(regex):

            return _action(regex, {'action': 'stop'})

        @web.route('/update/<regex>', methods=['POST'])
        def _replace(regex):

            return _action(regex, {'action': 'update', 'data': request.form})

        @web.route('/retrieve/<regex>', methods=['GET'])
        def _retrieve(regex):

            filtered = filter(lambda (ref, cluster): fnmatch(cluster, regex), refs)
            ret = {cluster: ref.ask(message={'action': 'retrieve'}, timeout=1) for ref, cluster in filtered}
            response = make_response(json.dumps({'success': True, 'message': ret}))
            response.headers["Content-type"] = "application/json"
            return response

        #
        # - run our flask endpoint on TCP 9000
        #
        web.run(host='0.0.0.0', port=9001, threaded=True)

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