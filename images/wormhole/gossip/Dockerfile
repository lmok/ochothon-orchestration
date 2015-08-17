FROM autodeskcloud/pod:1.0.2

RUN apt-get update && apt-get -y install python-pip vim

ADD resources/log.cfg /opt/gossip/
ADD resources/gossip.py /opt/gossip/
ADD resources/supervisor /etc/supervisor/conf.d
CMD /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf