# Change Logs

## Guidelines
When making an entry, first generate a UTC datestamp with `date -u "+%Y%m%d.%H%M"`.

Each section should be titled in the form of `{datestamp} - {short description}`.

Entries should be prepended to the `History` section.

# History

## 20210606.0638 - Service Containers, Readiness Probes, Privileged Containers and Container Logging
Containers already just run, which meets the need for a "Service Container". This change entry focuses on making this useful.

Container output is now logged in the build log, which is neccessary to see what's up with container services.

Added ability to make containers privileged.

All containers in a pod must now be "ready" before commands are executed. To make this useful, readiness probes have been exposed to .jetci.yaml.

Fixed a bug where invalid YAML files caused a crash in `operator_loop()`.

## 20210605.2216 - Added Webhook Endpoint
The most notable change here was that `crds.yaml` was updated to have API token info be required. 