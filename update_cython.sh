#!/bin/sh
cython src/psd_tools/*.pyx -a
cython src/psd_tools/user_api/*.pyx -a
