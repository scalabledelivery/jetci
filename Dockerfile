FROM python:3
ENV JETCI_MODE=operator
WORKDIR /usr/src/
COPY . /usr/src/
ENTRYPOINT /bin/bash /usr/src/jetci-entrypoint.sh