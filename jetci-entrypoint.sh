#!/bin/bash
set -e -x
case "${JETCI_MODE}" in
  "operator")
    python3 /usr/src/operator.py
    ;;

  "webhook")
    echo "Webhook is not available yet."
    ;;

  *)
    echo "JETCI_MODE not implemented: ${JETCI_MODE}"
    exit 0
    ;;
esac
