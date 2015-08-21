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

from ochopod.bindings.ec2.marathon import Pod
from ochopod.models.piped import Actor as Piped
from ochopod.models.reactive import Actor as Reactive

logger = logging.getLogger('ochopod')

if __name__ == '__main__':

    class Model(Reactive):

        depends_on = ['portal']

    class Strategy(Piped):

        cwd = '/opt/scaler'
        pipe_subprocess = True

        def can_configure(self, cluster):

            #
            # - we need one portal pod
            #
            assert len(cluster.dependencies['portal']) == 1, 'need 1 portal'

        def configure(self, cluster):

            #
            # - look the ochothon portal up @ TCP 9000
            # - update the resulting connection string into /opt/scaler.portal
            # - this will be used by the scaler to poll and scale
            #
            with open('/opt/scaler/.portal', 'w') as f:
                f.write(cluster.grep('portal', 9000))
            
            return 'python -u scaler.py', {}

        def signaled(self, js, process):

            #
            # - ping the locust flask with whatever json you need
            #
            @retry(timeout=30.0, pause=0)
            def _self_curl(method, endpoint, payload=None):

                if method == requests.post:

                    reply = method('http://localhost:9001/%s' % endpoint, data=payload)

                else:

                    reply = method('http://localhost:9001/%s' % endpoint, params=payload)
                    
                code = reply.status_code
                assert code == 200 or code == 201, 'Scaler curl failed'
                return json.loads(reply.text)
            
            key, val = js.popitem()
                       
            return _self_curl(requests.get if 'retrieve' in js else requests.post, key, val)

    Pod().boot(Strategy, model=Model)
