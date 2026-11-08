# ~/.bash_profile
[[ -f ~/.bashrc ]] && . ~/.bashrc

# termOS: start the desktop automatically on the first console.
if [[ -z $WAYLAND_DISPLAY && $(tty) == /dev/tty1 ]]; then
    exec termos-session
fi
