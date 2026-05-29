FROM mcr.microsoft.com/devcontainers/cpp:ubuntu-22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    gdb \
    git \
    wget \
    curl \
    vim \
    nano \
    net-tools \
    dbus-x11 \
    x11-xserver-utils \
    xfce4 \
    xfce4-terminal \
    tigervnc-standalone-server \
    tigervnc-common \
    novnc \
    websockify \
    qtbase5-dev \
    qtchooser \
    qt5-qmake \
    qtbase5-dev-tools \
    qttools5-dev \
    qttools5-dev-tools \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV DISPLAY=:1
ENV QT_X11_NO_MITSHM=1
