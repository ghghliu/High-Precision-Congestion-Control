# HPCC / NS-3.17 build environment.
#
# NS-3.17 ships a self-contained waf (waf 1.7) that only runs under Python 2,
# and its C++ code follows an older style that fails to compile with modern
# GCC (>5). Ubuntu 16.04 provides Python 2.7 and GCC 5 out of the box, which
# is the toolchain this simulator was written for.
FROM ubuntu:16.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        make \
        python \
        git \
        curl \
        ca-certificates \
        sudo \
    && rm -rf /var/lib/apt/lists/*

# Cloud Agents check out the repository and run commands as a non-root user.
RUN useradd -m -s /bin/bash -u 1000 ubuntu \
    && echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ubuntu \
    && chmod 0440 /etc/sudoers.d/ubuntu

USER ubuntu
WORKDIR /home/ubuntu
