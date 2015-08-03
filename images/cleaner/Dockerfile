FROM autodeskcloud/pod:1.0.2

#
# - add pip, pyyaml & redis
#
RUN apt-get update && apt-get -y install python-pip vim
RUN pip install --no-use-wheel --upgrade distribute
RUN pip install redis pyyaml

#
# - add our spiffy pod script + the cleaner code itself
# - add our supervisor script
# - start supervisor
#
ADD resources/pod /opt/cleaner/pod
ADD resources/cleaner.py /opt/cleaner/
ADD resources/supervisor /etc/supervisor/conf.d
CMD /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf