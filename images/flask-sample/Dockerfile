FROM autodeskcloud/pod:1.0.2

#
# - add our spiffy pod script + the flask endpoint code & its templates
# - add our supervisor script
# - start supervisor
#
#RUN pip install psutil
ADD resources/pod /opt/flask/pod
ADD resources/webserver.py /opt/flask/
ADD resources/testy-echo.py /opt/flask/
ADD resources/static /opt/flask/static
ADD resources/templates /opt/flask/templates
ADD resources/supervisor /etc/supervisor/conf.d
CMD /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf