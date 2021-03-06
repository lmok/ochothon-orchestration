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
import logging
import json
import os
from ochopod.bindings.ec2.marathon import Pod
from ochopod.models.piped import Actor as Piped
from ochopod.models.reactive import Actor as Reactive

logger = logging.getLogger('ochopod')

if __name__ == '__main__':

    #
    # - load our pod configuration settings
    # - this little json payload is packaged by the marathon toolset upon a push
    # - is it passed down to the container as the $pod environment variable
    #

    cfg = json.loads(os.environ['pod'])

    class Model(Reactive):

        depends_on = [cfg['haproxy']]

    class Strategy(Piped):

        cwd = '/opt/locust'
        pipe_subprocess = True

        def can_configure(self, cluster):

            #
            # - we need one haproxy pod
            #
            assert cluster.grep(cfg['haproxy'], cfg['port']), 'cluster.grep could not find an HAProxy'
            assert len(cluster.dependencies['haproxy']) == 1, 'need 1 HAproxy'

        def configure(self, cluster):

            #
            # - look for the haproxy at the user-defined port
            #
            urls = cluster.grep(cfg['haproxy'], cfg['port']).split(',')
            
            return 'locust --host=http://%s' % urls[0], {}

    Pod().boot(Strategy, model=Model)