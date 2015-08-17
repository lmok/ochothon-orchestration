FROM autodeskcloud/pod:1.0.2

#
# - add pip, pyyaml & redis
#
RUN apt-get update && apt-get -y install python-pip vim
RUN pip install --no-use-wheel --upgrade distribute
RUN pip install redis pyyaml

#
# - expose port for mailing
#
EXPOSE 9000

#
# - add our spiffy pod script + the mailer code itself
# - add our supervisor script
# - start supervisor
#
ADD resources/mailer.py /opt/mailer/
ADD resources/log.cfg /opt/mailer/
ADD resources/supervisor /etc/supervisor/conf.d
CMD /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf