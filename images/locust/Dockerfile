FROM autodeskcloud/pod:1.0.2

#
# - add pip, pyyaml & redis
#
RUN apt-get update && apt-get -y install python-pip python-dev vim
RUN pip install --no-use-wheel --upgrade distribute
RUN pip install locustio

#
# - add our spiffy pod script + the locust code itself
# - add our supervisor script
# - start supervisor
#
ADD resources/pod /opt/locust/pod
ADD resources/locustfile.py /opt/locust/
ADD resources/supervisor /etc/supervisor/conf.d
CMD /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf