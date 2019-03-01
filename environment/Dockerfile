FROM ubuntu:bionic

LABEL tailor="builder"

ARG AWS_ACCESS_KEY_ID
ENV AWS_ACCESS_KEY_ID ${AWS_ACCESS_KEY_ID}

ARG AWS_SECRET_ACCESS_KEY
ENV AWS_SECRET_ACCESS_KEY ${AWS_SECRET_ACCESS_KEY}

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install --no-install-recommends -y locales curl gnupg1 gpgv1 sudo
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8

RUN apt-get update && apt-get install --no-install-recommends -y \
  python3-dev \
  python3-pip \
  python3-setuptools \
  python3-wheel \
  git

# Let's start with some basic stuff.
RUN apt-get update -qq && apt-get install -qqy \
    apt-transport-https \
    ca-certificates \
    curl \
    lxc \
    iptables

# Install Docker from Docker Inc. repositories.
RUN curl -sSL https://get.docker.com/ | sh

RUN pip3 install \
    click \
    PyYaml \
    pytest \
    pytest-mypy \
    pytest-flake8 \
    pytest-runner \
    docker

COPY tailor-image tailor-image
RUN pip3 install -e tailor-image

COPY rosdistro/rosdep/rosdep.yaml /root/rosdep.yaml

# Create non-root user
RUN groupadd -r tailor && useradd -ms /bin/bash -g tailor -G sudo tailor
RUN usermod -aG docker tailor
RUN echo "tailor ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers
USER tailor
RUN mkdir -p /home/tailor && \
    usermod -d /home/tailor tailor
