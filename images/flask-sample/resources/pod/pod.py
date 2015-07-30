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
from requests import get
from ochopod.bindings.ec2.marathon import Pod
from ochopod.models.piped import Actor as Piped
from ochopod.models.reactive import Actor as Reactive
from ochopod.core.utils import merge, retry
from random import choice

logger = logging.getLogger('ochopod')

if __name__ == '__main__':

    class Strategy(Piped):

        cwd = '/opt/flask'
        checks = 5
        check_every = 1
        metrics = True

        def sanity_check(self, pid):
            
            #
            # - Randomly decide to be stressed  
            # - Curl to the Flask in subprocess to check number of threaded requests running.
            #
            @retry(timeout=30.0, pause=0)
            def _self_curl():
                reply = get('http://localhost:9000/threads')
                code = reply.status_code
                assert code == 200 or code == 201, 'Self curling failed'
                return merge({'stressed': choice(['Very', 'Nope'])}, json.loads(reply.text))

            return _self_curl()

        def configure(self, _):

            return 'python -u webserver.py', {}


    Pod().boot(Strategy)