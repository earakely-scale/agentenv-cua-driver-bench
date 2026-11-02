# The bench's grading container: Python 3 for trycua's evaluators and scoring, and Node 22 for the evaluator of a task
# that serves a site, at the version cdb-s04's app pins. A trial's steps load the task pack and the trial's snapshot
# into it and run grade.py there, with no network.
FROM node:22-bookworm@sha256:18a6d90fd60542269850c80ca03b29b1d9b14d6b221ac7ee8e35b0d33ef904bd
COPY grade.py /grade/grade.py
