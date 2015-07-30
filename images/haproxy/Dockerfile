FROM autodeskcloud/pod:1.0.2

#
# - install haproxy
#
RUN apt-get update && apt-get -y install haproxy

#
# - add our spiffy pod script + the basic set of haproxy options 
# - add the haproxy supervisor config file
# - start supervisor
#
ADD resources/pod /opt/haproxy/pod
ADD resources/frontend.cfg /opt/haproxy/
ADD resources/supervisor /etc/supervisor/conf.d
CMD /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
