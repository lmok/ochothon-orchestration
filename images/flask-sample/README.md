## Ochothon flask sample

### Overview

This project is a simple [**Docker**](https://www.docker.com/) container definition that can be run on the
[**Ochothon**](https://github.com/autodesk-cloud/ochothon) PaaS. It of course requires a functional cluster running
the [**Marathon**](https://mesosphere.github.io/marathon/) framework.

I just implemented a trivial REST endpoint using the fantabulous [**Flask**](http://flask.pocoo.org/). If you plan on
using a VPC make sure this container lands on a public facing instance.


### Deploy it !

Make sure you installed [**Ochothon**](https://github.com/autodesk-cloud/ochothon) first. Then simply use its CLI and
invoke the **deploy** tool, the image being already uploaded to the hub under _paugamo/marathon-ec2-flask-sample_. For
instance:

```
$ ./cli.py
welcome to the ocho CLI ! (CTRL-C to exit)
> deploy marathon-ec2-flask-sample/marathon.yml
100% success (spawned 1 pods)
```

Then look up what port 9000 is mapped to and use your browser ! For instance:

```
> port 9000 *sample
<*sample> -> 100% replies (1 pods total) ->

pod                       |  node IP         |  TCP
                          |                  |
marathon.flask-sample #0  |  54.144.138.148  |  9094
```

You should see a pretty picture with some text snippets. Enjoy !

### Support

Contact autodesk.cloud.opensource@autodesk.com for more information about this project.


### License

© 2015 Autodesk Inc.
All rights reserved

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.