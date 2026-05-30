FROM mcr.microsoft.com/devcontainers/cpp:1-ubuntu-24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        cmake \
        ninja-build \
        build-essential \
        gdb \
        git \
        curl \
        wget \
        nano \
        vim \
        net-tools \
        python3 \
        python3-pip \
        python3-venv \
        python3-pyqt6 \
        pyqt6-dev-tools \
        fontconfig \
        fonts-dejavu-core \
        fonts-noto-cjk \
        fonts-noto-color-emoji \
        libgl1 \
        libegl1 \
        libxkbcommon-x11-0 \
        libxcb-cursor0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-randr0 \
        libxcb-render-util0 \
        libxcb-shape0 \
        libxcb-xinerama0 \
        libxcb-xinput0 \
        dbus-x11 \
        xauth \
        x11-xserver-utils \
        xterm \
        xfce4 \
        xfce4-session \
        xfce4-panel \
        xfdesktop4 \
        xfwm4 \
        xfce4-terminal \
        tigervnc-standalone-server \
        tigervnc-common \
        tigervnc-tools \
        novnc \
        websockify \
    && fc-cache -f \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER vscode

WORKDIR /workspaces/framework
