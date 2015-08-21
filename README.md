# ochothon-orchestration

This is a small project that (hopefully) demos the usefulness of ocho* for orchestrating clustered applications.

----

## Deploying the Demo
1. Follow the setup guide for [Ochothon](https://github.com/autodesk-cloud/ochothon).
2. When the [proxy/portal pod](https://github.com/autodesk-cloud/ochothon/blob/master/dcos.json) is running, open up the [CLI](https://github.com/autodesk-cloud/ochothon/blob/master/cli.py).
3. Deploy the Flask, HAProxy, and Locust IO pods onto your Mesos/Marathon setup using the CLI and provided YAML files. They should use the same namespace, so use commands like::
        
        123.4.5.678> deploy flask-sample.yml -n <app-namespace> 
        123.4.5.678> deploy haproxy.yml -n <app-namespace>
        123.4.5.678> deploy locust.yml -n <app-namespace>

4. Modify, then deploy the Scaler, Watcher, and Cleaner pods using the CLI. The Watcher pod requires configuration for operability with Splunk. Use the same commands above with the appropriate YAML files and **the Portal's namespace**.
5. Figure out the public IP & port mapping of your Locust pod, then use the web UI and crank it up!

        123.4.5.678> port 8089 *locust*

----

## Resources
+ [Ochothon](https://github.com/autodesk-cloud/ochothon) is a set of tools used to deploy containerised applications with an [Ochopod](https://github.com/autodesk-cloud/ochopod) installation.
+ Flask server pods based off of [this flask sample](https://github.com/opaugam/marathon-ec2-flask-sample).