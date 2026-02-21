#!/bin/bash

case "$1" in
  on)
    flatpak run com.github.wwmm.easyeffects -l "Mic - Echo Canceller v2"
    ;;
  off)
    flatpak run com.github.wwmm.easyeffects -l "Mic - No Echo Canceller"
    ;;
esac
