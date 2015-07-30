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
import os

from jinja2 import Environment, FileSystemLoader
from ochopod.bindings.ec2.marathon import Pod
from ochopod.models.piped import Actor as Piped
from ochopod.models.reactive import Actor as Reactive
from os.path import join, dirname

logger = logging.getLogger('ochopod')


if __name__ == '__main__':

    #
    # - load our pod configuration settings
    # - this little json payload is packaged by the marathon toolset upon a push
    # - is it passed down to the container as the $pod environment variable
    #
    cfg = json.loads(os.environ['pod'])

    class Model(Reactive):

        depends_on = [cfg['target']]

    class Strategy(Piped):

        cwd = '/opt/haproxy'
        pipe_subprocess = True

        def can_configure(self, cluster):

            #
            # - we need at least one downstream url to redirect traffic to
            #
            assert cluster.grep(cfg['target'], cfg['port']), 'need 1+ downstream listener'

        def tear_down(self, running):

            #
            # - for a kill to shut the proxy down
            #
            running.kill()

        def configure(self, cluster):

            #
            # - grep our listeners
            # - render into our 'local' backend directive (which is a standalone file)
            #
            urls = cluster.grep(cfg['target'], cfg['port']).split(',')
            env = Environment(loader=FileSystemLoader(join(dirname(__file__), 'templates')))
            logger.info('%d downstream urls ->\n - %s' % (len(urls), '\n - '.join(urls)))
            mappings = \
                {
                    'listeners': {'listener-%d' % index: endpoint for index, endpoint in enumerate(urls)}
                }

            template = env.get_template('local.cfg')
            with open('%s/local.cfg' % self.cwd, 'w') as f:
                f.write(template.render(mappings))

            #
            # - at this point we have both the global/frontend and our default backend
            # - start haproxy using both configuration files
            #
            return '/usr/sbin/haproxy -f frontend.cfg -f local.cfg', {}

        def signaled(self, js, process=None):

            #
            # - this pod can be switched to draining mode when being signaled
            # - the configuration file will be re-written using an alternate template
            # - the pod must then be restarted for the change to take effect
            # - the input YAML payload should be a comma separated list of urls, for instance :
            #
            # urls:
            #   - 127.345.24.100:9000
            #   - 138.12.123.56:9000
            #
            urls = js['urls'].split(',')
            logger.info('rendering draining.cfg (%s)' % js['urls'])
            env = Environment(loader=FileSystemLoader(join(dirname(__file__), 'templates')))
            mappings = \
                {
                    'default': self.hints['namespace'],
                    'listeners': {'listener-%d' % index: endpoint for index, endpoint in enumerate(urls)}
                }

            template = env.get_template('draining.cfg')
            with open('%s/frontend.cfg' % self.cwd, 'w') as f:
                f.write(template.render(mappings))

    Pod().boot(Strategy, model=Model)