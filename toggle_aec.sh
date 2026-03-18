#!/bin/bash

case "$1" in
  on)
    flatpak run com.github.wwmm.easyeffects -l "Mic - Echo Canceller v2" 2>/dev/null
    ;;
  off)
    flatpak run com.github.wwmm.easyeffects -l "Mic - No Echo Canceller" 2>/dev/null
    ;;
esac
