#!/bin/sh
case "$1" in
    pre)
        modprobe -r ov01a10 intel_ipu6_isys intel_ipu6
        ;;
    post)
        modprobe intel_ipu6
        ;;
esac
