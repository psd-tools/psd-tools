#!/usr/bin/env bash

set -eux

# Add a setup.cfg file to configure the ABI tag for the built wheel.
tee setup.cfg <<EOF
[bdist_wheel]
py_limited_api = cp313
EOF
