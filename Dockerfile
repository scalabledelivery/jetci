FROM python:3
ENV JETCI_MODE=operator
WORKDIR /usr/src/
COPY . /usr/src/
RUN pip3 install -r /usr/src/requirements.txt
ENTRYPOINT /bin/bash /usr/src/jetci-entrypoint.sh