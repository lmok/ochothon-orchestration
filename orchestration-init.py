import json
import requests
import argparse
import cmd
import os
import sys
import time
import csv
from ochopod.core.fsm import diagnostic
from ochopod.core.utils import retry, shell
from os.path import basename, expanduser, isfile
from subprocess import Popen, PIPE
from sys import exit

def poll(remote, period, writer=None, stagnant_pings=15, user_counts=[], pod_counts=[]):
    # want to stop after 10 polls of stagnancy

    # Start polling for nums
    count = stagnant_pings

    while 0 < count:

        prev = time.time()
        
        try:

            js = remote('ping \'{\\"stats/requests\\": {}}\' *locust* -j -v ')

            locusts = {}

            try:
                
                locusts = json.loads(js['out'])
            
            except Exception as e:
                
                locusts = json.loads(js['out'].splitlines()[-1])
            
            users = sum(int(data['user_count']) for locust, data in locusts.iteritems())

            flasks = len(json.loads(remote('grep *clus1.flask* -j')['out'])) + len(json.loads(remote('grep *clus2.flask* -j')['out']))

            js = remote('poll *flask* -j')
            outs = json.loads(js['out'])
            threads = sum(item['threads'] for key, item in outs.iteritems() if 'threads' in item) #/ sum(1 for key, item in outs.iteritems() if 'threads' in item)

            # Decrease if stagnant
            dec = count - 1
            count = dec if (len(pod_counts) > 0 and flasks == pod_counts[-1]) else stagnant_pings

            user_counts += [users]
            pod_counts += [flasks]

            print 'Pods: %s | Users: %s | Threads: %s | Stagnancy: %d' % (flasks, users, threads, count)

            if writer:
                writer.writerow([flasks, users, threads])

            # remaining time left for sleep
            time.sleep(max(0, period + prev - time.time()))

        except Exception as e:

            print 'Error on line %s' % (sys.exc_info()[-1].tb_lineno)
            print e
            continue

    return user_counts, pod_counts

def start(remote, reset, period, nosim, stagnant_pings, graph):

    try:

        now = time.strftime('%b-%d-%H-%M')
        
        management = 'lillio'
        clusters = ['clus1', 'clus2']
        managers = {
            'scaler': 'scaler-lillio.yml',
            'cleaner': 'cleaner-lillio.yml',
            'watcher': 'watcher-lillio.yml',
        }
        pods = {
            'flask-sample': 'flask-olivier.yml',
            'haproxy': 'haproxy-lillio.yml',
            'locust': 'locust-lillio.yml',           
        }

        print 'Deploying app clusters'
        # Ditto for testing clusters
        for cluster in clusters:

            for pod, yaml in pods.iteritems():

                js = remote('grep *%s.%s* -j' % (cluster, pod))

                if not json.loads(js['out']):

                    # use two locust pods for giggles
                    js = remote('deploy %s -n %s -p %d %s' % (yaml, cluster, 2 if pod == 'locust' else 1, '-f' if pod != 'flask-sample' else ''))
                    assert js['ok'], 'Could not deploy %s.%s' % (cluster, pod)

        print 'Deploying management'
        # Deploy management if not already deployed
        for pod, yaml in managers.iteritems():

            js = remote('grep *%s.%s* -j' % (management, pod))

            if not json.loads(js['out']):

                js = remote('deploy %s -n %s -f' % (yaml, management))
                assert js['ok'], 'Could not deploy %s.%s' % (management, pod)

        # Reset everything first
        if reset:

            print 'Resetting...'
            js = remote('off *scaler* --force')
            js = remote('reset *locust* --force')

            for cluster in clusters:

                js = remote('scale *%s.%s* -f @1' %(cluster, 'flask-sample')) 

            js = remote('on *scaler*')

        if nosim:

            return

        with open('%s.csv' % now, 'w', 1) as csvfile:

            print ' ***--- Csv at %s.csv ---***' % now

            writer = csv.writer(csvfile)

            user_counts = []
            pod_counts = []

            # print 'Turning locust on to 1600/0.5'
            # # Switch dem locusts on
            # js = remote('ping \'{\\"swarm\\": {\\"locust_count\\": 1600, \\"hatch_rate\\": 0.5}}\' *locust* -j -v ')

            # user_counts, pod_counts = poll(remote, period, writer=writer, stagnant_pings=stagnant_pings)

            # print 'Locust to 1100/0'
            # # Switch dem locusts to ~ 500 each
            # js = remote('ping \'{\\"swarm\\": {\\"locust_count\\": 1100, \\"hatch_rate\\": 0}}\' *locust* -j -v ')

            # user_counts, pod_counts = poll(remote, period, writer=writer, stagnant_pings=stagnant_pings, user_counts=user_counts, pod_counts=pod_counts)

            print 'Locust to 600/1'
            # Switch dem locusts to ~ 500 each
            js = remote('ping \'{\\"swarm\\": {\\"locust_count\\": 600, \\"hatch_rate\\": 1}}\' *locust* -j -v ')

            user_counts, pod_counts = poll(remote, period, writer=writer, stagnant_pings=stagnant_pings, user_counts=user_counts, pod_counts=pod_counts)

            # print 'Locust to 1600/1'
            # # Switch dem locusts on again
            # js = remote('ping \'{\\"swarm\\": {\\"locust_count\\": 1600, \\"hatch_rate\\": 1}}\' *locust* -j -v ')

            # user_counts, pod_counts = poll(remote, period, writer=writer, stagnant_pings=stagnant_pings, user_counts=user_counts, pod_counts=pod_counts)

            print 'Locust to 100/0.01'
            # Switch dem locusts to ~ 500 each
            js = remote('ping \'{\\"swarm\\": {\\"locust_count\\": 5, \\"hatch_rate\\": 0.01}}\' *locust* -j -v ')

            user_counts, pod_counts = poll(remote, period, writer=writer, stagnant_pings=stagnant_pings, user_counts=user_counts, pod_counts=pod_counts)
            print user_counts
            print pod_counts
            print 'Outputting final rows'

            writer.writerow(user_counts)
            writer.writerow(pod_counts)

        return 0

    except Exception as e:

        print diagnostic(e)
        return 1

    finally:

        print 'Offing locusts'
        js = remote('ping \'{\\"stop\\": {}}\' *locust* -j -v ')

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()

    parser.add_argument('portal', help='Portal IP for cluster')
    parser.add_argument('-g', '--graph', help='show real-time graph', action='store_true')
    parser.add_argument('-r', '--reset', help='reset your setup before swarming', action='store_true')
    parser.add_argument('-p', '--period', help='seconds interval', default=10.0, type=float)
    parser.add_argument('-ns', '--nosim', help='skip the simulation, just deploy', action='store_true')
    parser.add_argument('-s', '--stagnancy', help='number of stagnant pings allowed', default=15, type=int)

    args = parser.parse_args()

    def _remote(cmdline):

        #
        # - this block is taken from cli.py in ochothon
        # - in debug mode the verbatim response from the portal is dumped on stdout
        #
        now = time.time()
        tokens = cmdline.split(' ')
        files = ['-F %s=@%s' % (basename(token), expanduser(token)) for token in tokens if isfile(expanduser(token))]
        line = ' '.join([basename(token) if isfile(expanduser(token)) else token for token in tokens])
        snippet = 'curl -X POST -H "X-Shell:%s" %s %s/shell' % (line, ' '.join(files), args.portal)
        code, lines = shell(snippet)
        assert code is 0, 'i/o failure (is the proxy portal down ?)'
        js = json.loads(lines[0])
        elapsed = time.time() - now
        return js

    start(_remote, args.reset, args.period, args.nosim, args.stagnancy, args.graph)

