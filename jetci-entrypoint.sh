#!/bin/bash
set -e -x
case "${JETCI_MODE}" in
  "operator")
    python3 /usr/src/operator.py
    ;;

  "webhook")
    python3 /usr/src/endpoint.py
    ;;

  *)
    echo "JETCI_MODE not implemented: ${JETCI_MODE}"
    exit 0
    ;;
esac
