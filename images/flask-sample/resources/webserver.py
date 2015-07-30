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
import ochopod
import os
import sys
import random
import time

from flask import Flask, request, render_template, send_from_directory
from ochopod.core.fsm import diagnostic

logger = logging.getLogger('ochopod')

web = Flask(__name__)


if __name__ == '__main__':

    try:

        #
        # - parse our ochopod hints
        # - enable CLI logging
        # - parse our $pod settings (defined in marathon.yml)
        #
        env = os.environ
        hints = json.loads(env['ochopod'])
        ochopod.enable_cli_log(debug=hints['debug'] == 'true')
        settings = json.loads(env['pod'])

        threads = 0

        @web.route('/threads')
        def _threads():
            global threads
            threads += 1
            
            try:
                
                return json.dumps({'threads': threads})
            
            except Exception as e:

                return {'Exception': e}, 500

            finally:

                threads -= 1

        @web.route('/static/<path:path>')
        def _static(path):
            global threads
            threads += 1

            try:

                time.sleep(random.randrange(10, 50, 5)/10.0)
                return send_from_directory('static', path)

            except Exception as failure:
                logger.error('unexpected failure while receiving -> %s' % diagnostic(failure))
                return '', 500

            finally:

                threads -= 1

        @web.route('/stats', methods=['GET'])
        def _in():
            global threads
            threads += 1
            
            try:

                time.sleep(random.randrange(10, 50, 5)/10.0)
                chain = request.access_route + [request.remote_addr]
                host = chain[0]
                lines = \
                    [
                        settings['welcome'],
                        'container running @ %s (%s)' % (hints['node'], hints['ip']),
                        'http request from %s' % host
                    ]

                return json.dumps({'out': '<br/>'.join(lines)})

            except Exception as failure:

                logger.error('unexpected failure while receiving -> %s' % diagnostic(failure))
                return '', 500

            finally:

                threads -= 1

        @web.route('/')
        def index():
            global threads
            threads += 1

            try:

                time.sleep(random.randrange(10, 50, 5)/10.0)
                #
                # - index.html contains all the jquery magic that will run the shell and
                #   use ajax to I/O with us
                #
                return render_template('index.html')

            except Exception as failure:
                logger.error('unexpected failure while receiving -> %s' % diagnostic(failure))
                return '', 500

            finally:

                threads -= 1

        #
        # - run our flask endpoint on TCP 9000
        #
        web.run(host='0.0.0.0', port=9000, threaded=True)

    except Exception as failure:

        logger.fatal('unexpected condition -> %s' % diagnostic(failure))

    finally:

        sys.exit(1)