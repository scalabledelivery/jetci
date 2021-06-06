Operating this task list is important. Once all sub-items are removed from a primary task, `CHANGELOG.md` needs to be added to.

Priority goes to the top of the list.

# Requirements for `v1alpha1` to `v1beta1`
These are the milestone requirements to become `v1beta1` software.

## Timeouts
Need `readinessTimeout` and `pipelineTimeout`.

## Debugging and Error Logging Improvement
Logging needs to be timestamped.
Formatting needs to be cleaner... or easier to read.
Debugging information needs to be made available.

## Per Build Locking
Right now all build status and log updates are handled only by the lock object `run_locker`. This can be changed as an optimization. The only reason a single lock was used was to simplify development.

## Rules engine - Auth required in namespace

## Rules engine - Allow Privileged Containers

## Rules engine - MaxTimeout

## Override branch in build object
Perhaps people would like to be able to selectively choose their branch. This requires a change to the build CRD.
